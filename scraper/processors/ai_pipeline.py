import os
import re
import sys
import json
import time
from datetime import datetime, timezone
from dotenv import load_dotenv
from scraper.processors.keyword_filter import check_relevance


# Used by the exercise tracker to collapse name variants the AI produces
# for the same activity (e.g. "Formation Drill" / "Formation Exercise" /
# "Formation Training" — all the same event, three different canonical
# keys without this normalisation). Strip the interchangeable trailing
# noun, lowercase, hyphenate.
_EXERCISE_SUFFIX_RE = re.compile(
    r'\s+(drills?|exercises?|trainings?)$', re.IGNORECASE
)


def _build_exercise_canonical_key(name_en: str | None) -> str | None:
    """Lower-hyphenated canonical form used for grouping and auto-merge."""
    if not name_en:
        return None
    stripped = _EXERCISE_SUFFIX_RE.sub('', name_en.strip())
    key = stripped.lower().replace(' ', '-').replace('_', '-')
    return key or None

_GLOSSARY_PATH = os.path.join(os.path.dirname(__file__), 'glossary.json')
with open(_GLOSSARY_PATH, encoding='utf-8') as _f:
    _MASTER_GLOSSARY = json.load(_f)

_CANONICAL_PATH = os.path.join(os.path.dirname(__file__), 'entity_canonical.json')
with open(_CANONICAL_PATH, encoding='utf-8') as _f:
    _CANONICAL_ENTITIES = json.load(_f)

_MIL_LOCATIONS_PATH = os.path.join(os.path.dirname(__file__), 'military_locations.json')
# Companion file written by the API's PATCH endpoint each time an analyst
# supplies coords + a location_label that the lookup didn't already cover.
# Kept separate from military_locations.json so the curated, human-vetted
# entries stay clean while the auto-learned ones accumulate.
_MIL_LOCATIONS_AUTO_PATH = os.path.join(os.path.dirname(__file__), 'military_locations_auto.json')

with open(_MIL_LOCATIONS_PATH, encoding='utf-8') as _f:
    _MIL_LOCATIONS = json.load(_f)
try:
    with open(_MIL_LOCATIONS_AUTO_PATH, encoding='utf-8') as _f:
        _MIL_LOCATIONS = _MIL_LOCATIONS + json.load(_f)
except FileNotFoundError:
    pass
# Sorted longest-name-first within each entry so a search for "Hualien airbase"
# matches before "Hualien" when both appear in the table.
for _entry in _MIL_LOCATIONS:
    _entry['names'] = sorted(_entry['names'], key=len, reverse=True)


def _geocode_from_label(label):
    """Curated case-insensitive substring lookup. Returns (lat, lng) or
    (None, None) when no entry matches. Used to fill coords when the AI
    extracted a location_label but couldn't confidently resolve coordinates
    itself — a deterministic fallback that avoids paying for a second AI
    call and never hallucinates."""
    if not label:
        return None, None
    needle = label.lower()
    for entry in _MIL_LOCATIONS:
        for name in entry['names']:
            if name.lower() in needle:
                return entry['lat'], entry['lng']
    return None, None


def _normalise_entity_name(entity):
    """Override entity name_en with the canonical English form if the Chinese
    name matches an entry in entity_canonical.json. Falls through three tiers:
      1. Exact match (always safe).
      2. Canonical key is a prefix of the extracted name (e.g. 解放軍 → 解放軍海軍).
      3. Canonical key is a prefix of the canonical key — i.e. the AI returned
         the shorter form (e.g. extracted 解放軍 against canonical 中國人民解放軍).
    Bidirectional substring matching is intentionally avoided: it produced
    false positives where short keys like 臺灣 collided with unrelated longer
    entity names that contained them. Only keys with 2+ characters
    participate. Whitespace is normalised and all-lowercase AI output is
    title-cased."""
    zh_name = entity.get('name', '')
    if not zh_name:
        return entity

    for zh, en in _CANONICAL_ENTITIES.items():
        if len(zh) < 2:
            continue
        if zh == zh_name or zh_name.startswith(zh) or zh.startswith(zh_name):
            entity['name_en'] = en
            return entity

    # Normalise whitespace and fix all-lowercase names
    name_en = ' '.join(entity.get('name_en', '').split())
    if name_en and name_en == name_en.lower():
        name_en = name_en.title()
    entity['name_en'] = name_en
    return entity


