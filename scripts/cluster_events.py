"""
Event clustering script for Cross-Strait Signal.
Groups articles covering the same story based on title similarity and publication time.
Run after the pipeline: python scripts/cluster_events.py
"""
import sqlite3
import os
import re
import uuid
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'db', 'cross_strait_signal.db')

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


def cluster_recent_articles(hours=48):
    """
    Cluster articles published within the last N hours.
    Articles from different sources covering the same story get the same cluster ID.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Get recently published, AI-processed articles
    articles = conn.execute("""
        SELECT a.id, a.title_original, a.title_en, a.language,
               a.published_at, a.source_id, a.event_cluster_id
        FROM articles a
        JOIN ai_analysis ai ON a.id = ai.article_id
        WHERE a.published_at >= datetime('now', ?)
          AND a.ai_processed = 1
        ORDER BY a.published_at ASC
    """, (f'-{hours} hours',)).fetchall()

    print(f"Clustering {len(articles)} articles from the last {hours} hours...")

    articles = [dict(a) for a in articles]

    # Build clusters using a simple union-find approach
    # Each article starts in its own cluster
    clusters = {}  # article_id -> cluster_id

    for i, article in enumerate(articles):
        if article['id'] not in clusters:
            clusters[article['id']] = str(uuid.uuid4())[:8]

        for j, other in enumerate(articles):
            if i >= j:
                continue
            if article['source_id'] == other['source_id']:
                continue  # Don't cluster same-source articles

            # Use English title if available (better cross-language matching)
            title_a = article['title_en'] or article['title_original']
            lang_a = 'en' if article['title_en'] else article['language']
            title_b = other['title_en'] or other['title_original']
            lang_b = 'en' if other['title_en'] else other['language']

            if titles_are_similar(title_a, lang_a, title_b, lang_b):
                # Merge clusters — give both the same ID
                cluster_id = clusters[article['id']]
                if other['id'] in clusters:
                    # Remap all articles with the other cluster ID
                    old_id = clusters[other['id']]
                    for aid in clusters:
                        if clusters[aid] == old_id:
                            clusters[aid] = cluster_id
                else:
                    clusters[other['id']] = cluster_id

    # Count cluster sizes
    from collections import Counter
    cluster_counts = Counter(clusters.values())

    # Update database
    updated = 0
    clustered = 0
    for article_id, cluster_id in clusters.items():
        size = cluster_counts[cluster_id]
        conn.execute(
            "UPDATE articles SET event_cluster_id = ?, cluster_size = ? WHERE id = ?",
            (cluster_id if size > 1 else None, size, article_id)
        )
        if size > 1:
            clustered += 1
        updated += 1

    conn.commit()
    conn.close()

    multi_clusters = sum(1 for c, n in cluster_counts.items() if n > 1)
    print(f"Done. {updated} articles processed, {clustered} articles in {multi_clusters} clusters.")


if __name__ == '__main__':
    cluster_recent_articles(hours=48)