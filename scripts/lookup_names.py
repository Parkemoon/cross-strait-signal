"""Run the name lookup worker by hand (pipeline Step 3f does the same every tick).

    python scripts/lookup_names.py --days 30 --limit 100
    python scripts/lookup_names.py --no-search          # Wikidata + generated only
    python scripts/lookup_names.py --db /var/www/cross-strait-signal/db/cross_strait_signal.db
"""
import argparse
import os
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

from scraper.utils.db import get_connection
from scraper.processors.name_lookup import lookup_new_names


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--days', type=int, default=14)
    ap.add_argument('--limit', type=int, default=60)
    ap.add_argument('--db')
    ap.add_argument('--no-search', action='store_true', help='skip the grounded-search tier')
    args = ap.parse_args()
    conn = get_connection(args.db)
    lookup_new_names(days=args.days, limit=args.limit, conn=conn, use_search=not args.no_search)
    conn.close()


if __name__ == '__main__':
    main()
