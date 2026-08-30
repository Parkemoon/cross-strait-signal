"""Cross-strait visits side-extract (Phase 2f) — pipeline Step 3e.

One Gemini call per analysed DIP_VISIT / PARTY_VISIT article, returning the
publicly reported visits / meetings / exchanges between an official- or
party-level actor from Taiwan and one from the mainland (incl. HK / Macao).
Rows land `pending` in `cross_strait_visits` for the analyst queue.

Scope is cross-strait ONLY — Taiwan↔third-country and PRC↔third-country
travel belongs to the diplomacy axis and must never land here. The scope
gate lives in `_VISIT_RULES` (the prompt) AND in `insert_visit_row` (the
code): an extracted row whose two sides are not one TW and one PRC
affiliation is dropped, whatever the model said.

Lives in its own module rather than ai_pipeline.py on purpose: the pass is
topic-gated (runs on ~5% of articles), so it has no business inside the
unconditional Tier-1 prompt, and it borrows only the shared plumbing
(Gemini client, glossary, usage log, JSON parse, key-figure aliases).
"""
from __future__ import annotations

import json
import re

from scraper.processors.ai_pipeline import (
    _ALIAS_TO_FIGURE_ID,
    _is_transient_error,
    client,
    generate_dynamic_glossary,
)
from scraper.utils.llm import parse_llm_json
from scraper.utils.usage_log import log_usage

_MODEL = "gemini-3.1-flash-lite"

# Affiliation enum. Side is derived from it (never trusted from the model)
# — this is what enforces the cross-strait scope gate in code.
TW_AFFILIATIONS = {
    'DPP', 'KMT', 'TPP', 'NPP', 'PFP', 'NP', 'TW_OTHER_PARTY',
    'TW_GOV',          # central government: Executive Yuan, MAC, ministries, presidency
    'SEF',             # Straits Exchange Foundation (quasi-official)
    'TW_LEGISLATURE',  # Legislative Yuan as a body / cross-party legislator group
    'TW_LOCAL',        # county / city governments and councils
    'TW_IND',          # independent politicians
}
PRC_AFFILIATIONS = {
    'CCP',             # party organs: Central Committee, United Front Work Dept, provincial party
    'TAO',             # Taiwan Affairs Office (State Council / CCP Central Committee)
    'ARATS',           # Association for Relations Across the Taiwan Straits
    'PRC_GOV',         # State Council ministries, NPC, CPPCC
    'PRC_LOCAL',       # provincial / municipal governments
    'HKMO_GOV',        # Hong Kong / Macao governments
    'PRC_OTHER',
}
AFFILIATIONS = TW_AFFILIATIONS | PRC_AFFILIATIONS

LEVELS = {
    'head_of_state_govt',   # president / premier / vice-president
    'party_leader',         # party chair
    'party_senior',         # vice-chair, secretary-general, standing committee member
    'minister',             # minister / vice-minister / TAO director / MAC minister / SEF-ARATS chair
    'legislator',           # LY member / NPC or CPPCC delegate
    'local_executive',      # mayor / county magistrate / provincial governor / party secretary
    'local_official',       # deputy mayor, bureau chief, city councillor
    'youth_delegation',     # party youth wing / student-political exchange delegation
    'delegation',           # mixed or unspecified official delegation
    'other',
}
DIRECTIONS = {'TW_TO_PRC', 'PRC_TO_TW', 'THIRD_VENUE'}
STATUSES = {'reported', 'planned', 'rumoured', 'cancelled', 'blocked'}


def side_of(affiliation: str | None) -> str | None:
    a = (affiliation or '').strip().upper()
    if a in TW_AFFILIATIONS:
        return 'TW'
    if a in PRC_AFFILIATIONS:
        return 'PRC'
    return None


