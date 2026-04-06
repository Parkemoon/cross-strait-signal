import sqlite3
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

conn = sqlite3.connect('db/cross_strait_signal.db')
conn.row_factory = sqlite3.Row

PARTY_KEYWORDS = [
    '國民黨', '民眾黨', '朱立倫', '韓國瑜', '鄭麗文', '江啟臣', '傅崐萁',
    '訪陸', '赴陸', '赴京', '訪問北京', '訪問大陸', 'KMT', '藍委', '藍營',
    '在野', '參訪團', '兩岸論壇', '國共', 'kmt', 'kuomintang',
]

rows = conn.execute("""
    SELECT a.id, a.title_original, a.published_at, ai.topic_primary
    FROM articles a
    JOIN ai_analysis ai ON a.id = ai.article_id
    WHERE ai.topic_primary != 'PARTY_VISIT'
      AND ai.topic_primary != 'NOT_RELEVANT'
    ORDER BY a.published_at DESC
""").fetchall()

candidates = []
for r in rows:
    title = r['title_original']
    if any(kw.lower() in title.lower() for kw in PARTY_KEYWORDS):
        candidates.append(r)

print(f"Likely misclassified party visit articles ({len(candidates)} found):\n")
for r in candidates:
    print(f"  [{r['id']}] [{r['topic_primary']}] {r['published_at'][:10]}  {r['title_original'][:80]}")

if not candidates:
    print("None found.")
    conn.close()
    exit()

to_update = [r['id'] for r in candidates]
confirm = input(f"\nReclassify all {len(to_update)} to PARTY_VISIT? (y/n): ")
if confirm.strip().lower() == 'y':
    conn.execute(f"""
        UPDATE ai_analysis SET topic_primary = 'PARTY_VISIT'
        WHERE article_id IN ({','.join('?' * len(to_update))})
    """, to_update)
    conn.commit()
    print(f"Done. {conn.total_changes} rows updated.")
else:
    print("Aborted.")

conn.close()
