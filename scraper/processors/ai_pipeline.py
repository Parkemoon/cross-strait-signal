import os
import sys
import json
import time
from datetime import datetime, timezone
from dotenv import load_dotenv
from scraper.processors.keyword_filter import check_relevance

_GLOSSARY_PATH = os.path.join(os.path.dirname(__file__), 'glossary.json')
with open(_GLOSSARY_PATH, encoding='utf-8') as _f:
    _MASTER_GLOSSARY = json.load(_f)

_CANONICAL_PATH = os.path.join(os.path.dirname(__file__), 'entity_canonical.json')
with open(_CANONICAL_PATH, encoding='utf-8') as _f:
    _CANONICAL_ENTITIES = json.load(_f)


def _normalise_entity_name(entity):
    """Override entity name_en with the canonical English form if the Chinese
    name matches an entry in entity_canonical.json. Substring matching handles
    cases where the AI returns a longer form (e.g. 中國人民解放軍 matching 解放軍).
    Only keys with 2+ characters are used for substring matching to avoid
    false positives from single-character suffixes.
    Also normalises whitespace and fixes all-lowercase names (AI slip)."""
    zh_name = entity.get('name', '')
    if not zh_name:
        return entity

    # Canonical map lookup
    for zh, en in _CANONICAL_ENTITIES.items():
        if len(zh) < 2:
            continue
        if zh == zh_name or (zh in zh_name or zh_name in zh):
            entity['name_en'] = en
            return entity

    # Normalise whitespace and fix all-lowercase names
    name_en = ' '.join(entity.get('name_en', '').split())
    if name_en and name_en == name_en.lower():
        name_en = name_en.title()
    entity['name_en'] = name_en
    return entity

_KEY_FIGURES_PATH = os.path.join(os.path.dirname(__file__), 'key_figures.json')
try:
    with open(_KEY_FIGURES_PATH, encoding='utf-8') as _kf:
        _KEY_FIGURES_LIST = json.load(_kf)
except Exception:
    _KEY_FIGURES_LIST = []

# alias (lowercased) → figure_id lookup
_ALIAS_TO_FIGURE_ID = {}
for _fig in _KEY_FIGURES_LIST:
    for _alias in _fig.get('aliases', []):
        _ALIAS_TO_FIGURE_ID[_alias.lower()] = _fig['id']

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

load_dotenv()

from google import genai
from scraper.utils.db import get_connection

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