_VISIT_RULES = """SCOPE GATE (apply FIRST): extract ONLY visits, meetings, forums, exchanges or delegations where ONE party is an official- or party-level actor from Taiwan (government, MAC, SEF, Legislative Yuan, county/city governments, political parties and their youth wings, serving or former senior politicians) and the OTHER party is an official- or party-level actor from mainland China, Hong Kong or Macao (CCP organs, TAO, ARATS, State Council ministries, NPC/CPPCC, provincial or municipal governments, HK/Macao governments). Cross-strait ONLY:
- EXCLUDE any travel between Taiwan and a THIRD country (Taiwan officials in the US, Japan, Europe, Palau, etc.) and between the PRC and a third country (a Japanese delegation in Beijing) — those belong to a different axis. Return an empty array for them even when the article is about a visit.
- EXCLUDE purely private, commercial, academic, religious, sporting or tourist travel unless it is LED by a serving official / party officer or is a party- or government-organised delegation. A Taiwanese businessman at a Beijing trade fair is not a visit; a KMT vice-chair leading a business delegation is.
- INCLUDE visits that were announced but not yet made (visit_status='planned'), reported but unconfirmed (='rumoured'), called off (='cancelled'), and visits refused entry or denied a permit by either side (='blocked') — a blocked visit is a signal in its own right. A completed or ongoing visit is 'reported'.
- INCLUDE meetings between the two sides held in a THIRD place (Singapore, an international forum's sidelines): direction='THIRD_VENUE', visitor = the Taiwan-side party.
- One row per VISIT EVENT, not per person: a delegation is one row with its head as the visitor and the delegation described in delegation_desc_en. If the article covers two distinct trips (e.g. a KMT visit AND a separate TPP visit), return two rows.
- Reactions and commentary about a visit (MAC criticising a KMT trip, DPP legislators condemning it) are NOT separate visits — extract the visit itself once, from the facts the article gives.

FIELDS:
- direction: 'TW_TO_PRC' when the Taiwan party travels to the mainland/HK/Macao; 'PRC_TO_TW' when the mainland/HK/Macao party travels to Taiwan; 'THIRD_VENUE' as above.
- visitor_*: the TRAVELLING party (head of delegation when several). visitor_name_en uses the established romanisation (Wade-Giles/Tongyong for Taiwanese names, Hanyu Pinyin for PRC names); visitor_name_zh as printed. visitor_title = role in English as the article gives it ('KMT Vice Chairman', 'Taipei Mayor', 'Director of the Taiwan Affairs Office').
- visitor_affiliation: EXACTLY one of DPP, KMT, TPP, NPP, PFP, NP, TW_OTHER_PARTY, TW_GOV, SEF, TW_LEGISLATURE, TW_LOCAL, TW_IND (Taiwan side) or CCP, TAO, ARATS, PRC_GOV, PRC_LOCAL, HKMO_GOV, PRC_OTHER (mainland side). A serving mayor or county magistrate is TW_LOCAL even if they belong to a party; a party official with no government post is their party; a Legislative Yuan member is their party, TW_LEGISLATURE only for a cross-party LY body.
- visit_level: EXACTLY one of head_of_state_govt, party_leader, party_senior, minister, legislator, local_executive, local_official, youth_delegation, delegation, other. Use the HIGHEST-ranking traveller's level.
- counterpart_*: who they met / were hosted by on the other side, same conventions; null when the article names only the event. counterpart_affiliation from the same enum.
- event_name_en/zh: the occasion when it is a named forum or programme (Straits Forum 海峽論壇, KMT-CCP Forum 國共論壇, Shanghai–Taipei City Forum 雙城論壇, Cross-Strait Youth Summit 海峽青年節); null for an ad-hoc visit.
- location_label: city or venue in English ('Shanghai', 'Xiamen', 'Taipei', 'Kinmen').
- start_date / end_date: YYYY-MM-DD. DATE ANCHORING — default to the article's PUBLISHED year; 'today', 'this week', a bare month/day all mean the published year. Only use another year when the article states it. end_date null when unknown or single-day.
- purpose_en: ONE English sentence — what the visit was for and what, if anything, was agreed or said.
- quote_zh: a verbatim original-language snippet (≤200 chars) that establishes the visit; null if the article is in English.
- confidence 0–1: 0.9 when names, dates and place are all explicit; ≤0.5 for rumoured or indirectly reported trips.

WORKED EXAMPLES:
- "KMT vice chairman Andrew Hsia leads delegation to Straits Forum in Xiamen, meets Wang Huning" → direction=TW_TO_PRC, visitor=Hsia Li-yan / 夏立言, KMT, party_senior, counterpart=Wang Huning, CCP, event=Straits Forum, location=Xiamen.
- "Shanghai TAO director visits Taipei for the Twin-City Forum; MAC says the delegation may not meet the media" → PRC_TO_TW, visitor=the Shanghai official, PRC_LOCAL, local_official, event=Shanghai–Taipei City Forum, location=Taipei, 'reported'.
- "MAC denies entry permit to Shanghai TAO officials over political conditions" → PRC_TO_TW, visit_status='blocked'.
- "Foreign Minister Lin Chia-lung to attend Pacific Islands Forum in Palau" → OUT OF SCOPE, empty array.
- "Japanese cross-party delegation visits Beijing, discusses Taiwan" → OUT OF SCOPE, empty array.
- "DPP legislators condemn KMT youth trip to Shanghai as kowtowing" → ONE row for the KMT youth trip (TW_TO_PRC, KMT, youth_delegation), nothing for the DPP reaction."""

