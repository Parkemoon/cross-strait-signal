import os
import re
import sys
import json
import time
from datetime import datetime, timezone
from dotenv import load_dotenv
from scraper.processors.keyword_filter import check_relevance
from scraper.utils.usage_log import log_usage


# Article body slice fed to every Gemini prompt. Must be at least as large
# as the scraper-side content cap (25_000 in the poll scrapers) so Tier 1
# and Tier 2 review the same evidence — otherwise the escalation reviewer
# can disagree with Tier 1 simply because it sees less of the article,
# which would falsely trip the human review queue.
MAX_PROMPT_CONTENT_CHARS = 25000


# Used by the exercise tracker to collapse name variants the AI produces
# for the same activity. Three layers:
#   1. "Exercise No. 42" → "42" so "Han Kuang Exercise No. 42" matches
#      "Han Kuang 42 Exercise".
#   2. Strip trailing interchangeable nouns (drill/exercise/training/
#      wargame) — applied iteratively so chains like "Exercise Wargame"
#      collapse fully.
#   3. Lowercase + hyphenate.
# Parenthesised clauses are deliberately preserved — they often carry
# subtype info (CPX vs live-fire) that the merge logic must NOT collapse.
_EXERCISE_NO_RE = re.compile(r'\bExercise\s+No\.?\s+(\d+)\b', re.IGNORECASE)
_EXERCISE_SUFFIX_RE = re.compile(
    r'(\s+(drills?|exercises?|trainings?|wargames?))+$', re.IGNORECASE
)


def _build_exercise_canonical_key(name_en: str | None) -> str | None:
    """Lower-hyphenated canonical form used for grouping and auto-merge."""
    if not name_en:
        return None
    s = _EXERCISE_NO_RE.sub(r'\1', name_en.strip())
    s = re.sub(r'\s{2,}', ' ', s)
    s = _EXERCISE_SUFFIX_RE.sub('', s).strip()
    key = s.lower().replace(' ', '-').replace('_', '-')
    return key or None


def _exercise_canonical_en(name_zh, name_en_fallback):
    """Override the AI's name_en with the dictionary's canonical English
    ONLY on exact match against the Chinese name. Previously this used
    substring matching (`zh in name_zh_raw`) which let unit names like
    '東部戰區' (Eastern Theater Command) shadow the actual exercise name
    in compound phrases like '東部戰區聯合戰備警巡', because dict
    iteration order put the unit before the exercise. Exact match avoids
    the shadowing without losing the cases that matter — the glossary
    pre-injects canonical Chinese variants into the prompt, and we seed
    both hyphenated and non-hyphenated forms in entity_canonical.json."""
    if name_zh and name_zh in _CANONICAL_ENTITIES:
        return _CANONICAL_ENTITIES[name_zh]
    return name_en_fallback

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


def _flatten_locations(entries):
    """Return a list of (lower-cased-name, lat, lng) tuples sorted by
    name length DESCENDING. Sorting once globally — not within each
    entry — ensures the matcher prefers the longest available substring,
    so 'tw-northern-waters' beats 'Taiwan strait' when the label is
    'north of Taiwan Strait'."""
    out = []
    for entry in entries:
        for name in entry.get('names', []):
            out.append((name.lower(), entry['lat'], entry['lng']))
    out.sort(key=lambda t: len(t[0]), reverse=True)
    return out


def _load_mil_locations():
    """Read both files and return the flattened, length-sorted lookup +
    the auto file's current mtime. Tolerant of FileNotFoundError AND
    JSONDecodeError on the auto file (the API writer uses an atomic
    temp+rename pattern, but if something else corrupts it we don't want
    to crash the whole scraper at import time)."""
    with open(_MIL_LOCATIONS_PATH, encoding='utf-8') as f:
        entries = json.load(f)
    try:
        with open(_MIL_LOCATIONS_AUTO_PATH, encoding='utf-8') as f:
            entries = entries + json.load(f)
        auto_mtime = os.path.getmtime(_MIL_LOCATIONS_AUTO_PATH)
    except FileNotFoundError:
        auto_mtime = 0.0
    except (json.JSONDecodeError, ValueError) as e:
        print(f"[ai_pipeline] military_locations_auto.json unreadable, skipping: {e}")
        auto_mtime = 0.0
    return _flatten_locations(entries), auto_mtime


_MIL_LOCATIONS_FLAT, _MIL_LOCATIONS_AUTO_MTIME = _load_mil_locations()


def _refresh_locations_if_stale():
    """Reload the lookup if the auto file has been touched since our
    last read — so analyst PATCHes during a long-running scraper or
    uvicorn process become visible to subsequent _geocode_from_label
    calls without needing a process restart."""
    global _MIL_LOCATIONS_FLAT, _MIL_LOCATIONS_AUTO_MTIME
    try:
        mtime = os.path.getmtime(_MIL_LOCATIONS_AUTO_PATH)
    except FileNotFoundError:
        return
    if mtime > _MIL_LOCATIONS_AUTO_MTIME:
        _MIL_LOCATIONS_FLAT, _MIL_LOCATIONS_AUTO_MTIME = _load_mil_locations()


def _geocode_from_label(label):
    """Curated case-insensitive substring lookup. Returns (lat, lng) or
    (None, None) when no entry matches. Iterates names sorted by length
    DESCENDING so 'tw-northern-waters' beats 'Taiwan strait' when both
    could match — fixes the order-dependence bug. Re-reads the auto
    file if it's been updated since our cached snapshot."""
    if not label:
        return None, None
    _refresh_locations_if_stale()
    needle = label.lower()
    for name, lat, lng in _MIL_LOCATIONS_FLAT:
        if name in needle:
            return lat, lng
    return None, None


# ── Diplomacy Tracker (Phase 2c) ─────────────────────────────────────────
# Third-country stance on Taiwan / cross-strait. A SEPARATE axis from the
# core sentiment instrument — the main prompt deliberately discards
# third-party interactions ("third-party interactions are NOT cross-strait
# signals"); this captures exactly that discarded signal. See
# diplomacy_statements in db/schema.sql.
_COUNTRY_ISO_PATH = os.path.join(os.path.dirname(__file__), 'country_iso.json')
try:
    with open(_COUNTRY_ISO_PATH, encoding='utf-8') as _cf:
        _COUNTRY_LOOKUP = json.load(_cf)
except Exception as _e:
    print(f"[ai_pipeline] country_iso.json unreadable, diplomacy extraction disabled: {_e}")
    _COUNTRY_LOOKUP = {"exclude_iso": [], "iso_to_name": {}, "alias_to_iso": {}}

_VALID_AUTHORITY_TIERS = {
    'government', 'head_of_state', 'ruling_party', 'legislator',
    'subnational', 'former_official', 'other',
}
_ISO2_RE = re.compile(r'^[A-Z]{2}$')

# International organisations / alliances the model sometimes emits as if they
# were countries (ICAO under an invented 'UN' code, UN agencies, NATO, …).
# This axis is third-COUNTRY stance, so orgs are dropped — the ONE deliberate
# exception is the EU, tracked as a bloc via the 'EU' roster code. Matched on
# the emitted name; a code denylist (exclude_iso, e.g. 'UN') is the backstop
# for rows that carry an org code but no telltale name.
_ORG_NAME_RE = re.compile(
    r'(organi[sz]ation|united nations|civil aviation|world health|'
    r'world trade|world bank|monetary fund|criminal court|interpol|'
    r'\b(ICAO|UNESCO|UNICEF|UNFCCC|WHO|WTO|WHA|IMF|NATO|ASEAN|OECD|OPEC)\b)',
    re.IGNORECASE,
)
_EU_ALLOW_RE = re.compile(r'european union|\bEU\b', re.IGNORECASE)


def _looks_like_org(name):
    """True if the emitted entity name reads as an international organisation
    or alliance (not a state). The EU is exempt — we track it as a bloc."""
    if not name:
        return False
    if _EU_ALLOW_RE.search(name):
        return False
    return bool(_ORG_NAME_RE.search(name))


def _resolve_country_iso(name, iso):
    """Map an AI-emitted (country name, ISO code) pair to a canonical
    (ISO2, display_name). Trusts a valid 2-letter ISO first (accepting
    plausible codes outside our curated roster so long-tail countries still
    reach the review queue), then falls back to alias lookup on the name.
    Returns (None, None) for the excluded cross-strait principals
    (CN/TW/HK/MO), international organisations (orgs aren't states — EU bloc
    excepted), or when nothing resolves."""
    iso_to_name = _COUNTRY_LOOKUP.get('iso_to_name', {})
    alias_to_iso = _COUNTRY_LOOKUP.get('alias_to_iso', {})
    exclude = set(_COUNTRY_LOOKUP.get('exclude_iso', []))

    # Drop international orgs before anything else — they otherwise sail
    # through the "plausible 2-letter code" acceptance below.
    if _looks_like_org(name):
        return None, None

    code = (str(iso).strip().upper() if iso else '')
    if code:
        if code in exclude:
            return None, None
        if code in iso_to_name:
            return code, iso_to_name[code]
        if _ISO2_RE.match(code):
            return code, (name or code).strip()

    if name:
        for key in (name.strip().lower(), name.strip()):
            if key in alias_to_iso:
                resolved = alias_to_iso[key]
                if resolved in exclude:
                    return None, None
                return resolved, iso_to_name.get(resolved, name.strip())
    return None, None


