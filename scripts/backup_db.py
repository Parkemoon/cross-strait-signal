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

Files kept out of git: whatever `.git/info/exclude` matches in any
worktree of this repo is in no git history and in no DB backup, so the
same run packs it into `<dest>/private_files-YYYYMMDD-HHMMSS.tar.zst`
(members `<worktree folder>/<path>`; Claude Code's own `.claude/` state
left out), rotates those archives on the same schedule and uploads the
newest beside the DB archive. The list is read from git each night, so
nothing here names the files. A failure there exits 1 after the DB part
has finished.

check_scraper_health.py flags the newest local backup (backup:db_nightly)
and the newest R2 copies (backup:db_offsite, backup:private_offsite) once
a day old, so a missed night is emailed the next morning.

    venv/bin/python scripts/backup_db.py                 # prod DB, defaults
    venv/bin/python scripts/backup_db.py --db … --dest … --no-offsite
    venv/bin/python scripts/backup_db.py --private-only  # just the git-excluded files

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
import tarfile
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
PRIVATE_PREFIX = "private_files-"
PRIVATE_NAME = re.compile(rf"^{re.escape(PRIVATE_PREFIX)}(\d{{8}}-\d{{6}})\.tar\.zst$")
_R2_SETTINGS = ("R2_ENDPOINT", "R2_BUCKET", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY")


def backups(dest, pattern=_NAME):
    """[(datetime, path)] of finished archives in dest, newest first
    (DB archives by default; PRIVATE_NAME for the git-excluded files)."""
    found = []
    for name in os.listdir(dest):
        m = pattern.match(name)
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


def _git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


def private_files(root=ROOT):
    """[(worktree, relative path)] of the files `.git/info/exclude` keeps
    out of git, across every worktree of root's repo. Only that file's
    patterns count, so .gitignore'd files (the settings file, the DB,
    build output) are never picked up; `.claude/` (Claude Code's own
    state) is left out."""
    common = _git("-C", root, "rev-parse", "--path-format=absolute", "--git-common-dir").strip()
    exclude = os.path.join(common, "info", "exclude")
    if not os.path.exists(exclude):
        return []
    trees = [line.split(" ", 1)[1] for line in _git("-C", root, "worktree", "list", "--porcelain").splitlines()
             if line.startswith("worktree ")]
    found = []
    for tree in trees:
        if not os.path.isdir(tree):          # a worktree removed without `git worktree prune`
            continue
        listed = _git("-C", tree, "ls-files", "-z", "--others", "--ignored", f"--exclude-from={exclude}")
        found += [(tree, rel) for rel in sorted(listed.split("\0"))
                  if rel and not rel.startswith(".claude/") and os.path.isfile(os.path.join(tree, rel))]
    return found


def pack_private(files, out):
    """tar the files (members `<worktree folder>/<path>`), zstd to out and
    test the archive."""
    raw = out[:-len(".zst")]
    try:
        with tarfile.open(raw, "w") as tar:
            for tree, rel in files:
                tar.add(os.path.join(tree, rel), arcname=f"{os.path.basename(tree)}/{rel}", recursive=False)
        subprocess.run(["zstd", "-q", "-T0", "-6", raw, "-o", out], check=True)
        subprocess.run(["zstd", "-q", "-t", out], check=True)
    finally:
        if os.path.exists(raw):
            os.remove(raw)


def archive_private(dest, stamp, keep_daily, keep_weekly, root=ROOT):
    """Pack private_files() to <dest>/private_files-<stamp>.tar.zst (0600)
    and rotate those archives like the DB ones. Returns (path, file count),
    (None, 0) when nothing is excluded. Raises on failure, partials removed."""
    files = private_files(root)
    if not files:
        return None, 0
    partial = os.path.join(dest, f".partial-{stamp}.tar.zst")
    final = os.path.join(dest, f"{PRIVATE_PREFIX}{stamp}.tar.zst")
    try:
        pack_private(files, partial)
        os.chmod(partial, 0o600)
        os.rename(partial, final)
    finally:
        if os.path.exists(partial):
            os.remove(partial)
    found = backups(dest, PRIVATE_NAME)
    keep = to_keep([s for s, _ in found], keep_daily, keep_weekly)
    for stamp_, path in found:
        if stamp_ not in keep:
            os.remove(path)
    return final, len(files)


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


def newest_offsite(client, bucket, prefix=PREFIX, pattern=_NAME):
    """Upload time (naive UTC) of the newest archive in the bucket (DB
    archives by default), or None."""
    newest = None
    for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            if pattern.match(obj["Key"]) and (newest is None or obj["LastModified"] > newest):
                newest = obj["LastModified"]
    return newest.astimezone(timezone.utc).replace(tzinfo=None) if newest else None


def backup_database(db, dest, stamp, keep_daily, keep_weekly):
    """The DB archive: snapshot, check, compress, verify, rename, rotate.
    Exits 1 on failure with its partials removed. Returns the archive path."""
    raw = os.path.join(dest, f".partial-{stamp}.db")
    packed = os.path.join(dest, f".partial-{stamp}.db.zst")
    final = os.path.join(dest, f"{PREFIX}{stamp}.db.zst")

    started = time.monotonic()
    try:
        verdict = snapshot(db, raw)
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

    found = backups(dest)
    keep = to_keep([s for s, _ in found], keep_daily, keep_weekly)
    dropped = [p for s, p in found if s not in keep]
    for path in dropped:
        os.remove(path)

    size_mb = os.path.getsize(final) / 1e6
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S} backup ok: {final} "
          f"({size_mb:,.0f} MB; copy+check {copied - started:.0f}s, "
          f"total {time.monotonic() - started:.0f}s); "
          f"{len(found) - len(dropped)} kept, {len(dropped)} rotated out")
    return final


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--dest", default=DEFAULT_DEST)
    ap.add_argument("--env-file", default=DEFAULT_ENV)
    ap.add_argument("--keep-daily", type=int, default=7)
    ap.add_argument("--keep-weekly", type=int, default=4)
    ap.add_argument("--no-offsite", action="store_true", help="skip the R2 upload")
    ap.add_argument("--private-only", action="store_true",
                    help="only archive (and upload) the files .git/info/exclude keeps out of git")
    args = ap.parse_args()
    load_dotenv(args.env_file)

    os.makedirs(args.dest, exist_ok=True)
    os.chmod(args.dest, 0o700)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    archives = []
    if not args.private_only:
        archives.append(backup_database(args.db, args.dest, stamp, args.keep_daily, args.keep_weekly))

    private_failed = False
    try:
        private, count = archive_private(args.dest, stamp, args.keep_daily, args.keep_weekly)
        if private:
            archives.append(private)
            print(f"  private files: {private} ({count} files, {os.path.getsize(private) / 1e3:,.0f} KB)")
        else:
            print("  private files: none excluded, nothing to archive")
    except Exception as exc:
        print(f"  private files FAILED: {type(exc).__name__}: {exc}")
        private_failed = True

    if not args.no_offsite:
        try:
            r2 = r2_client()
            if r2 is None:
                print("  off-site: skipped, no R2 settings")
            for path in archives if r2 else []:
                sent = time.monotonic()
                key = upload_offsite(*r2, path)
                print(f"  off-site: r2://{r2[1]}/{key} ok ({time.monotonic() - sent:.0f}s)")
        except Exception as exc:
            print(f"  off-site upload FAILED (local backup kept): {type(exc).__name__}: {exc}")
            sys.exit(1)
    if private_failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