_VISIT_ONLY_PROMPT = ("""You are extracting CROSS-STRAIT VISITS — publicly reported visits, meetings and exchanges between official- or party-level actors from Taiwan and from mainland China / Hong Kong / Macao — from a news article.

Return JSON: {"visits": [ {"direction","visit_status","visitor_name_en","visitor_name_zh","visitor_title","visitor_affiliation","visit_level","delegation_desc_en","counterpart_name_en","counterpart_name_zh","counterpart_title","counterpart_affiliation","event_name_en","event_name_zh","location_label","start_date","end_date","purpose_en","quote_zh","confidence"} ]}

""" + _VISIT_RULES + """

Return {"visits": []} if the article reports no in-scope cross-strait visit.
""")


def extract_visits(article) -> list[dict]:
    """One Gemini call. Returns the raw list (possibly empty) of visit dicts
    ready for insert_visit_row. Raises on API failure (caller decides
    whether it is transient)."""
    glossary = generate_dynamic_glossary(
        article['content_original'] or '',
        article['title_original'] or '',
    )
    prompt = f"""{_VISIT_ONLY_PROMPT}

{glossary}

SOURCE: {article['source_name']}
LANGUAGE: {article['language']}
PUBLISHED: {article['published_at'] or 'unknown'}
TITLE: {article['title_original']}

FULL TEXT:
{(article['content_original'] or '')[:6000]}"""

    resp = client.models.generate_content(
        model=_MODEL,
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "max_output_tokens": 4000,
            "temperature": 0.1,
            "thinking_config": {"thinking_level": "medium"},
        },
    )
    log_usage("visits_only", _MODEL, resp, article_id=article['id'])
    try:
        out = parse_llm_json(resp.text, envelope_key='visits')
    except json.JSONDecodeError:
        return []
    return out if isinstance(out, list) else []


_DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')


def _clean(s, limit=None):
    s = (s or '')
    if not isinstance(s, str):
        s = str(s)
    s = s.strip() or None
    if s and limit:
        s = s[:limit]
    return s


def _english_or_none(s):
    """CJK guard for *_en fields — null rather than reject the row."""
    s = _clean(s)
    if not s:
        return None
    cjk = sum(1 for c in s if '一' <= c <= '鿿') / len(s)
    return None if cjk > 0.15 else s


def _figure_id(*names):
    for n in names:
        n = (n or '').strip().lower()
        if n and n in _ALIAS_TO_FIGURE_ID:
            return _ALIAS_TO_FIGURE_ID[n]
    return None


