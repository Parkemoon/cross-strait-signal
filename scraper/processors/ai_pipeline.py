import os
import sys
import json
import time
from datetime import datetime, timezone
from dotenv import load_dotenv
from scraper.processors.keyword_filter import check_relevance

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

load_dotenv()

from google import genai
from scraper.utils.db import get_connection

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

ANALYSIS_SYSTEM_PROMPT = """You are an intelligence analyst specialising in cross-strait 
relations between the People's Republic of China and Taiwan. You are processing a media 
article for a monitoring dashboard.

Analyse the following article and return a JSON object with this exact structure:

{
  "title_en": "English translation of the title (or original if already English)",
  "summary_en": "2-3 sentence English summary of the article's key content and significance",
  "topic_primary": "one of: MIL_EXERCISE, MIL_MOVEMENT, MIL_HARDWARE, DIP_STATEMENT, DIP_VISIT, DIP_SANCTIONS, ECON_TRADE, ECON_INVEST, POL_DOMESTIC, POL_TONGDU, INFO_WARFARE, LEGAL_GREY, HUMANITARIAN",
  "topic_secondary": null,
  "sentiment": "one of: destabilising, stabilising, neutral, ambiguous",
  "sentiment_score": 0.0,
  "urgency": "one of: flash, priority, routine",
  "key_quote": "most significant direct quote from the article in original language",
  "key_quote_en": "English translation of the key quote",
  "is_new_formulation": false,
  "is_escalation_signal": false,
  "escalation_note": null,
  "entities": [
    {
      "name": "entity name in original language",
      "name_en": "English name",
      "type": "one of: person, military_unit, ship, aircraft, location, organisation, weapon_system",
      "role": "brief role description",
      "location": null
    }
  ],
  "keywords_matched": [
    {
      "keyword": "matched keyword",
      "category": "keyword taxonomy category"
    }
  ],
  "confidence": 0.8
}

IMPORTANT:
- sentiment_score ranges from -1.0 (strongly stabilising) to +1.0 (strongly destabilising)
- sentiment axis is stabilising/destabilising relative to the cross-strait status quo — a DPP sovereignty push and a PLA exercise are both destabilising; a TAO investment welcome and a KMT mainland visit can be stabilising. Do not pre-judge which side causes instability.
- stabilising = -1.0 to -0.3, neutral = -0.3 to +0.3, destabilising = +0.3 to +1.0
- Only flag is_escalation_signal for genuinely significant developments, not routine rhetoric
- urgency: flash = breaking/status quo change, priority = notable, routine = standard coverage
- Extract ALL named entities: people, military units, ships, aircraft, locations, organisations
- All strings in the JSON must have special characters properly escaped.
- Unification/independence spectrum (統獨): reunification rhetoric, independence moves, sovereignty claims, constitutional norm changes, status quo shifts from either side
- RELEVANCE: If the article has NO direct connection to PRC-Taiwan relations, cross-strait dynamics, PRC foreign/military policy, or Taiwan defence/security policy, set topic_primary to "NOT_RELEVANT" and confidence to 0.0.
- If the article is primarily about a third-party conflict (e.g. US-Iran, Russia-Ukraine) and China's role is only peripheral, set topic_primary to "NOT_RELEVANT".
- If the article is about Taiwan domestic affairs with NO cross-strait dimension (local elections unrelated to cross-strait, crime, weather, sports, entertainment, consumer news, social media trends), set topic_primary to "NOT_RELEVANT".
- Only classify an article if it directly involves: PRC-Taiwan military/diplomatic/economic relations, PRC statements about Taiwan, Taiwan defence/security policy, cross-strait political dynamics, or PRC foreign policy with direct Taiwan implications.
- For Taiwanese political figures, use the official romanisation used by their party or office. Key figures: 賴清德 = Lai Ching-te, 蕭美琴 = Hsiao Bi-khim, 鄭麗文 = Cheng Li-wen, 韓國瑜 = Han Kuo-yu, 柯文哲 = Ko Wen-je. Do not invent romanisations.
- Return ONLY valid JSON. No markdown code blocks, no commentary, no text before or after the JSON."""


def analyse_article(title, content, language, source_name):
    """Send one article to Gemini and return structured analysis."""
    prompt = f"""{ANALYSIS_SYSTEM_PROMPT}

SOURCE: {source_name}
LANGUAGE: {language}
TITLE: {title}

FULL TEXT:
{content[:5000]}"""

    response = client.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "max_output_tokens": 8000
        }
    )

    try:
        return json.loads(response.text)
    except json.JSONDecodeError:
        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            text = text.rsplit("```", 1)[0]
        return json.loads(text)