ANALYSIS_SYSTEM_PROMPT = """You are an intelligence analyst specialising in cross-strait
relations between the People's Republic of China and Taiwan. You are processing a media
article for a monitoring dashboard.

STEP 1 — RELEVANCE GATE (decide this first, before anything else):
Ask yourself: is this article's PRIMARY subject PRC-Taiwan cross-strait dynamics?
Set is_cross_strait_primary to false if ANY of the following apply:
- The article is primarily about a third-party event (e.g. Iran war, Russia-Ukraine, US domestic politics) and PRC/Taiwan appears only as a comparison, analogy, or peripheral reference
- The article is about Taiwan domestic affairs with no cross-strait dimension (crime, weather, sports, entertainment, consumer news, local governance, obituaries)
- PRC or Taiwan is mentioned only in passing, not as the main subject
If is_cross_strait_primary is false, set topic_primary to "NOT_RELEVANT" and confidence to 0.0. Do not fill in other fields.

IMPORTANT EXCEPTION — PRC sources writing about Taiwan: If the SOURCE is a PRC outlet (People's Daily, Xinhua, Global Times, The Paper, TAO, MFA, Guancha, PLA Daily, Haixia Daobao, etc.) and Taiwan is the article's PRIMARY subject, treat it as relevant regardless of topic. PRC state and nationalist media coverage of Taiwanese society, culture, festivals, and everyday life carries cross-strait analytical value as identity and sovereignty framing. Use POL_TONGDU for articles that emphasise Taiwan's Chinese cultural heritage, cross-strait people-to-people ties, or shared identity — this framing is analytically equivalent to Taiwanese sources emphasising indigenous identity or distinct Taiwanese nationhood; both are moves on the unification/independence spectrum and should be treated symmetrically. Use INFO_WARFARE only for active disinformation or cognitive warfare operations (e.g. fabricated stories, coordinated inauthentic narratives). Use POL_DOMESTIC_TW for PRC reporting on Taiwan's political life.

Analyse the following article and return a JSON object with this exact structure:

{
  "is_cross_strait_primary": true,
  "title_en": "English translation of the title (or original if already English)",
  "summary_en": "2-3 sentence English summary of the article's key content and significance",
  "topic_primary": "one of: MIL_EXERCISE, MIL_MOVEMENT, MIL_HARDWARE, MIL_POLICY, DIP_STATEMENT, DIP_VISIT, DIP_SANCTIONS, PARTY_VISIT, ECON_TRADE, ECON_INVEST, POL_DOMESTIC_TW, POL_DOMESTIC_PRC, POL_TONGDU, INFO_WARFARE, LEGAL_GREY, TRANSPORT, INT_ORG, HUMANITARIAN, US_PRC, US_TAIWAN, HK_MAC, CULTURE, CYBER, ARMS_SALES, SPORT, ENERGY, SCI_TECH, NOT_RELEVANT",
  "topic_secondary": null,
  "sentiment": "one of: hostile, cooperative, neutral, mixed",
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
  "key_figure_statements": [
    {
      "speaker": "name exactly as it appears in the article",
      "statement_text": "MUST be in English — translate from Chinese/other language if needed; for quotes use direct speech, for actions a brief description",
      "statement_zh": "original-language text — copy verbatim from article",
      "statement_kind": "quote or action",
      "confidence": 0.9
    }
  ],
  "confidence": 0.8
}

CLASSIFICATION RULES:
- sentiment_score measures cross-strait sentiment — how positively or negatively the article frames the opposing side or the overall relationship. Score from -1.0 (strongly hostile) to +1.0 (strongly cooperative).
- For PRC sources: how does the article portray Taiwan, Taiwanese actors, or cross-strait relations?
- For Taiwan sources: how does the article portray the PRC, mainland actors, or cross-strait relations?
- For international/SG sources: what is the overall tone toward cross-strait dynamics?
- CRITICAL: Do NOT confuse cooperation between Taiwan and third parties (e.g. US, Japan, allies) with a cooperative sentiment toward the PRC. Taiwan-US military cooperation, arms sales, or joint exercises are not cross-strait cooperative signals — score them neutral or hostile depending on how the article frames the PRC, not on how Taiwan relates to the US.
- hostile (-1.0 to -0.3): threatening, antagonistic, confrontational, emphasising division, military pressure, sovereignty assertions against the other side
- neutral (-0.3 to +0.3): factual reporting without strong positive or negative framing
- cooperative (+0.3 to +1.0): warm, friendly, emphasising shared identity, engagement, dialogue, trade, people-to-people ties
- mixed: article contains both hostile and cooperative elements that cannot be clearly resolved to one direction
- Score the PRIMARY EVENT of the article, not an average of all perspectives. A KMT-CCP forum with cooperative statements scores cooperative even if the DPP criticises it. A PLA exercise scores hostile even if Taiwan responds calmly. A KMT or opposition party visit to the mainland — meetings, cultural exchanges, mausoleum visits, youth forums — scores cooperative regardless of the political symbolism involved (e.g. ROC calendar references, 1992 Consensus framing). The political complexity of such visits does not make them mixed; mixed requires genuine hostile and cooperative elements in roughly equal weight.
- MIL_POLICY covers military doctrine, defence budgets, force structure decisions, conscription policy, arms sales approvals (the political/policy decision, not the hardware itself), defence white papers, and MND statements on defence posture. Use MIL_HARDWARE for articles primarily about a specific weapon or platform; use MIL_POLICY when the focus is on a decision, budget, strategy, or institutional change. DIP_STATEMENT is for MFA/TAO diplomatic pronouncements; MIL_POLICY is for defence ministry/military institutional policy.
- TRANSPORT covers cross-strait transport and connectivity: flights, shipping, ferry links, port closures, aviation routes, and infrastructure connecting Taiwan and the mainland (including Kinmen-Xiamen links). Do not use HUMANITARIAN for transport disruptions.
- INT_ORG covers Taiwan's participation in, exclusion from, or treatment by international organisations (UN, WHO, UNESCO, ICAO, Interpol, etc.), and PRC efforts to block or shape Taiwan's international standing through multilateral bodies. Also covers PRC nationals in leadership roles at international organisations where this has cross-strait relevance.
- POL_DOMESTIC_TW covers Taiwan domestic politics with a cross-strait dimension (e.g. Taiwan legislature debating defence budgets, DPP/KMT domestic positioning on cross-strait policy, Taiwan election dynamics). POL_DOMESTIC_PRC covers PRC domestic politics with cross-strait relevance (e.g. NPC decisions affecting Taiwan policy, CCP leadership changes, PRC internal political signalling toward Taiwan). Use the subject of the article, not the source — a PRC outlet reporting on Taiwan domestic politics is POL_DOMESTIC_TW.
- DIP_VISIT is strictly for official state or government visits — head of state, government ministers, or official delegations acting in a governmental capacity. PARTY_VISIT is for party-to-party visits and meetings — KMT-CCP Forums, opposition party delegations to the mainland, CCP officials meeting Taiwan party figures in a non-governmental capacity. A KMT chair visiting Beijing is always PARTY_VISIT, never DIP_VISIT.
- US_PRC covers US-China relations with cross-strait relevance: US-China diplomatic meetings, trade/tech sanctions between Washington and Beijing, US naval operations in the Pacific as part of China deterrence, statements by US officials on China policy. Use when the US-China relationship itself is the primary subject, not Taiwan's relationship with the US.
- US_TAIWAN covers US-Taiwan relations: US political support for Taiwan, US-Taiwan economic and trade ties, US congressional legislation on Taiwan, US officials visiting Taiwan or meeting Taiwanese officials, US statements on Taiwan's status. Use ARMS_SALES for the specific arms transfer events; US_TAIWAN for the broader relationship.
- HK_MAC covers Hong Kong and Macau with cross-strait relevance: Beijing's governance of HK, erosion of "one country, two systems," HK as a model or warning for Taiwan, Macau political developments, cross-strait implications of HK/Macau dynamics.
- CULTURE covers cross-strait cultural exchange and soft power: Taiwanese artists/films/media popular on the mainland or vice versa, cultural festivals, tourism with cultural dimensions, shared heritage framing, people-to-people cultural ties. Use POL_TONGDU when the cultural framing is explicitly about sovereignty or national identity; use CULTURE for articles where cultural exchange is the primary subject without strong political framing.
- CYBER covers cyber operations, hacking, digital espionage, and infrastructure attacks with a cross-strait dimension: PRC-attributed cyberattacks on Taiwan, Taiwanese or allied cyber operations, cyber espionage cases, critical infrastructure intrusions. Distinct from INFO_WARFARE (narrative/propaganda operations) — CYBER is about technical intrusion and sabotage.
- ARMS_SALES covers arms transfer events and export control decisions: US government approval of arms packages to Taiwan, specific weapons system sales, third-party arms deals relevant to the strait, export control measures on defence technology. Use MIL_POLICY for the broader defence posture context; ARMS_SALES for the specific transfer or approval event.
- SPORT covers sporting events and disputes with cross-strait political dimensions: Olympic naming disputes ("Chinese Taipei"), cross-strait athletic competitions, sports boycotts, use of sport as soft power or political signal.
- SCI_TECH covers science, technology, and innovation with cross-strait relevance: semiconductor industry (TSMC, chip supply chains, foundry capacity), chip and tech export controls as technology policy, space programmes, AI competition and development, scientific exchanges across the strait, tech talent flows, cross-strait tech industry dynamics. Use ECON_TRADE for broad trade sanctions; use SCI_TECH when the primary subject is a specific technology, research programme, or innovation development. Use CYBER for digital intrusion operations; use SCI_TECH for civilian or dual-use technology industry and research topics. Use ARMS_SALES for defence hardware transfers; use SCI_TECH for dual-use or civilian tech.
- ENERGY covers energy security with cross-strait relevance: Taiwan's energy imports and supply chains, nuclear power policy, LNG procurement, energy infrastructure vulnerability, PRC energy leverage over Taiwan, shipping lane economics as they relate to energy supply.
- Only flag is_escalation_signal for genuinely significant developments, not routine rhetoric
- urgency: flash = breaking/status quo change, priority = notable, routine = standard coverage
- Extract ALL named entities: people, military units, ships, aircraft, locations, organisations
- All strings in the JSON must have special characters properly escaped.
- Unification/independence spectrum (統獨): reunification rhetoric, independence moves, sovereignty claims, constitutional norm changes, status quo shifts from either side
- For ALL Taiwanese entities (people, organisations, places), use Wade-Giles or Tongyong Pinyin. If a person has a known English name or self-used romanisation, prefer that. Do not use Hanyu Pinyin for Taiwanese entities. For ALL PRC entities, use Hanyu Pinyin. Never leave a Chinese name untranslated in an English field — if you cannot find an established romanisation, apply the appropriate system (Wade-Giles for TW, Hanyu Pinyin for PRC) and romanise it yourself. If a CRITICAL TERMINOLOGY MAPPING block is provided, you are strictly forbidden from deviating from its translations.
- KEY FIGURE STATEMENTS: Extract attributed statements only when speaker attribution is UNAMBIGUOUS in the article text. Focus on senior PRC and Taiwan officials (presidents, premiers, party chairs, ministers, official spokespersons, TAO/MAC heads). For 'quote': must be a direct statement BY this speaker — not a description of them, not a paraphrase, not a quote about them. For 'action': only major concrete acts — visits, meetings, signings, orders; NOT background references such as "Xi has previously said…" or passive mentions. If attribution is uncertain in any way, omit entirely. False negatives are strongly preferred over false positives. Return an empty array if no clearly attributed statements exist. CRITICAL: statement_text MUST always be written in English — if the article is in Chinese, translate the quote or action description into English before placing it in statement_text. Never put Chinese characters in statement_text.
- Use British English spelling in all English-language output fields (e.g. "analyse" not "analyze", "behaviour" not "behavior", "colour" not "color", "centre" not "center", "organisation" not "organization").
- Return ONLY valid JSON. No markdown code blocks, no commentary, no text before or after the JSON."""


