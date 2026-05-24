"""One-shot backfill of pla_incursions from the public PLATracker sheet.

PLATracker (Gerald Brown / Ben Lewis) compiles MND daily PLA aircraft
intrusions into Taiwan's de facto ADIZ since 2020-09-09 (the date MND
began publishing daily). The sheet exposes a CSV preview that we pull
once with a gviz URL — no API key needed, no live cron dependency.

Only the "Daily Totals" tab is ingested. Its `Total Aircraft Tracked in
de facto ADIZ` column maps to our `aircraft_intruded`; PLATracker does
not track the broader 共機架次 figure (aircraft_total) consistently,
nor vessels/coast-guard, so those stay NULL on backfill rows.

Inserts with source='platracker_backfill'. The live MND scraper writes
source='mnd' for any date both cover, and the API coalesces preferring
'mnd' — so re-running this script is safe and won't override recent data.

Re-run: `python scripts/backfill_pla_incursions_platracker.py`
Idempotent — upserts on (date, source).
"""
import csv
import io
import os
import sys
from datetime import datetime

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from scraper.utils.db import get_connection

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

SHEET_ID = '1qbfYF0VgDBJoFZN5elpZwNTiKZ4nvCUcs5a7oYwm52g'
TAB_NAME = 'Daily Totals'
GVIZ_URL = (
    f'https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq'
    f'?tqx=out:csv&sheet={TAB_NAME.replace(" ", "%20")}'
)

DATE_COL = 'Date'
INTRUDED_COL = 'Total Aircraft Tracked in de facto ADIZ'

_UPSERT_SQL = """
INSERT INTO pla_incursions
    (date, aircraft_total, aircraft_intruded, aircraft_zones,
     vessels_total, coast_guard_total, source, source_url, raw_text)
VALUES (?, NULL, ?, NULL, NULL, NULL, 'platracker_backfill', ?, NULL)
ON CONFLICT(date, source) DO UPDATE SET
    aircraft_intruded = excluded.aircraft_intruded,
    source_url        = excluded.source_url,
    scraped_at        = CURRENT_TIMESTAMP
"""


def _parse_date(s: str) -> str | None:
    s = (s or '').strip().strip('"')
    if not s:
        return None
    try:
        return datetime.strptime(s, '%m/%d/%Y').date().isoformat()
    except ValueError:
        return None


def _parse_int(s: str) -> int | None:
    s = (s or '').strip().strip('"').replace(',', '')
    if not s:
        return None
    try:
        return int(float(s))
    except ValueError:
        return None


def backfill() -> int:
    print(f"Fetching PLATracker CSV: {GVIZ_URL}")
    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        resp = client.get(GVIZ_URL)
        resp.raise_for_status()
    text = resp.text
    if text.startswith('﻿'):
        text = text[1:]
    reader = csv.DictReader(io.StringIO(text))
    headers = reader.fieldnames or []
    if DATE_COL not in headers or INTRUDED_COL not in headers:
        raise RuntimeError(
            f"Expected columns missing from sheet. Got: {headers!r}"
        )

    conn = get_connection()
    written = 0
    skipped = 0
    for row in reader:
        iso_date = _parse_date(row.get(DATE_COL, ''))
        intruded = _parse_int(row.get(INTRUDED_COL, ''))
        if iso_date is None or intruded is None:
            skipped += 1
            continue
        conn.execute(_UPSERT_SQL, (iso_date, intruded, GVIZ_URL))
        written += 1
    conn.commit()

    earliest = conn.execute(
        "SELECT MIN(date) AS d FROM pla_incursions WHERE source='platracker_backfill'"
    ).fetchone()['d']
    latest = conn.execute(
        "SELECT MAX(date) AS d FROM pla_incursions WHERE source='platracker_backfill'"
    ).fetchone()['d']
    conn.close()
    print(f"  wrote {written} rows ({earliest} → {latest}), skipped {skipped} unparseable")
    return written


if __name__ == '__main__':
    backfill()