def process_unanalysed_articles(limit=10):
    """Find articles that haven't been analysed yet and process them."""
    conn = get_connection()

    articles = conn.execute("""
        SELECT articles.id, articles.title_original, articles.content_original,
               articles.language, sources.name as source_name,
               sources.country as source_country
        FROM articles
        JOIN sources ON articles.source_id = sources.id
        WHERE articles.ai_processed = 0
          AND articles.content_original != ''
        ORDER BY articles.published_at DESC
        LIMIT ?
    """, (limit,)).fetchall()

    if not articles:
        print("No unprocessed articles found.")
        conn.close()
        return

    # Pre-filter: check keyword relevance before spending API tokens
    relevant_articles = []
    filtered_count = 0

    for article in articles:
        is_relevant, categories, keywords = check_relevance(
            article['title_original'],
            article['content_original'],
            article['language'],
            source_country=article['source_country']
        )

        if is_relevant:
            relevant_articles.append(article)
        else:
            conn.execute(
                "UPDATE articles SET ai_processed = 1, ai_processed_at = ? WHERE id = ?",
                (datetime.now(timezone.utc).isoformat(), article['id'])
            )
            filtered_count += 1

    conn.commit()

    print(f"Pre-filter: {len(articles)} articles checked, {len(relevant_articles)} relevant, {filtered_count} filtered out\n")

    if not relevant_articles:
        print("No relevant articles to process.")
        conn.close()
        return

    articles = relevant_articles
    print(f"Processing {len(articles)} relevant articles...\n")

    success_count = 0
    error_count = 0

    for article in articles:
        title = article['title_original']
        print(f"  Analysing: {title[:60]}...")

        try:
            analysis = analyse_article(
                title=title,
                content=article['content_original'],
                language=article['language'],
                source_name=article['source_name']
            )

            # Skip articles the AI identifies as irrelevant
            if analysis.get('topic_primary') == 'NOT_RELEVANT':
                conn.execute(
                    "UPDATE articles SET ai_processed = -1, ai_processed_at = ? WHERE id = ?",
                    (datetime.now(timezone.utc).isoformat(), article['id'])
                )
                conn.commit()
                print(f"    Skipped: not relevant to cross-strait monitoring")
                continue

            # Update the article with translation
            conn.execute("""
                UPDATE articles
                SET title_en = ?, content_en = ?, ai_processed = 1, ai_processed_at = ?
                WHERE id = ?
            """, (
                analysis.get('title_en', title),
                analysis.get('summary_en', ''),
                datetime.now(timezone.utc).isoformat(),
                article['id']
            ))

            # Insert analysis results
            conn.execute("""
                INSERT INTO ai_analysis
                (article_id, topic_primary, topic_secondary, sentiment, sentiment_score,
                 urgency, summary_en, key_quote, key_quote_en,
                 is_new_formulation, is_escalation_signal, escalation_note,
                 model_used, confidence)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                article['id'],
                analysis.get('topic_primary', 'HUMANITARIAN'),
                analysis.get('topic_secondary'),
                analysis.get('sentiment', 'neutral'),
                analysis.get('sentiment_score', 0.0),
                analysis.get('urgency', 'routine'),
                analysis.get('summary_en', ''),
                analysis.get('key_quote'),
                analysis.get('key_quote_en'),
                analysis.get('is_new_formulation', False),
                analysis.get('is_escalation_signal', False),
                analysis.get('escalation_note'),
                analysis.get('_model_used', 'gemini-2.5-flash-lite'),
                analysis.get('confidence', 0.0)
            ))

            # Insert entities
            for entity in analysis.get('entities', []):
                conn.execute("""
                    INSERT INTO entities
                    (article_id, entity_name, entity_name_en, entity_type,
                     entity_role, location_name)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    article['id'],
                    entity.get('name', ''),
                    entity.get('name_en', ''),
                    entity.get('type', 'organisation'),
                    entity.get('role', ''),
                    entity.get('location')
                ))

            # Insert keyword matches
            for kw in analysis.get('keywords_matched', []):
                conn.execute("""
                    INSERT INTO keywords_matched
                    (article_id, keyword, keyword_category)
                    VALUES (?, ?, ?)
                """, (
                    article['id'],
                    kw.get('keyword', ''),
                    kw.get('category', '')
                ))

            conn.commit()

             # Flag low confidence articles for human review
            if analysis.get('confidence', 1.0) < 0.7:
                conn.execute("""
                    UPDATE ai_analysis SET needs_human_review = 1, review_reason = ?
                    WHERE article_id = ?
                """, (f"Low confidence: {analysis.get('confidence', 0):.2f}", article['id']))
                conn.commit()

            # Escalation review: re-analyse with Flash for flagged articles
            if analysis.get('is_escalation_signal') or analysis.get('urgency') == 'flash':
                try:
                    # Save Flash Lite values BEFORE overwriting with Flash review
                    lite_sentiment = analysis.get('sentiment')
                    lite_escalation = analysis.get('is_escalation_signal')
                    lite_topic = analysis.get('topic_primary')
                    lite_confidence = analysis.get('confidence', 1.0)

                    review = client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=f"""{ANALYSIS_SYSTEM_PROMPT}

SOURCE: {article['source_name']}
LANGUAGE: {article['language']}
TITLE: {title}

FULL TEXT:
{article['content_original'][:5000]}""",
                        config={
                            "response_mime_type": "application/json",
                            "max_output_tokens": 8000
                        }
                    )
                    review_analysis = json.loads(review.text)

                    # Update analysis dict with Flash's assessment
                    analysis['sentiment'] = review_analysis.get('sentiment', analysis['sentiment'])
                    analysis['sentiment_score'] = review_analysis.get('sentiment_score', analysis['sentiment_score'])
                    analysis['is_escalation_signal'] = review_analysis.get('is_escalation_signal', analysis['is_escalation_signal'])
                    analysis['escalation_note'] = review_analysis.get('escalation_note', analysis.get('escalation_note'))
                    analysis['entities'] = review_analysis.get('entities', analysis.get('entities', []))

                    # Update the database with Flash's assessment
                    conn.execute("""
                        UPDATE ai_analysis SET sentiment = ?, sentiment_score = ?,
                        is_escalation_signal = ?, escalation_note = ?, model_used = ?
                        WHERE article_id = ?
                    """, (
                        analysis['sentiment'], analysis['sentiment_score'],
                        analysis['is_escalation_signal'], analysis.get('escalation_note'),
                        'gemini-2.5-flash (review)', article['id']
                    ))
                    conn.commit()

                    # --- HUMAN REVIEW FLAGGING ---
                    # Compare Flash Lite originals vs Flash review
                    review_reasons = []
                    flash_confidence = review_analysis.get('confidence', 1.0)

                    if review_analysis.get('sentiment') != lite_sentiment:
                        review_reasons.append(
                            f"Sentiment disagreement: Flash Lite={lite_sentiment} / Flash={review_analysis.get('sentiment')}"
                        )

                    if review_analysis.get('is_escalation_signal') != lite_escalation:
                        review_reasons.append(
                            f"Escalation disagreement: Flash Lite={lite_escalation} / Flash={review_analysis.get('is_escalation_signal')}"
                        )

                    if lite_confidence < 0.7 or flash_confidence < 0.7:
                        review_reasons.append(
                            f"Low confidence: Flash Lite={lite_confidence} / Flash={flash_confidence}"
                        )

                    if review_analysis.get('topic_primary') != lite_topic:
                        review_reasons.append(
                            f"Topic disagreement: Flash Lite={lite_topic} / Flash={review_analysis.get('topic_primary')}"
                        )

                    if review_reasons:
                        conn.execute("""
                            UPDATE ai_analysis
                            SET needs_human_review = 1, review_reason = ?
                            WHERE article_id = ?
                        """, (' | '.join(review_reasons), article['id']))
                        conn.commit()
                        print(f"    ↳ Flagged for human review: {review_reasons[0]}")

                    print(f"    ↳ Escalation review (Flash): Sentiment={analysis['sentiment']} | Confirmed={analysis['is_escalation_signal']}")

                except Exception as e:
                    print(f"    ↳ Escalation review failed: {e}")

            time.sleep(0.3)
            success_count += 1
            print(f"    Topic: {analysis.get('topic_primary')} | Sentiment: {analysis.get('sentiment')} | Escalation: {analysis.get('is_escalation_signal')}")

        except Exception as e:
            error_count += 1
            print(f"    ERROR: {e}")
            conn.execute(
                "UPDATE articles SET ai_processed = 1, ai_processed_at = ? WHERE id = ?",
                (datetime.now(timezone.utc).isoformat(), article['id'])
            )
            conn.commit()

    conn.close()
    print(f"\nDone. {success_count} analysed successfully, {error_count} errors.")


if __name__ == '__main__':
    process_unanalysed_articles(limit=10)