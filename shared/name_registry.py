"""Name registry — the live store of canonical English forms for Chinese
personal names (table `name_registry`, migration 0014).

Three callers:
  - the Tier-1 write path (scraper/processors/ai_pipeline.py) loads the
    approved rows once per run, merges them over entity_canonical.json for
    the entity resolver and over glossary.json for the prompt-time
    terminology block, and rewrites the model's own renderings in the
    English text fields (title, summary, key quote, reasoning) to the
    canonical form;
  - the lookup worker (scraper/processors/name_lookup.py) writes new rows;
  - the admin queue (api/routes/names.py) approves / edits / rejects.

Precedence: an approved registry row beats the committed JSON (the analyst's
decision is the later one). The JSON files stay the durable, committed
config — scripts/seed_name_registry.py --export writes approved worker /
analyst rows back into them so staging and prod converge through git, the
way refresh_officials.py output travels.

Only zh_trad is unique. Simplified spellings fold onto the traditional row
(zhconv when available; the row also stores zh_simp so a lookup by either
script hits without the library).
"""
import json
import re

from shared.name_style import style_name

try:
    import zhconv as _zhconv
except ImportError:  # pragma: no cover
    _zhconv = None

SOURCES = ('glossary', 'canonical', 'survey', 'wikidata', 'search', 'generated', 'analyst')
STATUSES = ('pending', 'approved', 'rejected')


def to_trad(s):
    return _zhconv.convert(s, 'zh-tw') if _zhconv and s else s


def to_simp(s):
    return _zhconv.convert(s, 'zh-cn') if _zhconv and s else s


def load_approved(conn):
    """{zh: en} over BOTH scripts for every approved row with an English form."""
    out = {}
    for r in conn.execute("SELECT zh_trad, zh_simp, en FROM name_registry WHERE status = 'approved' AND en IS NOT NULL AND en != ''"):
        out[r['zh_trad']] = r['en']
        if r['zh_simp']:
            out[r['zh_simp']] = r['en']
    return out


def merge_canon(canon, registry_map):
    """A copy of the entity_norm canon structure with approved registry
    rows layered over `canonical` (registry wins on conflict)."""
    merged = dict(canon)
    merged['canonical'] = {**canon['canonical'], **registry_map}
    return merged


def merge_glossary(glossary, registry_map):
    return {**glossary, **registry_map}


def known_forms(conn, zh):
    """Registry row for a name in either script, any status, or None."""
    return conn.execute(
        "SELECT * FROM name_registry WHERE zh_trad = ? OR zh_simp = ? OR zh_trad = ? LIMIT 1",
        (zh, zh, to_trad(zh))).fetchone()


def upsert(conn, zh, en, side, source, status, *, qid=None, evidence_url=None, evidence_note=None,
           role_hint=None, candidates=None, mentions=0, first_article_id=None, confidence=None,
           reviewed_by=None):
    """Insert a row keyed on the traditional form, or update a NON-approved
    existing row. An approved row is never overwritten here — that is the
    admin queue's job (source='analyst'). Returns the row id."""
    zh_trad = to_trad(zh)
    zh_simp = to_simp(zh_trad)
    if zh_simp == zh_trad:
        zh_simp = None if zh == zh_trad else zh
    en = style_name(zh_trad, en, side, role_hint) if en else en   # house style at the door (shared/name_style.py)
    cand = json.dumps(candidates or [], ensure_ascii=False)
    row = conn.execute("SELECT id, status FROM name_registry WHERE zh_trad = ?", (zh_trad,)).fetchone()
    if row is None:
        cur = conn.execute("""
            INSERT INTO name_registry (zh_trad, zh_simp, en, side, source, status, qid, evidence_url,
                                       evidence_note, role_hint, candidates_json, mentions, first_article_id,
                                       confidence, reviewed_at, reviewed_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CASE WHEN ? = 'pending' THEN NULL ELSE datetime('now') END, ?)""",
            (zh_trad, zh_simp, en, side, source, status, qid, evidence_url, evidence_note, role_hint,
             cand, mentions, first_article_id, confidence, status, reviewed_by))
        return cur.lastrowid
    if row['status'] == 'approved':
        return row['id']
    conn.execute("""
        UPDATE name_registry SET zh_simp = COALESCE(?, zh_simp), en = ?, side = COALESCE(?, side), source = ?,
               status = ?, qid = ?, evidence_url = ?, evidence_note = ?, role_hint = COALESCE(?, role_hint),
               candidates_json = ?, mentions = MAX(mentions, ?), confidence = ?,
               reviewed_at = CASE WHEN ? = 'pending' THEN NULL ELSE datetime('now') END, reviewed_by = ?
        WHERE id = ?""",
        (zh_simp, en, side, source, status, qid, evidence_url, evidence_note, role_hint, cand, mentions,
         confidence, status, reviewed_by, row['id']))
    return row['id']


def rewrite_renderings(text, pairs):
    """Replace the model's own rendering of each name with the canonical
    form in a free-text field. `pairs` = [(rendering, canonical), …];
    whole-word, case-sensitive, longest rendering first so 'Wang Hung-wei'
    is replaced before a bare 'Wang'. Renderings shorter than four
    characters or equal to the canonical are skipped."""
    if not text or not pairs:
        return text
    for rendering, canonical in sorted(pairs, key=lambda p: -len(p[0] or '')):
        if not rendering or not canonical or rendering == canonical or len(rendering) < 4:
            continue
        text = re.sub(r'(?<![A-Za-z\-])' + re.escape(rendering) + r'(?![A-Za-z\-])', canonical, text)
    return text


TEXT_FIELDS = ('title_en', 'summary_en', 'key_quote_en', 'sentiment_reasoning')


def apply_to_analysis(analysis, resolver):
    """Rewrite one Tier-1 analysis dict in place: every person entity whose
    Chinese name resolves to a canonical English form gets that form, and
    the model's original rendering is replaced in the English text fields
    and key-figure statements. `resolver(zh) -> en | None`. Returns the
    list of (rendering, canonical) pairs applied."""
    pairs = []
    for e in analysis.get('entities') or []:
        if not isinstance(e, dict) or e.get('type') != 'person':
            continue
        canonical = resolver(e.get('name') or '')
        rendering = (e.get('name_en') or '').strip()
        if canonical and rendering and rendering != canonical:
            pairs.append((rendering, canonical))
            e['name_en'] = canonical
    if not pairs:
        return pairs
    for f in TEXT_FIELDS:
        if analysis.get(f):
            analysis[f] = rewrite_renderings(analysis[f], pairs)
    for s in analysis.get('key_figure_statements') or []:
        if isinstance(s, dict) and s.get('statement_text'):
            s['statement_text'] = rewrite_renderings(s['statement_text'], pairs)
    return pairs
