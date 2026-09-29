#!/usr/bin/env python3
"""Nightly backup of the SQLite database, with rotation.

Until 2026-09-29 the only copies of prod were the hand-made predeploy
snapshots. This takes an online copy through SQLite's backup API (a
consistent snapshot; in WAL mode the pipeline keeps writing while it
runs), checks it with PRAGMA quick_check, compresses it with zstd to
`<dest>/cross_strait_signal-YYYYMMDD-HHMMSS.db.zst` and verifies the
archive. Only then does it rotate: keep the newest --keep-daily copies
plus the newest copy of each of the last --keep-weekly ISO weeks. A
failed run exits 1, removes its own partial files and leaves every
earlier backup in place. check_scraper_health.py flags the newest backup
once it is a day old, so a missed night is emailed the next morning.

    venv/bin/python scripts/backup_db.py                 # prod DB, defaults
    venv/bin/python scripts/backup_db.py --db … --dest …

Cron: nightly 02:30 UTC from the prod worktree (between pipeline ticks).

Restore: stop the backend (`systemctl stop cross-strait-signal`) and make
sure no pipeline tick is running; move the live DB and any -wal/-shm
beside it aside; `zstd -d <archive> -o db/cross_strait_signal.db`; start
the backend. The copy keeps the source's journal mode (WAL).
"""
import argparse
import os
import re
import sqlite3
import subprocess
import sys
import time
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.path.join(ROOT, "db", "cross_strait_signal.db")
DEFAULT_DEST = "/root/db-backups/nightly"
PREFIX = "cross_strait_signal-"
_NAME = re.compile(rf"^{re.escape(PREFIX)}(\d{{8}}-\d{{6}})\.db\.zst$")


def backups(dest):
    """[(datetime, path)] of finished archives in dest, newest first."""
    found = []
    for name in os.listdir(dest):
        m = _NAME.match(name)
        if m:
            found.append((datetime.strptime(m.group(1), "%Y%m%d-%H%M%S"),
                          os.path.join(dest, name)))
    return sorted(found, reverse=True)


def to_keep(stamps, keep_daily, keep_weekly):
    """The stamps (newest first) that rotation keeps: the newest
    keep_daily, plus the newest of each of the keep_weekly most recent
    ISO weeks that have a backup."""
    keep = set(stamps[:keep_daily])
    weeks = {}
    for stamp in stamps:
        weeks.setdefault(stamp.isocalendar()[:2], stamp)
    for week in sorted(weeks, reverse=True)[:keep_weekly]:
        keep.add(weeks[week])
    return keep


def snapshot(db, out):
    """Online copy of db into out via the backup API, in one step so it is
    a single consistent read. Returns quick_check's verdict on the copy."""
    src = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=60)
    dst = sqlite3.connect(out)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    check = sqlite3.connect(out)
    try:
        return check.execute("PRAGMA quick_check").fetchone()[0]
    finally:
        check.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--dest", default=DEFAULT_DEST)
    ap.add_argument("--keep-daily", type=int, default=7)
    ap.add_argument("--keep-weekly", type=int, default=4)
    args = ap.parse_args()

    os.makedirs(args.dest, exist_ok=True)
    os.chmod(args.dest, 0o700)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    raw = os.path.join(args.dest, f".partial-{stamp}.db")
    packed = os.path.join(args.dest, f".partial-{stamp}.db.zst")
    final = os.path.join(args.dest, f"{PREFIX}{stamp}.db.zst")

    started = time.monotonic()
    try:
        verdict = snapshot(args.db, raw)
        if verdict != "ok":
            raise RuntimeError(f"quick_check on the copy: {verdict}")
        copied = time.monotonic()
        subprocess.run(["zstd", "-q", "-T0", "-6", raw, "-o", packed], check=True)
        subprocess.run(["zstd", "-q", "-t", packed], check=True)
        os.chmod(packed, 0o600)
        os.rename(packed, final)
    except Exception as exc:
        print(f"{datetime.now():%Y-%m-%d %H:%M:%S} backup FAILED: {exc}")
        for path in (raw, packed):
            if os.path.exists(path):
                os.remove(path)
        sys.exit(1)
    os.remove(raw)

    found = backups(args.dest)
    keep = to_keep([s for s, _ in found], args.keep_daily, args.keep_weekly)
    dropped = [p for s, p in found if s not in keep]
    for path in dropped:
        os.remove(path)

    size_mb = os.path.getsize(final) / 1e6
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S} backup ok: {final} "
          f"({size_mb:,.0f} MB; copy+check {copied - started:.0f}s, "
          f"total {time.monotonic() - started:.0f}s); "
          f"{len(found) - len(dropped)} kept, {len(dropped)} rotated out")


if __name__ == "__main__":
    main()
