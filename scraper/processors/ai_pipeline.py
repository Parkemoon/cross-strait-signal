import os
import sys
import json
from datetime import datetime, timezone
from dotenv import load_dotenv

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
  "topic_primary": "one of: MIL_EXERCISE, MIL_MOVEMENT, MIL_HARDWARE, DIP_STATEMENT, DIP_VISIT, DIP_SANCTIONS, ECON_TRADE, ECON_INVEST, POL_DOMESTIC, POL_UNIFICATION, INFO_WARFARE, LEGAL_GREY, HUMANITARIAN",
  "topic_secondary": null,
  "sentiment": "one of: escalatory, conciliatory, neutral, ambiguous",
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
- sentiment_score ranges from -1.0 (strongly conciliatory) to +1.0 (strongly escalatory)
- Only flag is_escalation_signal for genuinely significant developments, not routine rhetoric
- urgency: flash = breaking/status quo change, priority = notable, routine = standard coverage
- Extract ALL named entities: people, military units, ships, aircraft, locations, organisations
- Return ONLY valid JSON. No markdown code blocks, no commentary, no text before or after the JSON.
- All strings in the JSON must have special characters properly escaped.
- If the article is not related to cross-strait relations, still classify it using the best-fit topic."""

def analyse_article(title, content, language, source_name):
    """Send one article to Gemini and return structured analysis."""
    prompt = f"""{ANALYSIS_SYSTEM_PROMPT}

SOURCE: {source_name}
LANGUAGE: {language}
TITLE: {title}

FULL TEXT:
{content[:5000]}"""

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "max_output_tokens": 8000
        }
    )

    try:
        return json.loads(response.text)
    except json.JSONDecodeError:
        # Sometimes the model returns JSON wrapped in markdown code blocks
        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1]  # Remove first line
            text = text.rsplit("```", 1)[0]  # Remove last ```
        return json.loads(text)


def process_unanalysed_articles(limit=10):
    """Find articles that haven't been analysed yet and process them.
    
    Args:
        limit: Maximum number of articles to process in one run (to control API costs)
    """
    conn = get_connection()

    # Get unprocessed articles, joined with their source info
    articles = conn.execute("""
        SELECT articles.id, articles.title_original, articles.content_original,
               articles.language, sources.name as source_name
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

    print(f"Processing {len(articles)} articles...\n")

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
                'gemini-2.5-flash',
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
            success_count += 1
            print(f"    Topic: {analysis.get('topic_primary')} | Sentiment: {analysis.get('sentiment')} | Escalation: {analysis.get('is_escalation_signal')}")

        except Exception as e:
            error_count += 1
            print(f"    ERROR: {e}")
            # Mark as processed anyway so we don't retry forever
            conn.execute(
                "UPDATE articles SET ai_processed = 1, ai_processed_at = ? WHERE id = ?",
                datetime.now(timezone.utc).isoformat(), article['id'])
            conn.commit()

    conn.close()
    print(f"\nDone. {success_count} analysed successfully, {error_count} errors.")


if __name__ == '__main__':
    process_unanalysed_articles(limit=10)