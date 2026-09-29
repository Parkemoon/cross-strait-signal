#!/usr/bin/env python3
"""Nightly backup of the SQLite database, with rotation and an off-site copy.

Until 2026-09-29 the only copies of prod were the hand-made predeploy
snapshots. This takes an online copy through SQLite's backup API (a
consistent snapshot; in WAL mode the pipeline keeps writing while it
runs), checks it with PRAGMA quick_check, compresses it with zstd to
`<dest>/cross_strait_signal-YYYYMMDD-HHMMSS.db.zst` and verifies the
archive. Only then does it rotate: keep the newest --keep-daily copies
plus the newest copy of each of the last --keep-weekly ISO weeks. A
failed run exits 1, removes its own partial files and leaves every
earlier backup in place.

Off-site: when the settings file carries R2_ENDPOINT, R2_BUCKET,
R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY (a Cloudflare R2 token scoped
to that one bucket), the verified archive is uploaded under its own name
and R2's copy is checked for size (content integrity in transit rests on
boto3's per-part upload checksums, which R2 validates). Retention there is the bucket's own
lifecycle rule (set in the Cloudflare dashboard), not this script. A
failed upload exits 1 but keeps the local backup and rotation.

check_scraper_health.py flags the newest local backup (backup:db_nightly)
and the newest R2 copy (backup:db_offsite) once a day old, so a missed
night is emailed the next morning.

    venv/bin/python scripts/backup_db.py                 # prod DB, defaults
    venv/bin/python scripts/backup_db.py --db … --dest … --no-offsite

Cron: nightly 02:30 UTC from the prod worktree (between pipeline ticks).

Restore: stop the backend (`systemctl stop cross-strait-signal`) and make
sure no pipeline tick is running; move the live DB and any -wal/-shm
beside it aside; `zstd -d <archive> -o db/cross_strait_signal.db`; start
the backend. The copy keeps the source's journal mode (WAL). An R2 copy
downloads with any S3 client, or from the bucket page in the dashboard.
"""
import argparse
import os
import re
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone

from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.path.join(ROOT, "db", "cross_strait_signal.db")
DEFAULT_ENV = os.path.join(ROOT, ".env")
DEFAULT_DEST = "/root/db-backups/nightly"
PREFIX = "cross_strait_signal-"
_NAME = re.compile(rf"^{re.escape(PREFIX)}(\d{{8}}-\d{{6}})\.db\.zst$")
_R2_SETTINGS = ("R2_ENDPOINT", "R2_BUCKET", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY")


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


def r2_client():
    """(S3 client, bucket) for the off-site copy from the R2_* settings,
    or None when none is set. Raises when only some are."""
    settings = {name: os.environ.get(name, "").strip() for name in _R2_SETTINGS}
    if not any(settings.values()):
        return None
    missing = [name for name, value in settings.items() if not value]
    if missing:
        raise RuntimeError(f"R2 partly configured, missing {', '.join(missing)}")
    import boto3
    from botocore.config import Config
    client = boto3.client(
        "s3", endpoint_url=settings["R2_ENDPOINT"], region_name="auto",
        aws_access_key_id=settings["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=settings["R2_SECRET_ACCESS_KEY"],
        config=Config(retries={"max_attempts": 5, "mode": "standard"}))
    return client, settings["R2_BUCKET"]


def upload_offsite(client, bucket, path):
    """Upload an archive under its own name (multipart; R2 validates
    boto3's per-part checksums) and confirm R2's copy has the full size."""
    key = os.path.basename(path)
    client.upload_file(path, bucket, key)
    stored = client.head_object(Bucket=bucket, Key=key)["ContentLength"]
    if stored != os.path.getsize(path):
        raise RuntimeError(f"R2 holds {stored} bytes of {key}, expected {os.path.getsize(path)}")
    return key


def newest_offsite(client, bucket):
    """Upload time (naive UTC) of the newest archive in the bucket, or None."""
    newest = None
    for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=PREFIX):
        for obj in page.get("Contents", []):
            if _NAME.match(obj["Key"]) and (newest is None or obj["LastModified"] > newest):
                newest = obj["LastModified"]
    return newest.astimezone(timezone.utc).replace(tzinfo=None) if newest else None


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--dest", default=DEFAULT_DEST)
    ap.add_argument("--env-file", default=DEFAULT_ENV)
    ap.add_argument("--keep-daily", type=int, default=7)
    ap.add_argument("--keep-weekly", type=int, default=4)
    ap.add_argument("--no-offsite", action="store_true", help="skip the R2 upload")
    args = ap.parse_args()
    load_dotenv(args.env_file)

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

    if args.no_offsite:
        return
    try:
        r2 = r2_client()
        if r2 is None:
            print("  off-site: skipped, no R2 settings")
            return
        sent = time.monotonic()
        key = upload_offsite(*r2, final)
        print(f"  off-site: r2://{r2[1]}/{key} ok ({time.monotonic() - sent:.0f}s)")
    except Exception as exc:
        print(f"  off-site upload FAILED (local backup kept): {type(exc).__name__}: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