def validate_visit(v: dict) -> dict | None:
    """Normalise one raw visit dict into insert-ready columns, or None when it
    fails the scope gate. Pure — no DB — so it is unit-testable."""
    direction = _clean(v.get('direction'))
    direction = direction.upper() if direction else None
    if direction not in DIRECTIONS:
        return None

    v_aff = (_clean(v.get('visitor_affiliation')) or '').upper()
    v_side = side_of(v_aff)
    if not v_side:
        return None                      # unknown affiliation → can't prove the scope
    c_aff = (_clean(v.get('counterpart_affiliation')) or '').upper() or None
    c_side = side_of(c_aff)
    if c_aff and not c_side:
        c_aff = None                     # keep the row, drop the junk enum
    # Scope gate in code: the two sides must be one TW and one PRC. When the
    # counterpart is unnamed, the direction must at least agree with the
    # visitor's side.
    if c_side and c_side == v_side:
        return None
    if direction == 'TW_TO_PRC' and v_side != 'TW':
        return None
    if direction == 'PRC_TO_TW' and v_side != 'PRC':
        return None
    if direction == 'THIRD_VENUE' and v_side != 'TW':
        return None

    level = (_clean(v.get('visit_level')) or 'other').lower()
    if level not in LEVELS:
        level = 'other'
    status = (_clean(v.get('visit_status')) or 'reported').lower()
    if status not in STATUSES:
        status = 'reported'

    start = _clean(v.get('start_date'))
    end = _clean(v.get('end_date'))
    if start and not _DATE_RE.match(start):
        start = None
    if end and not _DATE_RE.match(end):
        end = None
    if start and end and end < start:
        end = None

    try:
        conf = float(v.get('confidence'))
        conf = max(0.0, min(1.0, conf))
    except (TypeError, ValueError):
        conf = None

    name_en = _english_or_none(v.get('visitor_name_en'))
    name_zh = _clean(v.get('visitor_name_zh'), 80)
    if not (name_en or name_zh or _clean(v.get('delegation_desc_en'))):
        return None                      # nobody identified — not a usable row

    return {
        'direction': direction,
        'visit_status': status,
        'visitor_name_en': name_en,
        'visitor_name_zh': name_zh,
        'visitor_title': _english_or_none(v.get('visitor_title')),
        'visitor_affiliation': v_aff,
        'visitor_side': v_side,
        'visitor_figure_id': _figure_id(name_en, name_zh),
        'visit_level': level,
        'delegation_desc_en': _english_or_none(v.get('delegation_desc_en')),
        'counterpart_name_en': _english_or_none(v.get('counterpart_name_en')),
        'counterpart_name_zh': _clean(v.get('counterpart_name_zh'), 80),
        'counterpart_title': _english_or_none(v.get('counterpart_title')),
        'counterpart_affiliation': c_aff,
        'counterpart_figure_id': _figure_id(v.get('counterpart_name_en'), v.get('counterpart_name_zh')),
        'event_name_en': _english_or_none(v.get('event_name_en')),
        'event_name_zh': _clean(v.get('event_name_zh'), 80),
        'location_label': _english_or_none(v.get('location_label')),
        'start_date': start,
        'end_date': end,
        'purpose_en': _english_or_none(v.get('purpose_en')),
        'quote_zh': _clean(v.get('quote_zh'), 300),
        'confidence': conf,
    }


_COLS = [
    'direction', 'visit_status', 'visitor_name_en', 'visitor_name_zh', 'visitor_title',
    'visitor_affiliation', 'visitor_side', 'visitor_figure_id', 'visit_level',
    'delegation_desc_en', 'counterpart_name_en', 'counterpart_name_zh', 'counterpart_title',
    'counterpart_affiliation', 'counterpart_figure_id', 'event_name_en', 'event_name_zh',
    'location_label', 'start_date', 'end_date', 'purpose_en', 'quote_zh', 'confidence',
]