def _stance_label(stance):
    """Bucket a -1..+1 stance into the five map-fill bands. Mirrored in
    api/routes/diplomacy.py (_STANCE_BANDS) — keep the thresholds in sync."""
    if stance >= 0.6:
        return 'pro_taipei'
    if stance >= 0.2:
        return 'leaning_taipei'
    if stance > -0.2:
        return 'neutral'
    if stance > -0.6:
        return 'leaning_beijing'
    return 'pro_beijing'


def _source_side_from_place(place):
    """Reporting side for the deferred TW-lens/PRC-lens split. Best-effort
    from sources.place: TW → 'TW'; PRC/HK/MO → 'PRC' (HK media post-NSL is
    state-aligned for this purpose); everything else → 'INTL'."""
    p = (place or '').strip().upper()
    if p == 'TW':
        return 'TW'
    if p in ('PRC', 'CN', 'HK', 'MO'):
        return 'PRC'
    return 'INTL'


def _insert_diplomacy_row(conn, article_id, stmt, source_place=None):
    """Validate + insert one pending diplomacy_statements row. Returns True
    iff inserted. Drops rows that don't resolve to a third country or carry
    no numeric stance. Shared by the main Tier 1 loop and the backfill."""
    iso, country_name = _resolve_country_iso(stmt.get('country'), stmt.get('country_iso'))
    if not iso:
        return False

    try:
        stance = float(stmt.get('stance'))
    except (TypeError, ValueError):
        return False  # stance is the whole point — drop if missing/non-numeric
    stance = max(-1.0, min(1.0, stance))

    tier = (stmt.get('authority_tier') or 'other').strip().lower()
    if tier not in _VALID_AUTHORITY_TIERS:
        tier = 'other'

    # CJK guard on statement_en — drop to NULL rather than reject the row.
    stmt_en = (stmt.get('statement_en') or '').strip()
    if stmt_en:
        cjk_ratio = sum(1 for c in stmt_en if '一' <= c <= '鿿') / len(stmt_en)
        if cjk_ratio > 0.15:
            stmt_en = None

    stated_date = (stmt.get('stated_date') or '').strip() or None
    if stated_date and not re.match(r'^\d{4}-\d{2}-\d{2}$', stated_date):
        stated_date = None

    conn.execute("""
        INSERT INTO diplomacy_statements
        (article_id, country_iso, country_name, speaker, authority_tier,
         stance, stance_label, statement_en, statement_zh, stated_date,
         source_side, confidence, approval_status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
    """, (
        article_id, iso, country_name,
        (stmt.get('speaker') or '').strip() or None,
        tier, stance, _stance_label(stance),
        stmt_en,
        (stmt.get('statement_zh') or '').strip() or None,
        stated_date,
        _source_side_from_place(source_place),
        stmt.get('confidence', 0.7),
    ))
    return True


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

    # Tier 1: exact match wins outright, before the prefix tiers — otherwise an
    # earlier, longer key shadows it (bare 解放軍 would match 解放軍海軍 via the
    # prefix tiers and resolve to "PLAN" instead of "PLA").
    if len(zh_name) >= 2 and zh_name in _CANONICAL_ENTITIES:
        entity['name_en'] = _CANONICAL_ENTITIES[zh_name]
        return entity

    # Tiers 2-3: prefix relationships — the extracted name is a longer form of a
    # canonical key, or the AI returned a shorter form than the canonical key.
    for zh, en in _CANONICAL_ENTITIES.items():
        if len(zh) < 2:
            continue
        if zh_name.startswith(zh) or zh.startswith(zh_name):
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
    # The model can emit an explicit `"sentiment_score": null`; get(..., 0.0)
    # returns None (not the default) for a present-but-null key, and the
    # comparisons below would then raise TypeError. Treat null as 0.0 (neutral).
    if score is None:
        score = 0.0
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

def _format_officials_current_block():
    """Static roster of CURRENT office-holders. Injected into every prompt and
    kept small (~29 entries) and stable so it stays inside the implicitly
    cached prompt prefix."""
    lines = ['CURRENT OFFICIAL ROSTER (authoritative — override any conflicting training-data knowledge):']
    for o in _OFFICIALS.get('current', []):
        party = f", {o['party']}" if o.get('party') else ''
        lines.append(f"- {o['role']}: {o['name_en']} ({o.get('name_zh', '')}{party}, since {o.get('since', '')})")
    return '\n'.join(lines)


_OFFICIALS_CURRENT_BLOCK = _format_officials_current_block()


