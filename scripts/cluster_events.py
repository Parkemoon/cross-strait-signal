"""
Event clustering script for Cross-Strait Signal.
Groups articles covering the same story within a 48-hour window. Two articles
from different sources are linked when their titles share keywords (Jaccard)
OR their English title + summary read alike (TF-IDF cosine). Title links group
transitively; summary links only join groups that are alike on average.
Run after the pipeline: python scripts/cluster_events.py
"""
import math
import os
import re
import sys
import uuid
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from scraper.utils.db import get_connection

# Stopwords to ignore when comparing titles
ZH_STOPWORDS = {
    # Simplified Chinese
    '的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都',
    '一', '一个', '上', '也', '很', '到', '说', '要', '去', '你', '会',
    '着', '没有', '看', '好', '自己', '这', '那', '中', '大', '来',
    '他', '她', '它', '们', '与', '及', '对', '为', '以', '而', '但',
    '或', '等', '后', '前', '时', '年', '月', '日', '称', '表示',
    '据', '将', '已', '其', '被', '并', '还', '则', '又', '正',
    '该', '此', '当', '因', '由', '向', '后', '内', '外',
    # Traditional Chinese equivalents
    '個', '說', '要', '會', '沒有', '這', '那', '來', '們',
    '後', '時', '稱', '表示', '據', '將', '已', '其', '被',
    '並', '還', '則', '又', '正', '該', '此', '當', '因',
    '由', '向', '後', '內', '外', '對', '為', '與', '及',
    '或', '等', '前', '看', '好', '自己', '去', '你',
    # Common news filler words (both scripts)
    '报道', '報道', '消息', '指出', '认为', '認為', '强调', '強調',
    '宣布', '宣佈', '透露', '证实', '證實', '否认', '否認',
    '发表', '發表', '发布', '發布', '声明', '聲明',
}

EN_STOPWORDS = {
    'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to',
    'for', 'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are',
    'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does',
    'did', 'will', 'would', 'could', 'should', 'may', 'might', 'says',
    'said', 'over', 'after', 'before', 'that', 'this', 'its', 'it',
}


def extract_keywords(title, language):
    """Extract significant keywords from a title."""
    if not title:
        return set()

    if language and language.startswith('zh'):
        # For Chinese: extract 2-character+ substrings, filter stopwords
        # Simple character-level extraction — no jieba needed
        words = set()
        title_clean = re.sub(r'[^\u4e00-\u9fff\u3400-\u4dbf]', ' ', title)
        # Extract all 2-4 character sequences as candidate keywords
        for i in range(len(title_clean)):
            for length in [4, 3, 2]:
                chunk = title_clean[i:i+length].strip()
                if len(chunk) == length and chunk not in ZH_STOPWORDS:
                    words.add(chunk)
        return words
    else:
        # For English: split on whitespace, lowercase, filter stopwords
        words = set(re.sub(r'[^\w\s]', '', title.lower()).split())
        return words - EN_STOPWORDS


def comparison_title(article):
    """(title, language) to compare an article on: the English title when
    there is one (better cross-language matching), else the original."""
    if article['title_en']:
        return article['title_en'], 'en'
    return article['title_original'], article['language']


def titles_are_similar(title1, lang1, title2, lang2, threshold=0.25):
    """
    Check if two titles are similar enough to be the same story.
    Uses Jaccard similarity on keyword sets.
    """
    kw1 = extract_keywords(title1, lang1)
    kw2 = extract_keywords(title2, lang2)

    if not kw1 or not kw2:
        return False

    intersection = kw1 & kw2
    union = kw1 | kw2

    if not union:
        return False

    jaccard = len(intersection) / len(union)

    # Also require at least 2 shared keywords to avoid false positives
    return jaccard >= threshold and len(intersection) >= 2


# ── Summary similarity ──────────────────────────────────────────────────────
# The title rule rarely links the two sides of the strait: each headlines the
# same event in its own vocabulary, so only 7% of clusters carried both a PRC
# and a TW source (30 days to 2026-10-13). The English title + AI summary
# describe the event in far closer terms. A different-source pair is linked
# when the TF-IDF cosine of those texts reaches SUMMARY_THRESHOLD; document
# frequencies come from the trailing IDF_DAYS so a big story's own words keep
# their weight.
#
# Summary links are not trusted transitively. A TAO press-conference
# transcript or a multi-topic editorial reads a little like every story it
# touches, and plain chaining through it built 60-100 article "clusters" of
# unrelated stories. So a summary link only joins two groups when their
# AVERAGE pairwise cosine reaches GROUP_THRESHOLD: a hub joins the one story
# it fits best and stops there. Title links keep their old unconditional
# behaviour, so every cluster the title rule builds still forms.
# Both thresholds measured against hand-labelled prod pairs (2026-10-13).
SUMMARY_THRESHOLD = 0.15
GROUP_THRESHOLD = 0.10
IDF_DAYS = 30

