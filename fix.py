import sqlite3
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

conn = sqlite3.connect('db/cross_strait_signal.db')
conn.row_factory = sqlite3.Row

rows = conn.execute("""
    SELECT a.id, a.title_original, a.published_at, s.country
    FROM articles a
    JOIN ai_analysis ai ON a.id = ai.article_id
    JOIN sources s ON a.source_id = s.id
    WHERE ai.topic_primary = 'POL_DOMESTIC'
    ORDER BY s.country, a.published_at DESC
""").fetchall()

print(f"POL_DOMESTIC articles to migrate ({len(rows)} total):\n")
tw = [r for r in rows if r['country'] == 'TW']
prc = [r for r in rows if r['country'] == 'PRC']
sg = [r for r in rows if r['country'] not in ('TW', 'PRC')]

print(f"  → POL_DOMESTIC_TW (TW sources): {len(tw)}")
print(f"  → POL_DOMESTIC_PRC (PRC sources): {len(prc)}")
print(f"  → POL_DOMESTIC_TW (SG/other, Taiwan subject assumed): {len(sg)}\n")

# Show sample of each
for label, group in [("TW", tw[:3]), ("PRC", prc[:3]), ("SG/other", sg[:3])]:
    for r in group:
        print(f"  [{label}] {r['published_at'][:10]}  {r['title_original'][:70]}")

confirm = input(f"\nApply migration? (y/n): ")
if confirm.strip().lower() == 'y':
    tw_ids = [r['id'] for r in rows if r['country'] == 'TW']
    prc_ids = [r['id'] for r in rows if r['country'] == 'PRC']
    sg_ids = [r['id'] for r in rows if r['country'] not in ('TW', 'PRC')]

    if tw_ids + sg_ids:
        conn.execute(f"""
            UPDATE ai_analysis SET topic_primary = 'POL_DOMESTIC_TW'
            WHERE topic_primary = 'POL_DOMESTIC'
            AND article_id IN ({','.join('?' * len(tw_ids + sg_ids))})
        """, tw_ids + sg_ids)

    if prc_ids:
        conn.execute(f"""
            UPDATE ai_analysis SET topic_primary = 'POL_DOMESTIC_PRC'
            WHERE topic_primary = 'POL_DOMESTIC'
            AND article_id IN ({','.join('?' * len(prc_ids))})
        """, prc_ids)

    conn.commit()
    print(f"Done. {conn.total_changes} rows updated.")
else:
    print("Aborted.")

conn.close()