def _officials_former_block(content, title=""):
    """Only the FORMER officials actually named in the article. The full former
    roster is ~99 entries (~11k chars) and is almost never relevant to a given
    article, so — exactly like generate_dynamic_glossary — we filter by presence
    in the text instead of shipping the whole list on every Gemini call.
    Returns '' when no former official is mentioned (the common case)."""
    haystack = f"{content or ''}\n{title or ''}"
    matched = []
    for o in _OFFICIALS.get('former', []):
        name_zh = o.get('name_zh', '')
        name_en = o.get('name_en', '')
        if (name_zh and name_zh in haystack) or (name_en and name_en in haystack):
            party = f", {o['party']}" if o.get('party') else ''
            matched.append(f"- {o['role']}: {name_en} ({name_zh}{party}, served {o.get('term', '')})")
    if not matched:
        return ""
    return ('\n\nFORMER OFFICIALS named in this article (NO LONGER in role — never '
            'describe these people as currently holding the listed role):\n'
            + '\n'.join(matched))

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
  "polls": [
    {
      "pollster_hint": "name of the polling organisation EXACTLY as it appears in the article — Chinese or English, e.g. '美麗島電子報', 'TVBS民調中心', 'NCCU Election Study Center'. Null if the article does not name the pollster.",
      "fielded_start": "YYYY-MM-DD — first day of fieldwork",
      "fielded_end": "YYYY-MM-DD or null if single-day fielding",
      "sample_size": 1071,
      "methodology_note": "1-line method summary if stated (CATI, online panel, age range, dual-frame, etc.), else null",
      "questions": [
        {
          "question_text_zh": "exact question wording from the article in original language — DO NOT paraphrase",
          "question_text_en": "English translation of the question",
          "family_hint": "one of: identity, unification, approval, attitude, vote_intent, issue",
          "options": [
            {
              "label_zh": "option label in original language, e.g. '滿意' or '台灣人'",
              "label_en": "English label, e.g. 'Satisfied' or 'Taiwanese'",
              "percentage": 47.3
            }
          ]
        }
      ],
      "confidence": 0.85
    }
  ],
  "diplomacy_statements": [
    {
      "country": "English name of the THIRD country whose stance is expressed, e.g. 'Czech Republic', 'United States', 'Japan'. NEVER China/PRC or Taiwan/ROC.",
      "country_iso": "ISO 3166-1 alpha-2 code, uppercase, e.g. 'CZ', 'US', 'JP'. Use 'EU' for the European Union as a bloc.",
      "speaker": "person or body making the statement, e.g. 'President Petr Pavel', 'Senate foreign affairs committee', 'MOFA spokesperson'",
      "authority_tier": "one of: government, head_of_state, ruling_party, legislator, subnational, former_official, other",
      "stance": 0.0,
      "statement_en": "MUST be English — what the country/speaker said or did regarding Taiwan / cross-strait / the one-China question",
      "statement_zh": "verbatim original-language snippet, or null if the article is in English",
      "stated_date": "YYYY-MM-DD or null",
      "confidence": 0.8
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
- MIL_POLICY = defence doctrine, budgets, force structure, conscription, arms-sale approvals (the policy decision, not the hardware), white papers, MND posture statements. Use MIL_HARDWARE when a specific weapon/platform is the subject; DIP_STATEMENT for MFA/TAO diplomatic pronouncements (MIL_POLICY is defence-ministry/military institutional policy).
- TRANSPORT = cross-strait flights, shipping, ferry links, port closures, aviation routes, Kinmen-Xiamen connectivity. Not HUMANITARIAN for transport disruptions.
- INT_ORG = Taiwan's participation in / exclusion from international organisations (UN, WHO, ICAO, Interpol, etc.) and PRC efforts to block it; also PRC nationals leading IOs where cross-strait-relevant.
- POL_DOMESTIC_TW / POL_DOMESTIC_PRC = domestic politics with a cross-strait dimension (defence-budget debates, party positioning on cross-strait policy, NPC decisions affecting Taiwan, CCP leadership signalling). Classify by the article's SUBJECT, not the source — a PRC outlet on Taiwan domestic politics is POL_DOMESTIC_TW.
- DIP_VISIT = official state/government visits only (heads of state, ministers, official delegations). PARTY_VISIT = party-to-party (KMT-CCP forums, opposition delegations to the mainland, CCP officials meeting TW party figures). A KMT chair in Beijing is always PARTY_VISIT, never DIP_VISIT.
- US_PRC = US-China relations as the primary subject (diplomacy, Washington-Beijing trade/tech sanctions, Pacific deterrence) — NOT Taiwan's relationship with the US.
- US_TAIWAN = US-Taiwan relations (support, trade ties, congressional legislation, official visits, statements on Taiwan's status). Use ARMS_SALES for the specific transfer event.
- HK_MAC = Hong Kong / Macau with cross-strait relevance (Beijing's HK governance, "one country, two systems" credibility, HK as model/warning for Taiwan).
- CULTURE = cross-strait cultural exchange and soft power (artists/films/media, festivals, heritage framing, people-to-people ties). Use POL_TONGDU when the framing is explicitly about sovereignty or national identity.
- CYBER = cyber operations, hacking, digital espionage, infrastructure intrusions. Distinct from INFO_WARFARE (narrative/propaganda) — CYBER is technical intrusion/sabotage.
- ARMS_SALES = arms transfer events and export-control decisions (US arms packages, weapons-system sales, defence-tech export controls). Use MIL_POLICY for broader defence posture.
- SPORT = sport with cross-strait political dimensions (Olympic "Chinese Taipei" naming, boycotts, sport as soft power/signal).
- SCI_TECH = civilian/dual-use technology (semiconductors, chip/tech export controls, space, AI, scientific exchange, tech talent flows). Use ECON_TRADE for broad trade sanctions, CYBER for intrusion operations, ARMS_SALES for defence hardware.
- ENERGY = energy security with cross-strait relevance (imports, nuclear policy, LNG, infrastructure vulnerability, PRC energy leverage, shipping-lane economics).
- Only flag is_escalation_signal for genuinely significant developments, not routine rhetoric
- urgency: flash = breaking/status quo change, priority = notable, routine = standard coverage
- Extract ALL named entities: people, military units, ships, aircraft, locations, organisations
- All strings in the JSON must have special characters properly escaped.
- Unification/independence spectrum (統獨): reunification rhetoric, independence moves, sovereignty claims, constitutional norm changes, status quo shifts from either side
- For ALL Taiwanese entities (people, organisations, places), use Wade-Giles or Tongyong Pinyin. If a person has a known English name or self-used romanisation, prefer that. Do not use Hanyu Pinyin for Taiwanese entities. For ALL PRC entities, use Hanyu Pinyin. Never leave a Chinese name untranslated in an English field — if you cannot find an established romanisation, apply the appropriate system (Wade-Giles for TW, Hanyu Pinyin for PRC) and romanise it yourself. If a CRITICAL TERMINOLOGY MAPPING block is provided, you are strictly forbidden from deviating from its translations.
- KEY FIGURE STATEMENTS: Extract attributed statements only when speaker attribution is UNAMBIGUOUS in the article text. Focus on senior PRC and Taiwan officials (presidents, premiers, party chairs, ministers, official spokespersons, TAO/MAC heads). For 'quote': must be a direct statement BY this speaker — not a description of them, not a paraphrase, not a quote about them. For 'action': only major concrete acts — visits, meetings, signings, orders; NOT background references such as "Xi has previously said…" or passive mentions. If attribution is uncertain in any way, omit entirely. False negatives are strongly preferred over false positives. Return an empty array if no clearly attributed statements exist. CRITICAL: statement_text MUST always be written in English — if the article is in Chinese, translate the quote or action description into English before placing it in statement_text. Never put Chinese characters in statement_text.
- MILITARY EXERCISES: Extract any military exercise mentioned in the article — both named exercises (Joint Sword 聯合劍, Han Kuang 漢光, Keen Sword, Talisman Sabre, RIMPAC, Strait Thunder 海峽雷霆, Wan An 萬安, etc.) AND unnamed drills explicitly described as conducting live-fire training, readiness drills, joint patrols, amphibious landings, or cyber exercises (e.g. "MND conducted a routine readiness drill in eastern waters on 22 May" qualifies even with no exercise name). Map the actor to performer_side: PLA / 解放軍 / 東部戰區 / 南部戰區 → PRC; MND / 國防部 / 國軍 / 漢光 → ROC; INDOPACOM / US Pacific Fleet / USAF / USN / USMC → US; JSDF / 海上自衛隊 / 航空自衛隊 → JP; multilateral activity involving two or more sides → MULTI with `participants` listing each ISO-style side code. DATE ANCHORING — `start_date` and `end_date` default to the article's PUBLISHED year (given above). When the article says "today", "this week", "on 22 May", or any month/day without a year, use the PUBLISHED year. Only use a different year when the article explicitly cites one (e.g. "the 2024 drill", "Han Kuang 41 last year", "the original 2022 exercise"). Do NOT anchor dates to your training-data baseline — the PUBLISHED date is authoritative for the article's "now". LOCATION HANDLING — Two separate fields with different bars: `location_label` is REQUIRED whenever the article mentions ANY place reference for the exercise — a named base, range, harbour, county, body of water, region, or compass-quadrant description ("eastern Taiwan waters", "Bashi Channel", "Kaohsiung offshore", "砲測中心北岸陣地 / artillery testing centre north-bank position", "Jiupeng base 九鵬基地", "Kinmen", "Hualien airbase", "near Senkaku"). Translate Chinese place names to English in `location_label`; preserve the original in `description_zh`. The bar for `location_label` is LOW — if you can identify a place in the article, fill it. `latitude` and `longitude` are SEPARATE: only emit numeric coords when you can confidently resolve them from the text (named base with established centroid, named body of water, or coordinates stated explicitly) — otherwise both null. Use false-negatives-preferred discipline for lat/lng only, not for location_label. Return an empty array if no exercise is mentioned. description_en MUST be English (translate if needed); never put Chinese characters in description_en. If no name is given in the article, leave name_zh and name_en as null — do NOT invent a name.
- POLLS: Extract public-opinion polls of the Taiwanese (or PRC) public on TW political, cross-strait, identity, unification, political-approval, attitude, or vote-intention questions. PRIMARY SUBJECT bar — only extract when the article is REPORTING ON a poll's results, not when it merely cites a poll number in passing to back a wider argument. Skip polls of any other public (Israeli, US, Japanese, etc.) even when a TW outlet covers them. The four-signal gate is POLL-LEVEL not question-level: a poll qualifies when the ARTICLE AS A WHOLE names the pollster, gives a fieldwork date range, gives a sample size, and reports at least one numeric percentage attached to a question option. Once the poll qualifies, you MUST extract every distinct question reported in it — not just the headline one. A single article often carries 2–5 questions from one wave (vote intent + approval + favourability + policy ratings); emit them all into the SAME poll's `questions[]` array, sharing the pollster/sample/fielding properties. False negatives at the poll level (whole poll skipped) are preferred over false positives, but false negatives at the question level (cherry-picking from a qualifying poll) are NOT preferred — be exhaustive. Skip subgroup cross-tabulations (e.g. "among 20-29 year olds X% supported Y", "DPP-identifiers split Z%/W%") and demographic breakdowns of an already-extracted main result. SKIP: hypothetical surveys, forecasts/projections, expert-panel surveys, internal party-member polls, candidate-primary selection polls (初選民調 — parties using polls to pick nominees is a process mechanism, not public opinion), single-line passing references to past poll numbers ("a 2022 poll showed..."), and PRC state-media "surveys" with no methodology disclosed. POLLSTER — copy the organisation name VERBATIM from the article into `pollster_hint`; if the article references the poll without naming the pollster, set `pollster_hint` to null. The downstream pipeline resolves the hint to a canonical pollster; do not normalise or translate it yourself. DATE ANCHORING — same rule as exercises: `fielded_start`/`fielded_end` default to the article's PUBLISHED year; only use a different year if the article explicitly states one. QUESTION TEXT — `question_text_zh` should be the verbatim wording from the article when the article quotes the question directly. When the article reports results in prose without quoting the question (common in headlines: "X leads Y 43% to 37%" without a stated question), you MAY synthesise `question_text_zh` from the prose context (e.g. "2026年嘉義市長選舉支持哪位參選人？"). `question_text_en` must be English. OPTIONS — one entry per labelled response in the article (e.g. for an approval poll: 'Satisfied', 'Dissatisfied', 'No opinion'). `label_zh` is the article's original-language label; `label_en` is its English equivalent. `percentage` is the numeric value as a float (47.3, not 0.473 or "47.3%"). Do NOT compute or impute percentages — only extract values explicitly stated. If options sum to less than 100 (because the article omitted "no opinion" or "other"), that is fine — do not fabricate the missing rows. family_hint is your best guess at the question's category and is used as a starting suggestion in the analyst review queue, not as a binding classification. Return an empty array if no poll meeting the bar is reported.
- DIPLOMACY STATEMENTS: Extract statements or actions by THIRD COUNTRIES (any country other than China/PRC and Taiwan/ROC) that express a position on Taiwan, cross-strait relations, the Taiwan Strait, or the one-China question. This is a SEPARATE axis from cross-strait sentiment — capture the third country's stance ON THE TAIWAN QUESTION, NOT how it relates to either side bilaterally, and NOT the cross-strait sentiment_score. EXCLUDE statements by China/PRC or Taiwan/ROC themselves (those are the cross-strait axis, handled by sentiment). SCOPE GATE (apply FIRST, before scoring): only extract when the statement expresses an EXPLICIT position on Taiwan, the Taiwan Strait, cross-strait relations, or the one-China question. If it is about PRC domestic human-rights policy (Xinjiang/Uyghurs/Tibet), WWII history or anti-militarism, general freedom of navigation, semiconductor/AI supply chains, or routine bilateral/administrative matters with NO explicit Taiwan reference, DO NOT extract it — a loose anti-PRC or pro-PRC sentiment with no Taiwan nexus is NOT a Taiwan stance; when in doubt whether Taiwan is the actual subject, extract nothing. STANCE (-1.0 .. +1.0), pro-Beijing ↔ pro-Taipei: SIGN IS DIRECTION, NOT TONE — the sign encodes which side of the strait the speaker favours, never emotional tone: condemning/criticising Beijing (e.g. over its coercion of Taiwan) is POSITIVE (pro-Taipei), endorsing reunification is NEGATIVE (pro-Beijing); do not let harsh language about China push the score negative. +0.6..+1.0 (pro-Taipei) = explicit support — recognises/upgrades ties, backs Taiwan's international participation, official visit/delegation framed as solidarity, condemns PRC coercion of Taiwan, supplies arms with supportive framing; +0.2..+0.5 (leaning Taipei) = an explicit pro-Taiwan element is present — concern over PRC/Beijing pressure or coercion, a call for Taiwan's meaningful international participation, OR opposition to changing the status quo specifically "by force" or "by coercion" (these name the PRC as the threat); -0.2..+0.2 (neutral — the DEFAULT for diplomatic boilerplate) = a bare "peace and stability in the Taiwan Strait", "peaceful resolution", "cross-strait dialogue", or "oppose unilateral change to the status quo" with NO naming of Beijing's pressure and NO support for Taiwan's participation scores NEUTRAL (~0.0, within ±0.15), NOT leaning Taipei — most diplomatic readouts are exactly this; only move up to leaning Taipei when an anti-coercion / anti-force / pro-participation / pro-Taiwan element is explicitly present; -0.5..-0.2 (leaning Beijing) = routine reaffirmation of a one-China policy, "respects China's position", acknowledges PRC concerns without endorsing reunification; -1.0..-0.6 (pro-Beijing) = endorses reunification / "Taiwan is part of China", explicitly opposes Taiwan independence, supports PRC sovereignty claims, condemns Taiwan or foreign "interference". AUTHORITY TIER — classify from the title/role stated in the article text: national executive or foreign ministry → government; president/PM/monarch personally → head_of_state; the ruling party acting as a party → ruling_party; MPs/senators/parliamentary groups/committees → legislator; mayors/governors/states/provinces → subnational; ex-officials or retired figures → former_official; academics/NGOs/business/anything else → other. The SAME article can carry MULTIPLE statements from one country at different tiers (e.g. a government one-China line PLUS a supportive parliamentary delegation) — emit each as a SEPARATE object; that divergence is the point. country = English name; country_iso = ISO 3166-1 alpha-2 uppercase ('EU' for the European Union). DATE ANCHORING — same rule as exercises: stated_date defaults to the article's PUBLISHED year for any partial date. statement_en MUST be English (translate if needed); never put Chinese characters in statement_en. WORKED EXAMPLES: (a) 'US lawmaker calls the PRC ethnic-unity law dystopian, says it will harass Uyghurs/Tibetans' → no Taiwan nexus → extract NOTHING; (b) 'Senator condemns Beijing's military coercion of Taiwan' → +0.7 pro-Taipei (the condemnation targets Beijing, so the sign stays POSITIVE); (c) 'Foreign ministry reaffirms its one-China policy' with no pressure named → −0.3 leaning Beijing; (d) 'We support peace and stability in the Taiwan Strait' and nothing more → ~0.0 neutral. Return an empty array if no third-country stance on Taiwan/cross-strait is expressed.
- Use British English spelling in all English-language output fields (e.g. "analyse" not "analyze", "behaviour" not "behavior", "colour" not "color", "centre" not "center", "organisation" not "organization").
- CURRENT OFFICIALS: When an article references officials by role title alone (e.g. "the president", "總統", "the premier", "院長", "the foreign minister"), use the CURRENT OFFICIAL ROSTER provided below to identify who currently holds that role. If a name appears that is listed under FORMER OFFICIALS, describe them as "former [role]" — never as currently holding the role. Do not rely on training-data knowledge for current role-holders; the roster below is authoritative.
- SENTIMENT WORKED EXAMPLES (apply the same logic to all similar cases):
  - "Han Kuo-yu opposes Taiwan independence in legislative speech, calls for ROC constitutional framework" → POL_DOMESTIC_TW, sentiment=neutral, score=0.0, reasoning="" — TW politician's domestic position on independence with no characterisation of PRC.
  - "Ma Ying-jeou says 1992 Consensus is foundation for cross-strait peace, urges dialogue with Beijing" → POL_TONGDU, sentiment=cooperative, score=+0.5, reasoning="Ma Ying-jeou explicitly frames PRC engagement positively: '1992 Consensus is foundation for cross-strait peace'."
  - "MFA spokesperson: Taiwan independence is a dead end, separatist forces will face consequences" → DIP_STATEMENT, sentiment=hostile, score=-0.7, reasoning="PRC MFA characterises Taiwan's political direction in sovereignty-denying terms: 'Taiwan independence is a dead end'."
  - "DPP legislator accuses KMT chair of selling out Taiwan during mainland visit" → POL_DOMESTIC_TW, sentiment=neutral, score=0.0, reasoning="" — intra-Taiwan party conflict with no direct characterisation of PRC.
  - "Global Times editorial calls Lai Ching-te a 'troublemaker' threatening regional peace" → INFO_WARFARE, sentiment=hostile, score=-0.8, reasoning="PRC state media characterises Taiwan's president hostilely: 'troublemaker threatening regional peace'."
- Return ONLY valid JSON. No markdown code blocks, no commentary, no text before or after the JSON."""


# Appended to the Tier-2 escalation-review prompt. The reviewer only needs to
# second-guess the sentiment / escalation / topic judgement, so we tell it to
# skip the expensive extraction arrays — this cuts most of the review call's
# output tokens without touching the (shared) scoring rules above, so Tier 1 and
# Tier 2 still judge sentiment by identical rules.
_ESCALATION_REVIEW_DIRECTIVE = (
    "REVIEW MODE — you are re-judging an earlier analysis of THIS article. "
    "Populate ONLY these fields: is_cross_strait_primary, topic_primary, "
    "sentiment, sentiment_score, sentiment_reasoning, urgency, "
    "is_escalation_signal, escalation_note, confidence. Return empty arrays for "
    "entities, keywords_matched, key_figure_statements, military_exercises, "
    "polls, and diplomacy_statements — they are not needed for this review."
)


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


_POLL_DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')


def _load_pollster_lookup(conn):
    """Build a lowercased {slug | name_zh | name_en → pollster_id} dict.
    Used to resolve the AI's free-text `pollster_hint` to a FK. Reloaded
    every pipeline run (six-ish rows, negligible) so a newly-seeded
    pollster becomes visible without a process restart.

    Also validates `_POLLSTER_DIRECT_SOURCES` against the live `sources`
    table — that constant carries display names from seed_sources.py
    that drive source_url auto-population; a rename would silently
    break the auto-populate logic. We log a warning rather than
    raising so the pipeline keeps moving (the auto-populate is a
    convenience, not load-bearing)."""
    rows = conn.execute("SELECT id, slug, name_zh, name_en FROM pollsters").fetchall()
    lookup = {}
    for r in rows:
        for key in (r['slug'], r['name_zh'], r['name_en']):
            if key:
                lookup[key.strip().lower()] = r['id']

    known_source_names = {
        r['name'] for r in conn.execute("SELECT name FROM sources").fetchall()
    }
    missing = _POLLSTER_DIRECT_SOURCES - known_source_names
    if missing:
        print(f"  WARN: _POLLSTER_DIRECT_SOURCES references unknown source names "
              f"{sorted(missing)} — rename in seed_sources.py? source_url "
              f"auto-populate will silently no-op for these.")

    return lookup


def _resolve_pollster_id(hint, lookup):
    """Three-layer match against the lookup, falling back to the
    `unknown` pollster when no other match wins:
      1. Exact lowercased match on slug / name_zh / name_en.
      2. Lookup name is contained in the hint
         (e.g. '美麗島電子報今日公布...' contains '美麗島電子報').
      3. Hint is contained in the lookup name
         (e.g. 'TVBS' is contained in 'tvbs民調中心').
    Bidirectional substring matching is bounded by the small fixed
    pollster table — collisions are not a real risk at this scale.

    Glossary-mediated alias path: if the raw hint contains a glossary
    key (e.g. the short form '陸委會'), the glossary's English value
    ('Mainland Affairs Council (MAC)') is tried as a second candidate
    before falling through to `unknown`. Costs nothing for pollsters
    not in the glossary; gives every glossary-known acronym free alias
    resolution without a separate alias table. The short form '陸委會'
    is not a contiguous substring of the formal '大陸委員會' (because
    of the 員 in position 4), which is exactly the case this catches."""
    fallback = lookup.get('unknown')
    if not hint:
        return fallback
    candidates = [hint]
    for zh, en in _MASTER_GLOSSARY.items():
        if zh and zh in hint:
            candidates.append(en)
    for cand in candidates:
        h = (cand or '').strip().lower()
        if not h:
            continue
        if h in lookup:
            return lookup[h]
        for name, pid in lookup.items():
            if len(name) >= 2 and name in h:
                return pid
        for name, pid in lookup.items():
            if len(name) >= 2 and h in name:
                return pid
    return fallback


def _normalise_poll_questions(raw_questions):
    """Filter the AI's extracted questions to the shape the review queue
    expects. Drops questions with empty text or no numeric options;
    coerces percentage strings ('47.3%' or '47.3') to floats. Returns
    None when nothing usable survives — caller skips the whole poll."""
    cleaned = []
    for q in raw_questions or []:
        text_zh = (q.get('question_text_zh') or '').strip()
        text_en = (q.get('question_text_en') or '').strip()
        if not text_zh and not text_en:
            continue
        options = []
        for i, opt in enumerate(q.get('options') or []):
            label_zh = (opt.get('label_zh') or '').strip()
            label_en = (opt.get('label_en') or '').strip()
            pct_raw = opt.get('percentage')
            if isinstance(pct_raw, str):
                pct_raw = pct_raw.strip().rstrip('%').strip()
            try:
                pct = float(pct_raw)
            except (TypeError, ValueError):
                continue
            if not (0.0 <= pct <= 100.0):
                continue
            if not label_zh and not label_en:
                continue
            options.append({
                'label_zh': label_zh or label_en,
                'label_en': label_en or label_zh,
                'percentage': pct,
                'option_order': i,
            })
        if not options:
            continue
        cleaned.append({
            'question_text_zh': text_zh or text_en,
            'question_text_en': text_en or text_zh,
            'family_hint': (q.get('family_hint') or '').strip().lower() or None,
            'options': options,
        })
    return cleaned or None


# Sources whose article URL IS the pollster's canonical publication URL:
# TVBS poll PDFs, My-Formosa article pages, ETtoday ET民調 articles. For
# polls extracted from these articles, `source_url` is auto-populated to
# the article URL so the analyst doesn't have to paste it during approval.
# Polls cited inside third-party news articles (CNA, LTN, UDN, etc.) leave
# source_url NULL — those carry only a written reference, not a URL.
_POLLSTER_DIRECT_SOURCES = {'TVBS Poll Center', 'My-Formosa', 'ETtoday Polls'}


def _insert_poll_row(conn, article_id, poll, lookup):
    """Validate, resolve, and insert one AI-extracted poll as a pending
    row. Returns True iff a row was inserted. Used by both the Tier 1
    main loop and the poll-only Step 3c pass — keep both callers thin.

    Drops are logged with article_id + reason so analysts auditing
    pipeline runs can identify which extractions never made it into the
    review queue. Possible reasons: malformed fielded_start, no usable
    questions after _normalise_poll_questions, or a missing `unknown`
    fallback pollster (which should never happen post-seed)."""
    fielded_start = (poll.get('fielded_start') or '').strip()
    if not _POLL_DATE_RE.match(fielded_start):
        print(f"    poll dropped (article {article_id}): "
              f"fielded_start {fielded_start!r} not YYYY-MM-DD")
        return False

    fielded_end = (poll.get('fielded_end') or '').strip() or None
    if fielded_end and not _POLL_DATE_RE.match(fielded_end):
        fielded_end = None

    questions = _normalise_poll_questions(poll.get('questions'))
    if not questions:
        print(f"    poll dropped (article {article_id}): "
              f"no usable questions after normalisation "
              f"(pollster_hint={poll.get('pollster_hint')!r})")
        return False

    pollster_id = _resolve_pollster_id(poll.get('pollster_hint'), lookup)
    if pollster_id is None:
        print(f"    poll dropped (article {article_id}): "
              f"no `unknown` pollster in seed — run seed_sources.py")
        return False

    sample_size = poll.get('sample_size')
    try:
        sample_size = int(sample_size) if sample_size is not None else None
    except (TypeError, ValueError):
        sample_size = None

    methodology_note = (poll.get('methodology_note') or '').strip() or None

    # Resolve source_url: for pollster-direct sources the article URL IS
    # the pollster's canonical publication, so use it as source_url. For
    # everything else, leave NULL — the AI doesn't currently extract URLs
    # cited inside article bodies.
    source_url = None
    src = conn.execute(
        "SELECT a.url, s.name AS source_name FROM articles a "
        "JOIN sources s ON s.id = a.source_id WHERE a.id = ?",
        (article_id,),
    ).fetchone()
    if src and src['source_name'] in _POLLSTER_DIRECT_SOURCES:
        source_url = src['url']

    conn.execute("""
        INSERT INTO polls
        (pollster_id, fielded_start, fielded_end, sample_size,
         methodology_note, source_url, source_article_id, confidence,
         approval_status, pending_results_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
    """, (
        pollster_id, fielded_start, fielded_end, sample_size,
        methodology_note, source_url, article_id, poll.get('confidence', 0.7),
        json.dumps({'questions': questions}, ensure_ascii=False),
    ))
    return True


def analyse_article(title, content, language, source_name, published_at=None):
    """Send one article to Gemini and return structured analysis."""
    glossary_block = generate_dynamic_glossary(content, title)
    former_block = _officials_former_block(content, title)
    prompt = f"""{ANALYSIS_SYSTEM_PROMPT}

{_OFFICIALS_CURRENT_BLOCK}{glossary_block}{former_block}

SOURCE: {source_name}
LANGUAGE: {language}
PUBLISHED: {published_at or 'unknown'}
TITLE: {title}

FULL TEXT:
{content[:MAX_PROMPT_CONTENT_CHARS]}"""

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
    log_usage("tier1", "gemini-3.1-flash-lite", response)

    try:
        return json.loads(response.text)
    except json.JSONDecodeError:
        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            text = text.rsplit("```", 1)[0]
        return json.loads(text)


def _is_transient_error(exc):
    """True for failures worth retrying on the next run (rate limits, 5xx,
    network/timeout) rather than permanently tombstoning the article.
    google.genai raises APIError subclasses carrying a numeric `code`; raw
    transport failures surface as httpx/timeout exceptions whose class name we
    sniff so we don't have to import every SDK internal. Genuine parse/validation
    failures (e.g. JSONDecodeError) are NOT transient — those should tombstone so
    a pathological article can't retry forever."""
    code = getattr(exc, 'code', None)
    if not isinstance(code, int):
        code = getattr(exc, 'status_code', None)
    if isinstance(code, int) and (code == 429 or code >= 500):
        return True
    name = type(exc).__name__.lower()
    return any(tok in name for tok in
               ('timeout', 'connection', 'transport', 'unavailable',
                'deadline', 'resourceexhausted'))


def process_unanalysed_articles(limit=10):
    """Find articles that haven't been analysed yet and process them."""
    conn = get_connection()

    articles = conn.execute("""
        SELECT articles.id, articles.title_original, articles.content_original,
               articles.language, articles.published_at,
               sources.name as source_name,
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

    # Loaded once per pipeline run — six rows today, still cheap if the
    # roster grows. Falls back gracefully if the table is empty (no
    # polls will resolve, but everything else continues).
    pollster_lookup = _load_pollster_lookup(conn)

    for article in articles:
        title = article['title_original']
        print(f"  Analysing: {title[:60]}...")

        try:
            analysis = analyse_article(
                title=title,
                content=article['content_original'],
                language=article['language'],
                source_name=article['source_name'],
                published_at=article['published_at'],
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
                speaker = (stmt.get('speaker') or '').strip()
                figure_id = _ALIAS_TO_FIGURE_ID.get(speaker.lower())
                text = (stmt.get('statement_text') or '').strip()
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
                # Exact-match-only canonicalisation. See _exercise_canonical_en
                # for the reasoning (substring matching shadowed unit names
                # over compound exercise phrases).
                canonical_en = _exercise_canonical_en(name_zh_raw, name_en_raw)
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

            # Insert polls (pending analyst approval). Same editorial-gate
            # pattern as military_exercises — see _insert_poll_row for the
            # validation rules. Per-question results stage in
            # pending_results_json until the analyst assigns question_keys
            # at approval.
            for poll in analysis.get('polls', []):
                _insert_poll_row(conn, article['id'], poll, pollster_lookup)

            # Insert third-country diplomacy statements (pending analyst
            # approval). Separate axis from cross-strait sentiment — see
            # _insert_diplomacy_row and diplomacy_statements in schema.sql.
            # Per-row guard so one malformed statement can't cost the
            # article its whole analysis transaction.
            for stmt in analysis.get('diplomacy_statements', []):
                try:
                    _insert_diplomacy_row(conn, article['id'], stmt,
                                          source_place=article['source_place'])
                except Exception as e:
                    print(f"    diplomacy insert skipped: {e}")

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
                    escalation_former = _officials_former_block(article['content_original'], title)
                    review = client.models.generate_content(
                        model="gemini-3.5-flash",
                        contents=f"""{ANALYSIS_SYSTEM_PROMPT}

{_OFFICIALS_CURRENT_BLOCK}{escalation_glossary}{escalation_former}

{_ESCALATION_REVIEW_DIRECTIVE}

SOURCE: {article['source_name']}
LANGUAGE: {article['language']}
PUBLISHED: {article['published_at'] or 'unknown'}
TITLE: {title}

FULL TEXT:
{article['content_original'][:MAX_PROMPT_CONTENT_CHARS]}""",
                        config={
                            "response_mime_type": "application/json",
                            "max_output_tokens": 8000,
                            "temperature": 0.1
                        }
                    )
                    log_usage("tier2", "gemini-3.5-flash", review, article_id=article['id'])
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
                        'gemini-3.5-flash (review)', article['id']
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
            if _is_transient_error(e):
                # Rate limit / 5xx / network blip — NOT the article's fault.
                # Roll back any partial writes and leave ai_processed = 0 so the
                # next cron tick retries it, rather than tombstoning a perfectly
                # good article as permanently processed (silent data loss).
                conn.rollback()
                print(f"    ↳ transient error — leaving article {article['id']} "
                      f"unprocessed for retry next run")
                continue
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

DATE ANCHORING — `start_date` and `end_date` default to the article's
PUBLISHED year (given below). "Today", "this week", "on 22 May", or any
month/day without a year → use the PUBLISHED year. Only use a different
year when the article explicitly cites one. Do NOT anchor dates to your
training-data baseline.

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
PUBLISHED: {article['published_at'] or 'unknown'}
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
            # Template-following extraction — low thinking is plenty and avoids
            # spending several thinking tokens per output token (they bill at the
            # output rate). Measured ~12x thinking:output at 'medium'.
            "thinking_config": {"thinking_level": "low"},
        },
    )
    log_usage("exercise_only", "gemini-3.1-flash-lite", resp, article_id=article['id'])
    text = resp.text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        text = text.rsplit("```", 1)[0]
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return []
    # Accept a bare JSON array as well as the {"military_exercises": [...]} envelope.
    if isinstance(parsed, list):
        return parsed
    return (parsed or {}).get('military_exercises', []) or []


# NOTE: this mirrors the "DIPLOMACY STATEMENTS" block inside ANALYSIS_SYSTEM_PROMPT
# (the live Tier-1 path). Keep the SCOPE GATE / SIGN-guidance / WORKED EXAMPLES in
# sync across both — they can't share a constant because ANALYSIS_SYSTEM_PROMPT is a
# plain (brace-heavy JSON) string, not an f-string.
_DIPLOMACY_ONLY_PROMPT = """You are extracting THIRD-COUNTRY positions on Taiwan / the cross-strait (Taiwan Strait) question from a news article.

A "third country" is any country OTHER THAN China (PRC) and Taiwan (ROC). Extract statements or actions by a third country's officials, leaders, ruling party, legislators, or other figures that express a position on Taiwan, cross-strait relations, the Taiwan Strait, or the one-China question. Do NOT extract statements by China/PRC or Taiwan/ROC themselves. Do NOT score how the third country relates to either side bilaterally — score its stance ON THE TAIWAN QUESTION.

SCOPE GATE (apply FIRST): only extract a statement that expresses an EXPLICIT position on Taiwan, the Taiwan Strait, cross-strait relations, or the one-China question. If it is about PRC domestic human-rights policy (Xinjiang/Uyghurs/Tibet), WWII history or anti-militarism, general freedom of navigation, semiconductor/AI supply chains, or routine bilateral/administrative matters with NO explicit Taiwan reference, DO NOT extract it — a loose anti-PRC or pro-PRC sentiment with no Taiwan nexus is NOT a Taiwan stance. When in doubt whether Taiwan is the actual subject, extract nothing.

Return JSON: {"diplomacy_statements": [ {"country","country_iso","speaker","authority_tier","stance","statement_en","statement_zh","stated_date","confidence"} ]}

STANCE (-1.0 .. +1.0), pro-Beijing <-> pro-Taipei:
  SIGN IS DIRECTION, NOT TONE — the sign encodes which side of the strait the speaker favours, never emotional tone: condemning/criticising Beijing (e.g. over its coercion of Taiwan) is POSITIVE (pro-Taipei); endorsing reunification is NEGATIVE (pro-Beijing). Do not let harsh language about China push the score negative.
  +0.6..+1.0 pro-Taipei: explicit support — recognises/upgrades ties, backs Taiwan's international participation, official visit/delegation framed as solidarity, condemns PRC coercion of Taiwan, supplies arms with supportive framing.
  +0.2..+0.5 leaning Taipei: an explicit pro-Taiwan element is present — concern over PRC/Beijing pressure or coercion, a call for Taiwan's meaningful international participation, OR opposition to changing the status quo specifically "by force" / "by coercion" (these name the PRC as the threat).
  -0.2..+0.2 neutral (the DEFAULT for diplomatic boilerplate): a bare "peace and stability in the Taiwan Strait", "peaceful resolution", "cross-strait dialogue", or "oppose unilateral change to the status quo" — with NO naming of Beijing's pressure and NO support for Taiwan's participation — scores NEUTRAL (~0.0, within ±0.15), NOT leaning Taipei. Most diplomatic readouts are exactly this; only move up when an anti-coercion / anti-force / pro-participation / pro-Taiwan element is explicit.
  -0.5..-0.2 leaning Beijing: routine reaffirmation of a one-China policy, "respects China's position", acknowledges PRC concerns without endorsing reunification.
  -1.0..-0.6 pro-Beijing: endorses reunification / "Taiwan is part of China", explicitly opposes Taiwan independence, supports PRC sovereignty claims, condemns Taiwan or foreign "interference".

AUTHORITY TIER (classify from the title/role in the text): national executive or foreign ministry -> government; president/PM/monarch personally -> head_of_state; the ruling party acting as a party -> ruling_party; MPs/senators/parliamentary groups/committees -> legislator; mayors/governors/states/provinces -> subnational; ex-officials or retired figures -> former_official; academics/NGOs/business/anything else -> other.

The SAME article may carry MULTIPLE statements from one country at different tiers (e.g. a government one-China line PLUS a supportive parliamentary delegation) — emit each as a separate object; the divergence is the point.

country = English name; country_iso = ISO 3166-1 alpha-2 uppercase ('EU' for the European Union). stated_date defaults to the article's PUBLISHED year for any partial date. statement_en MUST be English (translate if needed); never put Chinese characters in it. WORKED EXAMPLES: (a) 'US lawmaker calls the PRC ethnic-unity law dystopian, says it will harass Uyghurs/Tibetans' -> no Taiwan nexus -> extract NOTHING; (b) 'Senator condemns Beijing's military coercion of Taiwan' -> +0.7 pro-Taipei (the condemnation targets Beijing, so the sign stays POSITIVE); (c) 'Foreign ministry reaffirms its one-China policy' with no pressure named -> -0.3 leaning Beijing; (d) 'We support peace and stability in the Taiwan Strait' and nothing more -> ~0.0 neutral. Return {"diplomacy_statements": []} if no third-country stance on Taiwan/cross-strait is expressed.
"""


def _extract_diplomacy_only(article):
    """Call Gemini with the diplomacy-only prompt over an already-analysed
    article. Returns the parsed list (possibly empty) of raw statement dicts
    ready for _insert_diplomacy_row. Used by the backfill script (historical
    articles were analysed before this feature existed, so the main Tier 1
    side-extract never ran on them)."""
    glossary = generate_dynamic_glossary(
        article['content_original'] or '',
        article['title_original'] or '',
    )
    prompt = f"""{_DIPLOMACY_ONLY_PROMPT}

{glossary}

SOURCE: {article['source_name']}
LANGUAGE: {article['language']}
PUBLISHED: {article['published_at'] or 'unknown'}
TITLE: {article['title_original']}

FULL TEXT:
{(article['content_original'] or '')[:6000]}"""

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
    log_usage("diplomacy_only", "gemini-3.1-flash-lite", resp, article_id=article['id'])
    text = resp.text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        text = text.rsplit("```", 1)[0]
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return []
    # The model occasionally returns a bare JSON array instead of the
    # {"diplomacy_statements": [...]} envelope — accept both.
    if isinstance(parsed, list):
        return parsed
    return (parsed or {}).get('diplomacy_statements', []) or []


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
    canonical_en = _exercise_canonical_en(name_zh_raw, name_en_raw)
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
    try:
        articles = conn.execute(f"""
            SELECT a.id, a.title_original, a.content_original, a.language,
                   a.published_at,
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
        # Wrap both extract AND insert in try/except per article so a single
        # bad payload (auth blip, IntegrityError, JSON encoding) doesn't
        # abort the whole batch and skip subsequent pipeline steps.
        for i, article in enumerate(articles, 1):
            try:
                exercises = _extract_exercises_only(article)
            except Exception as e:
                print(f"  [{i}/{len(articles)}] article {article['id']}: extract failed — {e}")
                continue
            if not exercises:
                continue
            article_inserted = 0
            for ex in exercises:
                try:
                    if _insert_exercise_row(conn, article['id'], ex):
                        article_inserted += 1
                except Exception as e:
                    # IntegrityError, JSON encoding error, etc. Log and
                    # continue — losing one candidate is preferable to
                    # aborting the run.
                    print(f"  [{i}/{len(articles)}] article {article['id']}: insert failed — {e}")
            if article_inserted:
                try:
                    conn.commit()
                except Exception as e:
                    print(f"  [{i}/{len(articles)}] commit failed: {e}")
                    conn.rollback()
            inserted += article_inserted
            print(f"  [{i}/{len(articles)}] article {article['id']}: "
                  f"{len(exercises)} extracted, {article_inserted} inserted")
        print(f"  Inserted {inserted} pending exercise candidates from {len(articles)} articles.")
    finally:
        conn.close()


# ============================================================
# Poll-only extraction pass (parallel to Tier 1)
# ============================================================
# Phase 2d follow-up to the main Tier 1 polls extraction. The keyword
# pre-filter rejects TW domestic political stories — including write-ups
# of Lai-approval / vote-intention / identity polls that lack a
# cross-strait keyword angle (no PRC / mainland / HK mention). Correct
# for the main signal feed but cuts off the polling tracker from its
# most data-rich source. This pass re-scans TW-side keyword-filter
# rejects whose TITLE contains 民調 or 民意調查 — a high-precision
# trigger (article is primarily ABOUT a poll) that avoids paying tokens
# on opinion pieces that mention 民調 only in passing. Byline-trigger
# (pollster homepage URLs) is deferred until pollster sources actually
# join the seed_sources roster.

_POLL_ONLY_PROMPT = """You are extracting public-opinion polls from a news article.
Return ONLY valid JSON of the shape:

{
  "polls": [
    {
      "pollster_hint": "organisation name EXACTLY as it appears in the article (Chinese or English), or null if not named",
      "fielded_start": "YYYY-MM-DD",
      "fielded_end": "YYYY-MM-DD or null if single-day fielding",
      "sample_size": 1071,
      "methodology_note": "1-line method summary (CATI / online panel / etc.) or null",
      "questions": [
        {
          "question_text_zh": "exact question wording from the article — DO NOT paraphrase",
          "question_text_en": "English translation of the question",
          "family_hint": "identity | unification | approval | attitude | vote_intent | issue",
          "options": [
            {"label_zh": "滿意", "label_en": "Satisfied", "percentage": 47.3}
          ]
        }
      ],
      "confidence": 0.85
    }
  ]
}

PRIMARY SUBJECT bar — only extract public-opinion polls of the
TAIWANESE or PRC publics on TW political, cross-strait, identity,
unification, approval, attitude, or vote-intention questions. Skip
polls of any other public (Israeli, US, Japanese, etc.) even when a
TW outlet covers them. Only extract when the article is REPORTING ON a
poll, not when it cites a poll number in passing to back a wider point.

The four-signal gate is POLL-LEVEL not question-level: a poll qualifies
when the ARTICLE AS A WHOLE names the pollster, gives a fieldwork date,
gives a sample size, and reports at least one numeric percentage. Once
the poll qualifies, you MUST extract every distinct question reported
in it — not just the headline one. Pollster-direct publications (e.g.
TVBS Poll Center PDFs, My-Formosa releases) typically report 3–8
questions per wave (vote intent, approval, favourability, policy
ratings, party-leader satisfaction, etc.) — emit them all into the
SAME poll's `questions[]` array. Skip ONLY: subgroup cross-tabulations
(e.g. "among 20-29 year olds X% supported Y", "DPP-identifiers split
Z%/W%") and demographic breakdowns of an already-extracted main result.

False negatives at the poll level (whole poll skipped) are preferred
over false positives. False negatives at the question level (only some
questions extracted from a qualifying poll) are NOT preferred — be
exhaustive once the poll qualifies.

SKIP: hypothetical surveys, forecasts, expert-panel surveys, internal
party-member polls, candidate-primary selection polls (初選民調 —
parties using polls to pick nominees is a process mechanism, not
public opinion), passing references to historical poll numbers, PRC
state-media "surveys" with no methodology disclosed.

POLLSTER — copy the organisation name VERBATIM into `pollster_hint`;
do not normalise or translate. The downstream resolver maps it to the
canonical pollster.

DATE ANCHORING — `fielded_start`/`fielded_end` default to the article's
PUBLISHED year (given below). "Today", "this week", "on 22 May", or any
month/day without a year → use the PUBLISHED year. Only use a different
year if the article explicitly cites one.

QUESTION TEXT — `question_text_zh` should be the verbatim wording from
the article when the article quotes the question directly. When the
article reports results in prose without quoting the question (common
in headlines: "X leads Y 43% to 37%" without a stated question), you
MAY synthesise the question_text_zh from the prose context (e.g.
"2026年嘉義市長選舉支持哪位參選人？"). Always provide
`question_text_en` in English.

OPTIONS — one entry per labelled response. `percentage` is a 0-100
float (47.3, not 0.473 or "47.3%"). Do NOT impute missing percentages.
If options sum to less than 100 because the article omitted some, leave
the gap — do not fabricate rows.

AGGREGATE-VS-INTENSITY: when an article reports a top-line aggregate
followed by an intensity breakdown — the standard My-Formosa / TVBS
pattern "有45.7%滿意（其中15.9%很滿意、29.8%還算滿意），44.9%不滿意
（其中26.0%很不滿意、18.9%有點不滿意），未明確回答有9.4%" — extract
ONLY the top-line aggregate (3 options: 滿意 / 不滿意 / 未明確回答),
NOT the 4-or-5-option intensity breakdown. The aggregated form is
what's directly comparable across waves and across pollsters; the
intensity breakdown is incidental journalistic detail. This rule
applies to ANY binary-with-intensity scale where the question
collapses to two directional positions plus no-opinion —
satisfied/dissatisfied, trust/distrust, favourable/unfavourable,
agree/disagree, and good/bad question families all qualify. If the
article reports both forms, compute the aggregate by summing the
two positive intensities and the two negative intensities. If the
article reports ONLY the intensity breakdown without a top-line
aggregate, ALSO collapse to the 3-option aggregate (sum the
positive intensities, sum the negative intensities, keep no-opinion
verbatim) — consistency across waves matters more than preserving
the journalistic detail. EXCEPTION (do NOT collapse): multi-option
position scales like the 統獨 7-step scale, statement-list
questions where each option is a distinct claim being rated,
multi-candidate vote-intention questions, and ranking questions.
These have more than two underlying positions; the option count is
the question's content, not modifier intensity.

CANONICAL NO-OPINION LABEL: when the article reports a no-opinion /
undeclared / didn't-answer bucket (typically 未明確回答 in Chinese
prose, sometimes 沒意見 / 不知道 / 未表態 / 無意見), emit it as:
  label_zh: "未明確回答"
  label_en: "No response"
Do NOT use variants like "No opinion", "No opinion/Other", "No
opinion/No answer", "Unspecified", "Don't know" — those break the
cross-wave trend chart by appearing as separate series.

VOTE-INTENT / CANDIDATE-SELECTION questions follow a different
canonical convention because they distinguish "didn't pick a
candidate" from "won't vote at all":
  - Candidate names: VERBATIM from the article, WITHOUT party
    prefix or party-parenthetical. Emit "李四川" not "國民黨李四川";
    emit "Su Chiao-hui" not "DPP Su Tsao-hui" or "Su Chiao-hui (DPP)".
    Party affiliation is a separate property of the pollster wave,
    not of the candidate-name string.
  - Residual buckets — collapse all of {不知道, 尚未決定, 未明確回答,
    無明確意見, "Don't know", "No clear answer", "No clear opinion"}
    to one canonical:
      label_zh: "尚未決定"
      label_en: "Undecided"
  - "Won't vote / spoiled ballot" is a SEPARATE residual category and
    must stay distinct. Canonical:
      label_zh: "不投票或投廢票"
      label_en: "Won't vote / Spoiled ballot"
    Collapse phrasing variants ("不投票/投廢票", "Not vote or spoiled
    ballot", "No vote or spoiled ballot", "Will not vote/Spoiled
    ballot") to this canonical.

EXAMPLE — a TVBS Chiayi poll PDF reporting vote intent + favourability
+ incumbent satisfaction yields ONE poll with THREE questions:

{
  "polls": [{
    "pollster_hint": "TVBS民調中心", "fielded_start": "2026-04-24",
    "fielded_end": "2026-04-30", "sample_size": 948,
    "methodology_note": "市內電話後四碼隨機抽樣 CATI",
    "questions": [
      {"question_text_zh": "2026年嘉義市長選舉，您支持哪位參選人？",
       "question_text_en": "Who do you support for 2026 Chiayi Mayor?",
       "family_hint": "vote_intent",
       "options": [{"label_zh": "王美惠", "label_en": "Wang Mei-hui", "percentage": 43.0},
                   {"label_zh": "張啟楷", "label_en": "Chang Chi-kai", "percentage": 37.0},
                   {"label_zh": "尚未決定", "label_en": "Undecided", "percentage": 20.0}]},
      {"question_text_zh": "您喜歡王美惠這位參選人嗎？",
       "question_text_en": "Do you like candidate Wang Mei-hui?",
       "family_hint": "approval",
       "options": [{"label_zh": "喜歡", "label_en": "Like", "percentage": 49.0},
                   {"label_zh": "不喜歡", "label_en": "Dislike", "percentage": 25.0},
                   {"label_zh": "未明確回答", "label_en": "No response", "percentage": 26.0}]},
      {"question_text_zh": "您對市長黃敏惠施政表現的滿意度？",
       "question_text_en": "Are you satisfied with Mayor Huang Min-hui's performance?",
       "family_hint": "approval",
       "options": [{"label_zh": "滿意", "label_en": "Satisfied", "percentage": 79.0},
                   {"label_zh": "不滿意", "label_en": "Dissatisfied", "percentage": 9.0},
                   {"label_zh": "未明確回答", "label_en": "No response", "percentage": 11.0}]}
    ],
    "confidence": 0.9
  }]
}

Use British English spelling in English fields. Return {"polls": []}
if no qualifying poll is reported.
"""


def _extract_polls_only(article):
    """Call Gemini with the poll-only prompt. Returns the parsed list
    (possibly empty) of raw poll dicts ready for _insert_poll_row."""
    glossary = generate_dynamic_glossary(
        article['content_original'] or '',
        article['title_original'] or '',
    )
    prompt = f"""{_POLL_ONLY_PROMPT}

{glossary}

SOURCE: {article['source_name']}
LANGUAGE: {article['language']}
PUBLISHED: {article['published_at'] or 'unknown'}
TITLE: {article['title_original']}

FULL TEXT:
{(article['content_original'] or '')[:MAX_PROMPT_CONTENT_CHARS]}"""

    resp = client.models.generate_content(
        model="gemini-3.5-flash",
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "max_output_tokens": 16000,
            "temperature": 0.1,
            # Template-following extraction against a detailed rubric — low
            # thinking is sufficient here and 'medium' was billing ~51 thinking
            # tokens per output token on this stage (thinking bills at the
            # output rate on the more expensive Flash model).
            "thinking_config": {"thinking_level": "low"},
        },
    )
    log_usage("poll_only", "gemini-3.5-flash", resp, article_id=article['id'])
    text = resp.text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        text = text.rsplit("```", 1)[0]
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return []
    # Accept a bare JSON array as well as the {"polls": [...]} envelope.
    if isinstance(parsed, list):
        return parsed
    return (parsed or {}).get('polls', []) or []


# Title-pattern trigger keywords. Kept as a tuple so the query builder
# generates the right number of placeholders. Title-only trigger is
# deliberately high-precision — articles whose title carries 民調 are
# almost always primarily about a poll. Adding body-text patterns
# (滿意度 / 支持度) would catch more but with much more noise; revisit
# if poll-bearing articles slip through unscanned.
POLL_ONLY_TITLE_PATTERNS = ('%民調%', '%民意調查%')


def process_poll_only_articles(days=14, limit=30):
    """Scan TW-side articles where the keyword pre-filter rejected the
    piece (no ai_analysis row) but the title carries a poll signal,
    and run the poll-only extraction. Capped per cron tick so a flurry
    of polling coverage can't run away. Idempotent — articles that
    already have a polls row are skipped."""
    from scraper.utils.db import get_connection
    conn = get_connection()
    try:
        pollster_lookup = _load_pollster_lookup(conn)
        title_clauses = " OR ".join(
            "a.title_original LIKE ?" for _ in POLL_ONLY_TITLE_PATTERNS
        )
        articles = conn.execute(f"""
            SELECT a.id, a.title_original, a.content_original, a.language,
                   a.published_at,
                   s.name AS source_name
            FROM articles a
            JOIN sources s ON s.id = a.source_id
            LEFT JOIN ai_analysis ai ON ai.article_id = a.id
            WHERE s.place = 'TW'
              AND a.ai_processed = 1
              AND ai.id IS NULL
              AND a.published_at >= datetime('now', ?)
              AND ({title_clauses})
              AND NOT EXISTS (
                  SELECT 1 FROM polls p WHERE p.source_article_id = a.id
              )
            ORDER BY a.published_at DESC
            LIMIT ?
        """, (f'-{days} days', *POLL_ONLY_TITLE_PATTERNS, limit)).fetchall()

        if not articles:
            print(f"  No candidate poll articles from TW sources in the last {days} days.")
            return

        inserted = 0
        # Per-article try/except — see process_exercise_only_articles for
        # the rationale (one bad payload mustn't abort subsequent steps).
        for i, article in enumerate(articles, 1):
            try:
                polls = _extract_polls_only(article)
            except Exception as e:
                print(f"  [{i}/{len(articles)}] article {article['id']}: extract failed — {e}")
                continue
            if not polls:
                continue
            article_inserted = 0
            for poll in polls:
                try:
                    if _insert_poll_row(conn, article['id'], poll, pollster_lookup):
                        article_inserted += 1
                except Exception as e:
                    print(f"  [{i}/{len(articles)}] article {article['id']}: insert failed — {e}")
            if article_inserted:
                try:
                    conn.commit()
                except Exception as e:
                    print(f"  [{i}/{len(articles)}] commit failed: {e}")
                    conn.rollback()
            inserted += article_inserted
            print(f"  [{i}/{len(articles)}] article {article['id']}: "
                  f"{len(polls)} extracted, {article_inserted} inserted")
        print(f"  Inserted {inserted} pending poll candidates from {len(articles)} articles.")
    finally:
        conn.close()


if __name__ == '__main__':
    process_unanalysed_articles(limit=10)