def _validate_sentiment(sentiment, score, reasoning):
    """Check that sentiment label, numeric score, and reasoning are mutually consistent.
    Returns a list of problem strings (empty = consistent)."""
    problems = []
    if sentiment == 'hostile' and score > -0.3:
        problems.append(f"label=hostile but score={score:.2f} (expected ≤ -0.3)")
    elif sentiment == 'cooperative' and score < 0.3:
        problems.append(f"label=cooperative but score={score:.2f} (expected ≥ +0.3)")
    elif sentiment == 'neutral' and abs(score) > 0.3:
        problems.append(f"label=neutral but score={score:.2f} (expected within ±0.3)")
    if sentiment in ('hostile', 'cooperative') and not (reasoning or '').strip():
        problems.append(f"label={sentiment} but sentiment_reasoning is empty")
    return problems

_KEY_FIGURES_PATH = os.path.join(os.path.dirname(__file__), 'key_figures.json')
try:
    with open(_KEY_FIGURES_PATH, encoding='utf-8') as _kf:
        _KEY_FIGURES_LIST = json.load(_kf)
except Exception:
    _KEY_FIGURES_LIST = []

_OFFICIALS_PATH = os.path.join(os.path.dirname(__file__), 'current_officials.json')
try:
    with open(_OFFICIALS_PATH, encoding='utf-8') as _of:
        _OFFICIALS = json.load(_of)
except Exception:
    _OFFICIALS = {'current': [], 'former': []}

def _format_officials_block():
    lines = ['CURRENT OFFICIAL ROSTER (authoritative — override any conflicting training-data knowledge):']
    for o in _OFFICIALS.get('current', []):
        party = f", {o['party']}" if o.get('party') else ''
        lines.append(f"- {o['role']}: {o['name_en']} ({o.get('name_zh', '')}{party}, since {o.get('since', '')})")
    lines.append('\nFORMER OFFICIALS (NO LONGER in role — never describe these people as currently holding the listed role):')
    for o in _OFFICIALS.get('former', []):
        party = f", {o['party']}" if o.get('party') else ''
        lines.append(f"- {o['role']}: {o['name_en']} ({o.get('name_zh', '')}{party}, served {o.get('term', '')})")
    return '\n'.join(lines)

_OFFICIALS_BLOCK = _format_officials_block()

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

_GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if not _GEMINI_API_KEY:
    raise RuntimeError(
        "GEMINI_API_KEY environment variable is not set. "
        "Add it to .env in the project root (see CLAUDE.md > Environment)."
    )
client = genai.Client(api_key=_GEMINI_API_KEY)

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
  "sentiment_reasoning": "ONE sentence: who is characterised how, toward whom across the strait, and quote the specific phrase that triggered the score. Empty string if sentiment is neutral with no explicit cross-strait framing.",
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
  "military_exercises": [
    {
      "name_zh": "exercise name in original language, e.g. '聯合劍2024B', or null if unnamed",
      "name_en": "exercise name in English, e.g. 'Joint Sword 2024B', or null if unnamed",
      "performer_side": "one of: PRC, ROC, US, JP, MULTI",
      "participants": ["ISO-side codes — only when performer_side is MULTI, e.g. ['US','JP','ROC']"],
      "exercise_kind": "one of: live_fire, readiness_drill, joint_patrol, named_exercise, cyber, amphibious, other",
      "start_date": "YYYY-MM-DD or null if uncertain",
      "end_date": "YYYY-MM-DD or null if single-day / ongoing / uncertain",
      "location_label": "human-readable location, e.g. 'Eastern Taiwan, ~50nm offshore' or 'Hualien airbase'",
      "latitude": "decimal degrees, null unless you can resolve a named base / named waters with established centroid / coordinates explicit in text",
      "longitude": "decimal degrees, same rule",
      "description_en": "MUST be in English — 1-2 sentence summary of what was reported",
      "description_zh": "verbatim snippet from the article in original language",
      "confidence": 0.85
    }
  ],
  "confidence": 0.8
}