def insert_visit_row(conn, article_id, raw: dict) -> bool:
    """Validate + insert one pending row. Returns True iff inserted. Does NOT
    commit — the caller owns the transaction. Shared by Step 3e and the
    backfill so the scope gate is identical on both paths."""
    row = validate_visit(raw)
    if not row:
        return False
    cols = ', '.join(['article_id'] + _COLS)
    marks = ', '.join('?' * (len(_COLS) + 1))
    conn.execute(
        f"INSERT INTO cross_strait_visits ({cols}, approval_status) VALUES ({marks}, 'pending')",
        (article_id, *[row[c] for c in _COLS]),
    )
    return True


VISIT_TOPICS = ('DIP_VISIT', 'PARTY_VISIT')

SELECT_SQL = """
    SELECT a.id, a.title_original, a.content_original, a.language, a.published_at,
           s.name AS source_name
    FROM articles a
    JOIN ai_analysis ai ON ai.article_id = a.id
    JOIN sources s ON s.id = a.source_id
    WHERE a.ai_processed = 1
      AND a.is_hidden = 0
      AND a.content_original != ''
      AND (ai.topic_primary IN ({topics}) OR ai.topic_secondary IN ({topics}))
      AND NOT EXISTS (SELECT 1 FROM cross_strait_visit_scans v WHERE v.article_id = a.id)
      AND a.published_at >= strftime('%Y-%m-%dT%H:%M:%S', 'now', ?)
    ORDER BY a.published_at DESC
    LIMIT ?
"""


def process_visit_articles(conn=None, days=14, limit=30, dry_run=False, log=print):
    """Step 3e. Scan analysed DIP_VISIT / PARTY_VISIT articles not yet
    visit-scanned, extract, insert pending rows, stamp the scan marker
    (zero-yield included). Transient API errors leave no marker so the
    article retries next tick. Returns (articles_scanned, rows_inserted)."""
    own = conn is None
    if own:
        from scraper.utils.db import get_connection
        conn = get_connection()
    try:
        topics = ','.join('?' * len(VISIT_TOPICS))
        sql = SELECT_SQL.format(topics=topics)
        articles = conn.execute(sql, (*VISIT_TOPICS, *VISIT_TOPICS, f'-{days} days', limit)).fetchall()
        if not articles:
            log(f"  No unscanned visit-topic articles in the last {days} days.")
            return 0, 0

        inserted = scanned = 0
        for i, article in enumerate(articles, 1):
            try:
                visits = extract_visits(article)
            except Exception as e:  # noqa: BLE001
                log(f"  [{i}/{len(articles)}] article {article['id']}: extract failed — {e}")
                if _is_transient_error(e):
                    continue
                visits = []
            n_ins = 0
            if dry_run:
                for v in visits:
                    ok = validate_visit(v)
                    log(f"    {'KEEP' if ok else 'DROP'} {v.get('direction')} {v.get('visitor_name_en')} "
                        f"({v.get('visitor_affiliation')}) → {v.get('counterpart_name_en')} "
                        f"{v.get('start_date')} {v.get('location_label')}")
                    n_ins += bool(ok)
            else:
                for v in visits:
                    try:
                        if insert_visit_row(conn, article['id'], v):
                            n_ins += 1
                    except Exception as e:  # noqa: BLE001
                        log(f"  [{i}/{len(articles)}] article {article['id']}: insert failed — {e}")
                conn.execute(
                    "INSERT OR REPLACE INTO cross_strait_visit_scans (article_id, n_extracted, n_inserted) VALUES (?, ?, ?)",
                    (article['id'], len(visits), n_ins))
                try:
                    conn.commit()
                except Exception as e:  # noqa: BLE001
                    log(f"  [{i}/{len(articles)}] commit failed: {e}")
                    conn.rollback()
                    continue
            scanned += 1
            inserted += n_ins
            if visits:
                log(f"  [{i}/{len(articles)}] article {article['id']}: {len(visits)} extracted, {n_ins} kept")
        log(f"  {'Would insert' if dry_run else 'Inserted'} {inserted} pending visit candidates from {scanned} articles.")
        return scanned, inserted
    finally:
        if own:
            conn.close()