def generate_dynamic_glossary(content: str, title: str = "") -> str:
    """Scan article text and title against master glossary, return only matched terms."""
    found = {zh: en for zh, en in _MASTER_GLOSSARY.items() if zh in content or zh in title}
    if not found:
        return ""
    lines = [f"- {zh} MUST be translated as: {en}" for zh, en in found.items()]
    return (
        "\n\nCRITICAL TERMINOLOGY MAPPING:\n"
        "You must strictly use the following English translations for these specific terms "
        "found in the text. Do not use alternative romanisations:\n"
        + "\n".join(lines)
    )


def analyse_article(title, content, language, source_name):
    """Send one article to Gemini and return structured analysis."""
    glossary_block = generate_dynamic_glossary(content, title)
    prompt = f"""{ANALYSIS_SYSTEM_PROMPT}{glossary_block}

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
            "max_output_tokens": 8000,
            "temperature": 0.1
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
               sources.place as source_place
        FROM articles
        JOIN sources ON articles.source_id = sources.id
        WHERE articles.ai_processed = 0
          AND articles.content_original != ''
          AND (articles.published_at IS NULL OR articles.published_at >= datetime('now', '-180 days'))
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
            source_place=article['source_place']
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

            # Enforce relevance gate — either field is sufficient to reject
            if not analysis.get('is_cross_strait_primary', True):
                analysis['topic_primary'] = 'NOT_RELEVANT'

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
                entity = _normalise_entity_name(entity)
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

            # Insert key figure statements (pending analyst approval)
            for stmt in analysis.get('key_figure_statements', []):
                speaker = stmt.get('speaker', '').strip()
                figure_id = _ALIAS_TO_FIGURE_ID.get(speaker.lower())
                text = stmt.get('statement_text', '').strip()
                if not figure_id or not text:
                    continue
                # Drop if model returned Chinese instead of translating
                cjk_ratio = sum(1 for c in text if '\u4e00' <= c <= '\u9fff') / len(text)
                if cjk_ratio > 0.15:
                    continue
                conn.execute("""
                    INSERT INTO key_figure_statements
                    (article_id, figure_id, speaker_raw, statement_text, statement_zh,
                     statement_kind, confidence, approval_status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')
                """, (
                    article['id'],
                    figure_id,
                    speaker,
                    text,
                    stmt.get('statement_zh'),
                    stmt.get('statement_kind', 'quote'),
                    stmt.get('confidence', 0.8)
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

                    escalation_glossary = generate_dynamic_glossary(article['content_original'], title)
                    review = client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=f"""{ANALYSIS_SYSTEM_PROMPT}{escalation_glossary}

SOURCE: {article['source_name']}
LANGUAGE: {article['language']}
TITLE: {title}

FULL TEXT:
{article['content_original'][:5000]}""",
                        config={
                            "response_mime_type": "application/json",
                            "max_output_tokens": 8000,
                            "temperature": 0.1
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