CLASSIFICATION RULES:
- sentiment_score measures cross-strait sentiment — how positively or negatively the article frames the opposing side or the overall relationship. Score from -1.0 (strongly hostile) to +1.0 (strongly cooperative).
- For PRC sources: how does the article portray Taiwan, Taiwanese actors, or cross-strait relations?
- For Taiwan sources: how does the article portray the PRC, mainland actors, or cross-strait relations?
- For international/SG sources: what is the overall tone toward cross-strait dynamics?
- CRITICAL — third-party interactions are NOT cross-strait signals (both directions): Taiwan's interactions with any third party (US, Japan, EU, Australia, Czech Republic, UK, allies, etc.) — whether cooperative (visits, arms sales, joint exercises, parliamentary resolutions of support, official meetings) or hostile (third-party criticism of Taiwan) — are not cross-strait sentiment signals. Likewise, PRC interactions with third parties are not cross-strait sentiment signals unless Taiwan is directly framed in the article. Score sentiment ONLY by how the article frames the opposing side of the strait, never by how either side relates to a third country. An Australian MP visiting Taipei is neutral on the cross-strait axis unless the article explicitly characterises the PRC's reaction or framing.
- CRITICAL — intra-society political conflict is NOT cross-strait hostility: Inter-party criticism within Taiwan (DPP vs KMT vs TPP) or factional/political conflict within the PRC belongs to POL_DOMESTIC_TW or POL_DOMESTIC_PRC and scores NEUTRAL on the cross-strait sentiment axis. A KMT politician attacking the DPP, or DPP figures criticising the KMT, is not cross-strait hostile — the dispute is internal. Only score hostile if the article shows one party explicitly characterising the OPPOSING SIDE OF THE STRAIT (not a domestic rival) in confrontational terms.
- CRITICAL — anti-formal-independence ≠ anti-Taiwan / pro-PRC: A Taiwanese politician (KMT, TPP, or other) opposing formal Taiwan independence is expressing a mainstream within-Taiwan position — by itself this is NEUTRAL on the cross-strait axis. Score based solely on how the politician characterises the PRC in the article: silent or factual about PRC → neutral; positive about mainland engagement → cooperative; criticising the PRC → hostile. The asymmetry is deliberate: when the PRC (officials, state media, MFA, TAO) uses anti-independence language (e.g. "Taiwan independence is a dead end", "separatist forces"), this IS hostile — the PRC is asserting sovereignty framing over Taiwan's right to choose. Anti-independence rhetoric from a Taiwanese voice is a domestic position; the same rhetoric from a PRC voice is a cross-strait assertion.
- DECISION CHECKLIST — before assigning a non-neutral sentiment, answer in order: (1) Who specifically in the article is being characterised hostilely or cooperatively? Name them. (2) Is that target the opposing side of the strait — a PRC actor in a Taiwan-source article, or a Taiwan actor in a PRC-source article? If no, score neutral. (3) Can you quote the specific sentence that frames the opposing side? If no, score neutral. (4) If the article is about a Taiwanese politician's stance on independence or unification, is there any explicit characterisation OF THE PRC in the article? If no, score neutral regardless of how strongly the politician favours or opposes independence.
- DEFAULT TO NEUTRAL when the cross-strait framing is not explicit: If you cannot point to a specific sentence in the article that explicitly frames the opposing side of the strait (PRC framing Taiwan, or Taiwan framing PRC) in positive or negative terms, default to `neutral` with a `sentiment_score` between -0.2 and +0.2. Reserve hostile or cooperative scores for articles where one side is clearly characterising or acting toward the other across the strait. When in doubt, choose neutral — false neutrals are preferred over false directional scores.
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
- MILITARY EXERCISES: Extract any military exercise mentioned in the article — both named exercises (Joint Sword 聯合劍, Han Kuang 漢光, Keen Sword, Talisman Sabre, RIMPAC, Strait Thunder 海峽雷霆, Wan An 萬安, etc.) AND unnamed drills explicitly described as conducting live-fire training, readiness drills, joint patrols, amphibious landings, or cyber exercises (e.g. "MND conducted a routine readiness drill in eastern waters on 22 May" qualifies even with no exercise name). Map the actor to performer_side: PLA / 解放軍 / 東部戰區 / 南部戰區 → PRC; MND / 國防部 / 國軍 / 漢光 → ROC; INDOPACOM / US Pacific Fleet / USAF / USN / USMC → US; JSDF / 海上自衛隊 / 航空自衛隊 → JP; multilateral activity involving two or more sides → MULTI with `participants` listing each ISO-style side code. LOCATION HANDLING — Two separate fields with different bars: `location_label` is REQUIRED whenever the article mentions ANY place reference for the exercise — a named base, range, harbour, county, body of water, region, or compass-quadrant description ("eastern Taiwan waters", "Bashi Channel", "Kaohsiung offshore", "砲測中心北岸陣地 / artillery testing centre north-bank position", "Jiupeng base 九鵬基地", "Kinmen", "Hualien airbase", "near Senkaku"). Translate Chinese place names to English in `location_label`; preserve the original in `description_zh`. The bar for `location_label` is LOW — if you can identify a place in the article, fill it. `latitude` and `longitude` are SEPARATE: only emit numeric coords when you can confidently resolve them from the text (named base with established centroid, named body of water, or coordinates stated explicitly) — otherwise both null. Use false-negatives-preferred discipline for lat/lng only, not for location_label. Return an empty array if no exercise is mentioned. description_en MUST be English (translate if needed); never put Chinese characters in description_en. If no name is given in the article, leave name_zh and name_en as null — do NOT invent a name.
- Use British English spelling in all English-language output fields (e.g. "analyse" not "analyze", "behaviour" not "behavior", "colour" not "color", "centre" not "center", "organisation" not "organization").
- CURRENT OFFICIALS: When an article references officials by role title alone (e.g. "the president", "總統", "the premier", "院長", "the foreign minister"), use the CURRENT OFFICIAL ROSTER provided below to identify who currently holds that role. If a name appears that is listed under FORMER OFFICIALS, describe them as "former [role]" — never as currently holding the role. Do not rely on training-data knowledge for current role-holders; the roster below is authoritative.
- SENTIMENT WORKED EXAMPLES (apply the same logic to all similar cases):
  - "Han Kuo-yu opposes Taiwan independence in legislative speech, calls for ROC constitutional framework" → POL_DOMESTIC_TW, sentiment=neutral, score=0.0, reasoning="" — TW politician's domestic position on independence with no characterisation of PRC.
  - "Ma Ying-jeou says 1992 Consensus is foundation for cross-strait peace, urges dialogue with Beijing" → POL_TONGDU, sentiment=cooperative, score=+0.5, reasoning="Ma Ying-jeou explicitly frames PRC engagement positively: '1992 Consensus is foundation for cross-strait peace'."
  - "MFA spokesperson: Taiwan independence is a dead end, separatist forces will face consequences" → DIP_STATEMENT, sentiment=hostile, score=-0.7, reasoning="PRC MFA characterises Taiwan's political direction in sovereignty-denying terms: 'Taiwan independence is a dead end'."
  - "DPP legislator accuses KMT chair of selling out Taiwan during mainland visit" → POL_DOMESTIC_TW, sentiment=neutral, score=0.0, reasoning="" — intra-Taiwan party conflict with no direct characterisation of PRC.
  - "Global Times editorial calls Lai Ching-te a 'troublemaker' threatening regional peace" → INFO_WARFARE, sentiment=hostile, score=-0.8, reasoning="PRC state media characterises Taiwan's president hostilely: 'troublemaker threatening regional peace'."
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
    prompt = f"""{ANALYSIS_SYSTEM_PROMPT}

{_OFFICIALS_BLOCK}{glossary_block}

SOURCE: {source_name}
LANGUAGE: {language}
TITLE: {title}

FULL TEXT:
{content[:5000]}"""

    response = client.models.generate_content(
        model="gemini-3.1-flash-lite",
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "max_output_tokens": 8000,
            "temperature": 0.1,
            "thinking_config": {"thinking_level": "medium"},
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

            sentiment_reasoning = analysis.get('sentiment_reasoning', '')

            # Insert analysis results
            conn.execute("""
                INSERT INTO ai_analysis
                (article_id, topic_primary, topic_secondary, sentiment, sentiment_score,
                 sentiment_reasoning, urgency, summary_en, key_quote, key_quote_en,
                 is_new_formulation, is_escalation_signal, escalation_note,
                 model_used, confidence)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                article['id'],
                analysis.get('topic_primary', 'HUMANITARIAN'),
                analysis.get('topic_secondary'),
                analysis.get('sentiment', 'neutral'),
                analysis.get('sentiment_score', 0.0),
                sentiment_reasoning,
                analysis.get('urgency', 'routine'),
                analysis.get('summary_en', ''),
                analysis.get('key_quote'),
                analysis.get('key_quote_en'),
                analysis.get('is_new_formulation', False),
                analysis.get('is_escalation_signal', False),
                analysis.get('escalation_note'),
                analysis.get('_model_used', 'gemini-3.1-flash-lite'),
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

            # Insert military exercises (pending analyst approval). Mirrors the
            # key_figure_statements pattern; the editorial gate is required because
            # mis-attributing performer (PRC vs ROC vs US) on a high-profile drill
            # is a credibility-ender, identical to mis-quoting a senior figure.
            _VALID_PERFORMERS = {'PRC', 'ROC', 'US', 'JP', 'MULTI'}
            _VALID_EXERCISE_KINDS = {'live_fire', 'readiness_drill', 'joint_patrol',
                                     'named_exercise', 'cyber', 'amphibious', 'other'}
            for ex in analysis.get('military_exercises', []):
                performer = (ex.get('performer_side') or '').upper().strip()
                if performer not in _VALID_PERFORMERS:
                    continue

                name_zh_raw = (ex.get('name_zh') or '').strip() or None
                name_en_raw = (ex.get('name_en') or '').strip() or None
                # Canonicalise via the same _CANONICAL_ENTITIES substring lookup
                # the entity normaliser uses — 聯合劍2024B and 联合剑2024B both
                # map to "Joint Sword 2024B".
                canonical_en = name_en_raw
                if name_zh_raw:
                    for zh, en in _CANONICAL_ENTITIES.items():
                        if len(zh) >= 2 and (zh == name_zh_raw or name_zh_raw.startswith(zh) or zh in name_zh_raw):
                            canonical_en = en
                            break
                canonical_key = _build_exercise_canonical_key(canonical_en)

                # CJK guard on description_en — drop to NULL rather than reject,
                # the row still has value for review even with no description.
                desc_en = (ex.get('description_en') or '').strip()
                if desc_en:
                    cjk_ratio = sum(1 for c in desc_en if '一' <= c <= '鿿') / len(desc_en)
                    if cjk_ratio > 0.15:
                        desc_en = None

                # Sanity-check coordinates against a generous Indo-Pacific bbox;
                # the AI sometimes invents lat/lng for vague locations. Fall back
                # to NULL so the row survives to review, just minus the marker.
                lat = ex.get('latitude')
                lng = ex.get('longitude')
                try:
                    lat = float(lat) if lat is not None else None
                    lng = float(lng) if lng is not None else None
                except (TypeError, ValueError):
                    lat, lng = None, None
                if lat is not None and not (8.0 <= lat <= 35.0):
                    lat = None
                if lng is not None and not (105.0 <= lng <= 135.0):
                    lng = None
                if lat is None or lng is None:
                    lat, lng = None, None  # require both or neither

                # Curated lookup fallback: if the AI gave us a location_label
                # but no coords, try to resolve via the deterministic table.
                # Avoids hallucinated lat/lng while still populating the map.
                location_label = (ex.get('location_label') or '').strip() or None
                if lat is None and location_label:
                    lat, lng = _geocode_from_label(location_label)

                participants = ex.get('participants') if performer == 'MULTI' else None
                participants_json = (json.dumps(participants) if isinstance(participants, list)
                                     and participants else None)

                kind = (ex.get('exercise_kind') or 'other').strip()
                if kind not in _VALID_EXERCISE_KINDS:
                    kind = 'other'

                conn.execute("""
                    INSERT INTO military_exercises
                    (article_id, canonical_name, name_en, name_zh, name_raw,
                     performer, participants_json, exercise_kind,
                     start_date, end_date, location_label, latitude, longitude,
                     description_en, description_zh, confidence, approval_status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
                """, (
                    article['id'],
                    canonical_key,
                    canonical_en,
                    name_zh_raw,
                    name_en_raw or name_zh_raw,
                    performer,
                    participants_json,
                    kind,
                    ex.get('start_date'),
                    ex.get('end_date'),
                    location_label,
                    lat,
                    lng,
                    desc_en,
                    (ex.get('description_zh') or '').strip() or None,
                    ex.get('confidence', 0.7),
                ))

            conn.commit()

            # Flag low confidence or inconsistent sentiment for human review
            tier1_review_reasons = []
            if analysis.get('confidence', 1.0) < 0.7:
                tier1_review_reasons.append(f"Low confidence: {analysis.get('confidence', 0):.2f}")
            sentiment_problems = _validate_sentiment(
                analysis.get('sentiment', 'neutral'),
                analysis.get('sentiment_score', 0.0),
                sentiment_reasoning,
            )
            tier1_review_reasons.extend(sentiment_problems)
            if tier1_review_reasons:
                conn.execute("""
                    UPDATE ai_analysis SET needs_human_review = 1, review_reason = ?
                    WHERE article_id = ?
                """, (' | '.join(tier1_review_reasons), article['id']))
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
                        contents=f"""{ANALYSIS_SYSTEM_PROMPT}

{_OFFICIALS_BLOCK}{escalation_glossary}

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
                    analysis['sentiment_reasoning'] = review_analysis.get('sentiment_reasoning', analysis.get('sentiment_reasoning', ''))
                    analysis['is_escalation_signal'] = review_analysis.get('is_escalation_signal', analysis['is_escalation_signal'])
                    analysis['escalation_note'] = review_analysis.get('escalation_note', analysis.get('escalation_note'))
                    analysis['entities'] = review_analysis.get('entities', analysis.get('entities', []))

                    # Re-validate sentiment after Flash may have changed it
                    tier2_sentiment_problems = _validate_sentiment(
                        analysis['sentiment'],
                        analysis['sentiment_score'],
                        analysis['sentiment_reasoning'],
                    )

                    # Update the database with Flash's assessment
                    conn.execute("""
                        UPDATE ai_analysis SET sentiment = ?, sentiment_score = ?,
                        sentiment_reasoning = ?, is_escalation_signal = ?,
                        escalation_note = ?, model_used = ?
                        WHERE article_id = ?
                    """, (
                        analysis['sentiment'], analysis['sentiment_score'],
                        analysis['sentiment_reasoning'],
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

                    review_reasons.extend(tier2_sentiment_problems)

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


# ============================================================
# Exercise-only extraction pass (parallel to Tier 1)
# ============================================================
# Phase 2b.2 follow-up. The keyword pre-filter rejects ROC domestic
# military training articles (e.g. YDN's "269 Brigade calibration
# firing") as not-cross-strait-relevant — correct for the main feed
# but blocks them from the exercise tracker. This pass runs a stripped-
# down exercise-only prompt against articles from a small whitelist of
# military-source feeds where Tier 1 was skipped (no ai_analysis row),
# so domestic drills flow into the analyst review queue without
# polluting the main signal feed with PR pieces.

_EXERCISE_ONLY_PROMPT = """You are extracting military exercises from a news article.
Return ONLY valid JSON of the shape:

{
  "military_exercises": [
    {
      "name_zh": "exercise name in original language, or null if unnamed",
      "name_en": "exercise name in English, or null if unnamed",
      "performer_side": "PRC | ROC | US | JP | MULTI",
      "participants": ["ISO codes — only when performer_side is MULTI"],
      "exercise_kind": "live_fire | readiness_drill | joint_patrol | named_exercise | cyber | amphibious | other",
      "start_date": "YYYY-MM-DD or null",
      "end_date": "YYYY-MM-DD or null",
      "location_label": "human-readable location (English; translate Chinese place names)",
      "latitude": "decimal degrees, null unless confidently parseable",
      "longitude": "decimal degrees, null unless confidently parseable",
      "description_en": "1-2 sentence English summary (English only)",
      "description_zh": "verbatim snippet from article",
      "confidence": 0.85
    }
  ]
}

Extract any military exercise mentioned — named (Joint Sword 聯合劍,
Han Kuang 漢光, Keen Sword, RIMPAC, Wan An 萬安) AND unnamed drills
explicitly described (live-fire / readiness / patrol / amphibious / cyber).
Map actor → performer_side: PLA/解放軍/東部戰區 → PRC; MND/國防部/國軍/漢光
→ ROC; INDOPACOM/USN/USAF → US; JSDF/海上自衛隊 → JP; two-or-more sides
→ MULTI with `participants`.

LOCATION HANDLING — `location_label` is REQUIRED whenever the article
mentions ANY place reference for the exercise: a named base, range,
harbour, county, body of water, or compass-quadrant. Translate Chinese
place names to English; preserve the original in `description_zh`. The
bar for location_label is LOW. `latitude` and `longitude` are SEPARATE:
only emit numeric coords when confidently resolvable; otherwise both
null. False-negatives-preferred applies to lat/lng only, NOT to
location_label. Beware of conflating REPORTER-location bylines (e.g.
"記者X／彰化報導") with EXERCISE location — the reporter's city is not
the drill's location unless the body explicitly says so.

description_en MUST be English. Return {"military_exercises": []} if no
exercise is mentioned. Use British spelling.
"""


def _extract_exercises_only(article):
    """Call Gemini with the exercise-only prompt. Returns the parsed list
    (possibly empty) of raw exercise dicts ready for canonicalisation and
    insertion via _insert_exercise_row."""
    glossary = generate_dynamic_glossary(
        article['content_original'] or '',
        article['title_original'] or '',
    )
    prompt = f"""{_EXERCISE_ONLY_PROMPT}

{glossary}

SOURCE: {article['source_name']}
LANGUAGE: {article['language']}
TITLE: {article['title_original']}

FULL TEXT:
{(article['content_original'] or '')[:5000]}"""

    resp = client.models.generate_content(
        model="gemini-3.1-flash-lite",
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "max_output_tokens": 4000,
            "temperature": 0.1,
            "thinking_config": {"thinking_level": "medium"},
        },
    )
    text = resp.text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        text = text.rsplit("```", 1)[0]
    try:
        return (json.loads(text) or {}).get('military_exercises', []) or []
    except json.JSONDecodeError:
        return []


def _insert_exercise_row(conn, article_id, ex):
    """Apply canonicalisation + sanity checks + geocoder fallback, then
    insert one pending row. Returns True iff a row was inserted (skips
    invalid performer_side)."""
    valid_performers = {'PRC', 'ROC', 'US', 'JP', 'MULTI'}
    valid_kinds = {'live_fire', 'readiness_drill', 'joint_patrol',
                   'named_exercise', 'cyber', 'amphibious', 'other'}
    performer = (ex.get('performer_side') or '').upper().strip()
    if performer not in valid_performers:
        return False

    name_zh_raw = (ex.get('name_zh') or '').strip() or None
    name_en_raw = (ex.get('name_en') or '').strip() or None
    canonical_en = name_en_raw
    if name_zh_raw:
        for zh, en in _CANONICAL_ENTITIES.items():
            if len(zh) >= 2 and (zh == name_zh_raw or name_zh_raw.startswith(zh) or zh in name_zh_raw):
                canonical_en = en
                break
    canonical_key = _build_exercise_canonical_key(canonical_en)

    desc_en = (ex.get('description_en') or '').strip()
    if desc_en:
        cjk_ratio = sum(1 for c in desc_en if '一' <= c <= '鿿') / len(desc_en)
        if cjk_ratio > 0.15:
            desc_en = None

    lat = ex.get('latitude')
    lng = ex.get('longitude')
    try:
        lat = float(lat) if lat is not None else None
        lng = float(lng) if lng is not None else None
    except (TypeError, ValueError):
        lat, lng = None, None
    if lat is not None and not (8.0 <= lat <= 35.0):
        lat = None
    if lng is not None and not (105.0 <= lng <= 135.0):
        lng = None
    if lat is None or lng is None:
        lat, lng = None, None

    location_label = (ex.get('location_label') or '').strip() or None
    if lat is None and location_label:
        lat, lng = _geocode_from_label(location_label)

    participants = ex.get('participants') if performer == 'MULTI' else None
    participants_json = (json.dumps(participants) if isinstance(participants, list)
                         and participants else None)

    kind = (ex.get('exercise_kind') or 'other').strip()
    if kind not in valid_kinds:
        kind = 'other'

    conn.execute("""
        INSERT INTO military_exercises
        (article_id, canonical_name, name_en, name_zh, name_raw,
         performer, participants_json, exercise_kind,
         start_date, end_date, location_label, latitude, longitude,
         description_en, description_zh, confidence, approval_status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
    """, (
        article_id, canonical_key, canonical_en, name_zh_raw,
        name_en_raw or name_zh_raw, performer, participants_json, kind,
        ex.get('start_date'), ex.get('end_date'), location_label, lat, lng,
        desc_en, (ex.get('description_zh') or '').strip() or None,
        ex.get('confidence', 0.7),
    ))
    return True


# Sources to scan in the exercise-only pass. Start narrow with YDN
# (Youth Daily News — MND's organ — almost all the ROC drill content).
# Add PLA Daily / INDOPACOM / JMOD here if coverage gaps emerge.
EXERCISE_ONLY_SOURCES = ['YDN']


def process_exercise_only_articles(source_names=None, days=14, limit=30):
    """Scan articles from the whitelisted military sources where Tier 1
    was skipped (rejected by the keyword pre-filter, no ai_analysis row),
    and run exercise-only extraction. Capped per cron tick so a busy YDN
    day can't run away. Idempotent — articles that already have any
    military_exercises row are skipped."""
    source_names = source_names or EXERCISE_ONLY_SOURCES
    placeholders = ",".join("?" * len(source_names))

    from scraper.utils.db import get_connection
    conn = get_connection()
    articles = conn.execute(f"""
        SELECT a.id, a.title_original, a.content_original, a.language,
               s.name AS source_name
        FROM articles a
        JOIN sources s ON s.id = a.source_id
        LEFT JOIN ai_analysis ai ON ai.article_id = a.id
        WHERE s.name IN ({placeholders})
          AND a.ai_processed = 1
          AND ai.id IS NULL
          AND a.published_at >= datetime('now', ?)
          AND NOT EXISTS (
              SELECT 1 FROM military_exercises me WHERE me.article_id = a.id
          )
        ORDER BY a.published_at DESC
        LIMIT ?
    """, (*source_names, f'-{days} days', limit)).fetchall()

    if not articles:
        print(f"  No candidate articles from {source_names} in the last {days} days.")
        return

    inserted = 0
    for i, article in enumerate(articles, 1):
        try:
            exercises = _extract_exercises_only(article)
        except Exception as e:
            print(f"  [{i}/{len(articles)}] article {article['id']}: extract failed — {e}")
            continue
        if not exercises:
            continue
        for ex in exercises:
            if _insert_exercise_row(conn, article['id'], ex):
                inserted += 1
        conn.commit()
        print(f"  [{i}/{len(articles)}] article {article['id']}: {len(exercises)} exercises")
    print(f"  Inserted {inserted} pending exercise candidates from {len(articles)} articles.")
    conn.close()


if __name__ == '__main__':
    process_unanalysed_articles(limit=10)