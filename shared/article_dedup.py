"""Same-outlet near-duplicate article detection, shared by the pipeline
dedup step (scripts/run_pipeline.py Step 2m) and the historical sweep
(scripts/dedup_articles.py).

The only ingest-time dedup is exact-URL (articles.url UNIQUE), so a slug
or SEO retitle from the same outlet re-inserts the same story — measured
at ~3% of the analysed corpus on prod (2026-08-24): 408 byte-identical
articles, ~344 near-identical re-pushes (CT Opinion re-pushed the same
column under new URLs up to 5x over 3 days), plus same-day rewrites.

Three rules, all same-source only — cross-outlet duplication (agency
copy, coordinated PRC state messaging) is *signal* and is deliberately
never touched:

  R1 content-hash    whitespace-normalised content identical, <=7 days
                     apart. Pure slug churn.
  R2 content-sim     content trigram-Jaccard >= 0.90, <=72h apart. The
                     0.90 floor is measured, not chosen: the YDN daily
                     PLA-dynamics report (中共解放軍臺海周邊海、空域動態)
                     is a legitimate *series* with the identical title
                     133x whose templated consecutive-day content
                     similarity runs up to 0.80, while true re-pushes
                     measure 0.99+. Don't lower it.
  R3 title-same-day  normalised titles equal OR title-token Jaccard
                     >= 0.85, same calendar day. Catches same-day
                     rewrites whose content diverges (measured as low
                     as 0.31 when the outlet expands the story). Safe
                     against daily/recurring series precisely because
                     those recur on *different* days — never widen the
                     window without re-measuring the series corpus.

Detection is deterministic (no AI). Duplicates are hidden with
articles.is_hidden=1 — never deleted — keeping the richest copy
(see choose_keeper).
"""
import hashlib
import re
from datetime import datetime

# Below this many normalised chars the content rules (R1+R2) abstain and
# only the same-day title rule can fire. 200 is a measured floor, not a
# style choice: the YDN daily report's QUIET-day variant is a 68–80 char
# template where consecutive days differ by one digit (共機2架次 vs 8架次)
# — trigram Jaccard 0.93+ across *different days' data*, and two quiet
# days could even hash identically. Genuine same-outlet re-pushes that
# recur cross-day (YDN print-cycle 今日→昨日 rewrites, CT Opinion columns)
# all measure 400+ chars. Don't lower this without re-checking the short
# templated series.
CONTENT_MIN_CHARS = 200
TITLE_MIN_CHARS = 4           # normalised-title equality needs some substance
R1_WINDOW_HOURS = 7 * 24
R2_WINDOW_HOURS = 72
R2_CONTENT_THRESHOLD = 0.90
R3_TITLE_THRESHOLD = 0.85
MAX_WINDOW_HOURS = R1_WINDOW_HOURS  # widest rule window — scan cutoff

_WS = re.compile(r'\s+')
_NON_WORD = re.compile(r'[^\w一-鿿㐀-䶿]+')
_CJK_ONLY = re.compile(r'^[一-鿿㐀-䶿]+$')


def normalise_content(text):
    return _WS.sub('', text or '')


def content_fingerprint(text):
    """R1 key: md5 of whitespace-normalised content; None when too short
    to be meaningful (BBC Chinese description-only rows still qualify)."""
    norm = normalise_content(text)
    if len(norm) < CONTENT_MIN_CHARS:
        return None
    return hashlib.md5(norm.encode('utf-8')).hexdigest()


def content_trigrams(text):
    norm = normalise_content(text)
    if len(norm) < CONTENT_MIN_CHARS:
        return frozenset()
    return frozenset(norm[i:i + 3] for i in range(len(norm) - 2))


def normalise_title(title):
    """Case/punctuation/whitespace-insensitive form — full-width
    punctuation variants (、，vs space) collapse to the same string."""
    return _NON_WORD.sub('', (title or '').lower())


def title_tokens(title):
    """Token set for fuzzy title comparison: latin words + CJK bigrams."""
    out = set()
    for w in _NON_WORD.sub(' ', (title or '').lower()).split():
        if _CJK_ONLY.match(w) and len(w) > 1:
            out.update(w[i:i + 2] for i in range(len(w) - 1))
        else:
            out.add(w)
    return frozenset(out)


def jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _sizes_can_reach(a, b, threshold):
    """Jaccard(a,b) <= min(|a|,|b|)/max(|a|,|b|) — prune before the
    expensive intersection when the size ratio alone rules the pair out."""
    la, lb = len(a), len(b)
    if not la or not lb:
        return False
    return min(la, lb) / max(la, lb) >= threshold


