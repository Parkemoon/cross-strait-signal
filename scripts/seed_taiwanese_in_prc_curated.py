"""Seed the curated PRC-side data on Taiwanese into `cross_strait_population`.

Reads `scraper/processors/prc_tw_people_records.json` and upserts numeric
milestones (台胞证 cumulative, NIA annual issuance, 2020 census settler
floor) under direction='taiwanese_in_prc', source='CURATED'.

The JSON's `policy_timeline` array is NOT ingested — it's served straight
to the frontend by the `/api/economy/people-records` endpoint as
annotations on the visitor-flow chart.

Idempotent — re-running upserts on (direction, metric, period, period_type).
Run after edits to the JSON file, e.g. when NIA publishes a new annual
issuance figure.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from scraper.utils.db import get_connection

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

JSON_PATH = os.path.join(
    os.path.dirname(__file__), '..',
    'scraper', 'processors', 'prc_tw_people_records.json',
)

_UPSERT_SQL = """
INSERT INTO cross_strait_population
    (direction, metric, period, period_type, value, unit, source, source_url, notes)
VALUES ('taiwanese_in_prc', ?, ?, ?, ?, ?, 'CURATED', ?, ?)
ON CONFLICT(direction, metric, period, period_type) DO UPDATE SET
    value      = excluded.value,
    unit       = excluded.unit,
    source_url = excluded.source_url,
    notes      = excluded.notes,
    scraped_at = CURRENT_TIMESTAMP
"""


def _seed(conn) -> int:
    with open(JSON_PATH, encoding='utf-8') as f:
        data = json.load(f)

    rows = []

    # cumulative_milestones: each entry has permits_issued_total +
    # unique_taiwanese_holders, fanned out as two separate metrics.
    for m in data.get('cumulative_milestones', []):
        period = m['as_of'][:4]  # 'YYYY-MM-DD' → 'YYYY'
        url = m.get('source_url')
        if 'permits_issued_total' in m:
            rows.append((
                'tbz_cumulative_permits', period, 'snapshot',
                float(m['permits_issued_total']), 'permits', url,
                m.get('note') or '',
            ))
        if 'unique_taiwanese_holders' in m:
            rows.append((
                'tbz_cumulative_holders', period, 'snapshot',
                float(m['unique_taiwanese_holders']), 'persons', url,
                m.get('note') or '',
            ))

    # annual_permits_issued: TW-only annual issuance figure.
    for a in data.get('annual_permits_issued', []):
        metric = (
            'tbz_annual_issued_partial' if a.get('partial')
            else 'tbz_annual_issued'
        )
        rows.append((
            metric, str(a['year']), 'annual',
            float(a['permits']), 'permits', a.get('source_url'),
            a.get('note') or '',
        ))

    # settler_floor: single 2020 census snapshot.
    sf = data.get('settler_floor')
    if sf:
        period = sf['as_of'][:4]
        rows.append((
            'census_residents', period, 'snapshot',
            float(sf['count']), 'persons', sf.get('source_url'),
            sf.get('definition') or '',
        ))

    conn.executemany(_UPSERT_SQL, rows)
    return len(rows)


def main():
    conn = get_connection()
    written = _seed(conn)
    conn.commit()
    conn.close()
    print(f'[seed taiwanese_in_prc curated] {written} rows upserted')


if __name__ == '__main__':
    main()