SUMMARY_STOPWORDS = EN_STOPWORDS | {
    'not', 'no', 'than', 'then', 'so', 'such', 'into', 'about', 'against',
    'between', 'during', 'under', 'up', 'down', 'out', 'also', 'say', 'which',
    'who', 'whom', 'whose', 'what', 'when', 'where', 'while', 'how', 'all',
    'any', 'both', 'each', 'few', 'more', 'most', 'other', 'some', 'own',
    'same', 'very', 'just', 'one', 'two', 'three', 'new', 'amid', 'per', 'via',
    'their', 'there', 'they', 'his', 'her', 'him', 'them', 'our', 'you',
    'your', 'these', 'those', 'can',
}
_WORD = re.compile(r"[a-z][a-z0-9'-]+")


def summary_terms(title_en, summary_en):
    """Term counts of the English title + summary (stopwords, <3 chars dropped)."""
    text = f"{title_en or ''} {summary_en or ''}".lower()
    return Counter(w for w in _WORD.findall(text)
                   if len(w) > 2 and w not in SUMMARY_STOPWORDS)


def summary_vectors(term_counts, df, n_docs):
    """{key: Counter} → {key: unit-length sublinear TF-IDF dict}.

    A term missing from `df` (the article is newer than the reference set)
    counts as seen once."""
    vectors = {}
    for key, counts in term_counts.items():
        v = {w: (1 + math.log(c)) * math.log(n_docs / df.get(w, 1))
             for w, c in counts.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        vectors[key] = {w: x / norm for w, x in v.items() if x}
    return vectors


def cosine(u, v):
    if len(u) > len(v):
        u, v = v, u
    return sum(x * v.get(w, 0.0) for w, x in u.items())


def document_frequencies(conn, days=IDF_DAYS):
    """(df Counter, n_docs) over the trailing `days` of analysed articles."""
    rows = conn.execute("""
        SELECT a.title_en, ai.summary_en
        FROM articles a
        JOIN ai_analysis ai ON a.id = ai.article_id
        WHERE a.published_at >= strftime('%Y-%m-%dT%H:%M:%S', 'now', ?)
          AND a.ai_processed = 1
          AND a.is_hidden = 0
    """, (f'-{days} days',)).fetchall()
    df = Counter()
    for r in rows:
        df.update(summary_terms(r['title_en'], r['summary_en']).keys())
    return df, max(len(rows), 1)


def group_articles(articles, vectors, summary_threshold=SUMMARY_THRESHOLD,
                   group_threshold=GROUP_THRESHOLD):
    """Group `articles` (dicts with id, source_id, titles) into stories.

    Pairs from the same source are never compared. Title links are applied
    first and always join; summary links follow, strongest first, and join
    two groups only when the groups' average pairwise cosine reaches
    `group_threshold`. Returns {article_id: group root id}."""
    cache = {}

    def sim(x, y):
        key = (x, y) if x < y else (y, x)
        if key not in cache:
            cache[key] = cosine(vectors.get(x, {}), vectors.get(y, {}))
        return cache[key]

    title_edges, summary_edges = [], []
    for i, a in enumerate(articles):
        for b in articles[i + 1:]:
            if a['source_id'] == b['source_id']:
                continue
            if titles_are_similar(*comparison_title(a), *comparison_title(b)):
                title_edges.append((a['id'], b['id']))
            else:
                s = sim(a['id'], b['id'])
                if s >= summary_threshold:
                    summary_edges.append((s, a['id'], b['id']))
    summary_edges.sort(key=lambda e: -e[0])

    parent = {a['id']: a['id'] for a in articles}
    members = {a['id']: [a['id']] for a in articles}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(rx, ry):
        if len(members[rx]) < len(members[ry]):
            rx, ry = ry, rx
        parent[ry] = rx
        members[rx] += members.pop(ry)

    for x, y in title_edges:
        rx, ry = find(x), find(y)
        if rx != ry:
            union(rx, ry)
    for _, x, y in summary_edges:
        rx, ry = find(x), find(y)
        if rx == ry:
            continue
        total = sum(sim(p, q) for p in members[rx] for q in members[ry])
        if total / (len(members[rx]) * len(members[ry])) >= group_threshold:
            union(rx, ry)
    return {aid: find(aid) for aid in parent}


def new_cluster_id():
    """A fresh cluster id that SQLite can never read as a number.

    articles.event_cluster_id has INTEGER affinity. The old bare 8-hex ids
    were coerced whenever they looked numeric: '3e412345' became REAL inf, so
    every such cluster merged into one, and all-digit ids became integers.
    The letter prefix keeps the id TEXT.
    """
    return 'c' + uuid.uuid4().hex[:12]


def repair_numeric_cluster_ids(conn, window_hours=48):
    """Re-key cluster ids that SQLite stored as numbers; returns a summary.

    A finite number still names exactly one cluster, so each distinct value
    just gets a new text id. Infinity is many clusters merged into one: its
    rows are re-grouped with the clustering rule itself (similar titles,
    different sources, published within `window_hours` of each other).
    Rows left alone in that re-grouping lose their cluster. Idempotent:
    once every id is text there is nothing to select. Does not commit.
    """
    rows = conn.execute("""
        SELECT id, event_cluster_id AS cid, title_original, title_en, language,
               source_id, julianday(published_at) AS jd
        FROM articles
        WHERE typeof(event_cluster_id) IN ('integer', 'real')
        ORDER BY published_at, id
    """).fetchall()
    rows = [dict(r) for r in rows]

    finite = {}
    merged = []
    for r in rows:
        if r['cid'] in (float('inf'), float('-inf')):
            merged.append(r)
        else:
            finite.setdefault(r['cid'], []).append(r['id'])

    for ids in finite.values():
        cid = new_cluster_id()
        conn.executemany("UPDATE articles SET event_cluster_id = ? WHERE id = ?",
                         [(cid, aid) for aid in ids])

    parent = {r['id']: r['id'] for r in merged}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    window = window_hours / 24.0
    for i, a in enumerate(merged):
        for b in merged[i + 1:]:
            if a['source_id'] == b['source_id']:
                continue
            if a['jd'] is None or b['jd'] is None or abs(a['jd'] - b['jd']) > window:
                continue
            if titles_are_similar(*comparison_title(a), *comparison_title(b)):
                parent[find(b['id'])] = find(a['id'])

    groups = {}
    for r in merged:
        groups.setdefault(find(r['id']), []).append(r['id'])
    regrouped = unclustered = 0
    for ids in groups.values():
        if len(ids) > 1:
            cid = new_cluster_id()
            conn.executemany(
                "UPDATE articles SET event_cluster_id = ?, cluster_size = ? WHERE id = ?",
                [(cid, len(ids), aid) for aid in ids])
            regrouped += 1
        else:
            conn.execute(
                "UPDATE articles SET event_cluster_id = NULL, cluster_size = 1 WHERE id = ?",
                (ids[0],))
            unclustered += 1

    return {
        'finite_clusters_rekeyed': len(finite),
        'merged_rows': len(merged),
        'regrouped_clusters': regrouped,
        'unclustered_rows': unclustered,
    }


def cluster_assignments(articles, groups):
    """One window's cluster ids: -> (assign, clear).

    assign = {article_id: (cluster_id, size)} for every article in a group of
    two or more, with a fresh id per group each run. clear = singletons that
    carry no cluster yet. A singleton that already has an id is in neither:
    its partners have aged out of the window, and NULLing it would tear the
    still-valid cross-window story apart.

    Ids are deliberately not carried over between runs. Keeping them let a
    story absorb the next day's related coverage indefinitely (week-long
    clusters of 100+ articles in the 2026-10-13 replay); a fresh id per run
    bounds a cluster to roughly the window."""
    by_root = {}
    for a in articles:
        by_root.setdefault(groups[a['id']], []).append(a)
    assign = {}
    for group in by_root.values():
        if len(group) > 1:
            cid = new_cluster_id()
            for a in group:
                assign[a['id']] = (cid, len(group))
    clear = [a['id'] for a in articles
             if a['id'] not in assign and a['event_cluster_id'] is None]
    return assign, clear


def cluster_recent_articles(hours=48, summary_threshold=SUMMARY_THRESHOLD,
                            group_threshold=GROUP_THRESHOLD):
    """
    Cluster articles published within the last N hours.
    Articles from different sources covering the same story get the same cluster ID.
    """
    # get_connection = row_factory + FK pragma + busy_timeout (this runs
    # inside the cron pipeline and used to be able to hit 'database is locked')
    conn = get_connection()

    # Get recently published, AI-processed articles
    articles = conn.execute("""
        SELECT a.id, a.title_original, a.title_en, a.language,
               a.published_at, a.source_id, a.event_cluster_id, ai.summary_en
        FROM articles a
        JOIN ai_analysis ai ON a.id = ai.article_id
        WHERE a.published_at >= strftime('%Y-%m-%dT%H:%M:%S', 'now', ?)
          AND a.ai_processed = 1
          AND a.is_hidden = 0
        ORDER BY a.published_at ASC
    """, (f'-{hours} hours',)).fetchall()

    print(f"Clustering {len(articles)} articles from the last {hours} hours...")

    articles = [dict(a) for a in articles]
    df, n_docs = document_frequencies(conn)
    vectors = summary_vectors(
        {a['id']: summary_terms(a['title_en'], a['summary_en']) for a in articles}, df, n_docs)
    groups = group_articles(articles, vectors, summary_threshold, group_threshold)
    assign, clear = cluster_assignments(articles, groups)

    conn.executemany(
        "UPDATE articles SET event_cluster_id = ?, cluster_size = ? WHERE id = ?",
        [(cid, size, aid) for aid, (cid, size) in assign.items()])
    conn.executemany(
        "UPDATE articles SET event_cluster_id = NULL, cluster_size = 1 WHERE id = ?",
        [(aid,) for aid in clear])
    conn.commit()
    conn.close()

    clusters = len({cid for cid, _ in assign.values()})
    print(f"Done. {len(articles)} articles processed, {len(assign)} articles in {clusters} clusters.")


if __name__ == '__main__':
    cluster_recent_articles(hours=48)