def parse_ts(published_at, scraped_at=None):
    """Article timestamp for windowing; scraped_at fallback for NULL
    published_at. Tolerates T- or space-separated ISO, with/without tz."""
    for raw in (published_at, scraped_at):
        if not raw:
            continue
        s = str(raw).replace('Z', '+00:00').split('+')[0].replace(' ', 'T')
        try:
            return datetime.fromisoformat(s)
        except ValueError:
            continue
    return None


def prepare(row):
    """Precompute per-article comparison fields once. `row` is a mapping
    with at least id/source_id/title_original/content_original/published_at
    (scraped_at and the keeper-preference fields optional). Returns None
    when no usable timestamp exists (can't be windowed safely)."""
    ts = parse_ts(row.get('published_at'), row.get('scraped_at'))
    if ts is None:
        return None
    content = row.get('content_original') or ''
    return {
        'id': row['id'],
        'source_id': row['source_id'],
        'ts': ts,
        'day': ts.date(),
        'fp': content_fingerprint(content),
        'tris': content_trigrams(content),
        'ntitle': normalise_title(row.get('title_original')),
        'ttoks': title_tokens(row.get('title_original')),
        'content_len': len(content),
        'is_hidden': row.get('is_hidden') or 0,
        'analyst_approved': row.get('analyst_approved') or 0,
        'has_override': row.get('has_override') or 0,
        'has_analysis': row.get('has_analysis') or 0,
    }


def duplicate_rule(a, b):
    """Return the matching rule name for two prepared same-source
    articles, or None. Cheapest checks first."""
    hours_apart = abs((a['ts'] - b['ts']).total_seconds()) / 3600.0
    if hours_apart > MAX_WINDOW_HOURS:
        return None

    if a['fp'] is not None and a['fp'] == b['fp']:
        return 'content-hash'

    if a['day'] == b['day']:
        if len(a['ntitle']) >= TITLE_MIN_CHARS and a['ntitle'] == b['ntitle']:
            return 'title-same-day'
        if (_sizes_can_reach(a['ttoks'], b['ttoks'], R3_TITLE_THRESHOLD)
                and jaccard(a['ttoks'], b['ttoks']) >= R3_TITLE_THRESHOLD):
            return 'title-same-day'

    if (hours_apart <= R2_WINDOW_HOURS
            and _sizes_can_reach(a['tris'], b['tris'], R2_CONTENT_THRESHOLD)
            and jaccard(a['tris'], b['tris']) >= R2_CONTENT_THRESHOLD):
        return 'content-sim'

    return None


def find_duplicate_groups(prepared):
    """Union-find over pairwise rule matches. Input: prepared dicts (any
    order, any mix of sources — same-source scoping happens here).
    Returns (groups, rules): groups is a list of lists of prepared dicts
    (each len >= 2); rules maps article id -> the rule that first linked
    it into its group (keepers included, informational)."""
    by_source = {}
    for p in prepared:
        by_source.setdefault(p['source_id'], []).append(p)

    parent = {}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        parent.setdefault(x, x)
        parent.setdefault(y, y)
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[ry] = rx

    rules = {}
    for rows in by_source.values():
        rows.sort(key=lambda p: p['ts'])
        for i, a in enumerate(rows):
            for b in rows[i + 1:]:
                if (b['ts'] - a['ts']).total_seconds() / 3600.0 > MAX_WINDOW_HOURS:
                    break
                rule = duplicate_rule(a, b)
                if rule:
                    union(a['id'], b['id'])
                    rules.setdefault(a['id'], rule)
                    rules.setdefault(b['id'], rule)

    clusters = {}
    by_id = {p['id']: p for p in prepared}
    for aid in parent:
        clusters.setdefault(find(aid), []).append(by_id[aid])
    return [g for g in clusters.values() if len(g) > 1], rules


def choose_keeper(group):
    """Pick the copy to keep: visible beats hidden, then analyst-approved,
    then analyst-overridden (never bury Ed's manual work), then already-
    analysed, then richest content, then earliest published, then lowest id."""
    def key(p):
        return (
            0 if p['is_hidden'] else 1,
            p['analyst_approved'],
            p['has_override'],
            p['has_analysis'],
            p['content_len'],
            -p['ts'].timestamp(),
            -p['id'],
        )
    return max(group, key=key)
