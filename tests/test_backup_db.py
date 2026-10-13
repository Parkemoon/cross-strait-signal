"""scripts/backup_db.py rotation, off-site copy and the archive of the
files kept out of git, and the three backup checks in
check_scraper_health.py."""
import os
import subprocess
import tarfile
from datetime import datetime, timedelta, timezone

import pytest

from scripts import backup_db
from scripts.backup_db import PREFIX, PRIVATE_NAME, PRIVATE_PREFIX, backups, to_keep
from scripts.check_scraper_health import backup_check, offsite_check, private_offsite_check


def nightly(days, start=datetime(2026, 9, 29, 2, 30)):
    """One stamp per night going back `days` nights, newest first."""
    return [start - timedelta(days=d) for d in range(days)]


def test_keeps_the_newest_dailies_and_one_per_recent_week():
    stamps = nightly(60)
    keep = to_keep(stamps, keep_daily=7, keep_weekly=4)
    assert set(stamps[:7]) <= keep
    weeks = {s.isocalendar()[:2] for s in keep}
    assert len(weeks) == 4                      # this week + the three before
    assert len(keep) == 7 + 2                   # dailies span 2 weeks; 2 older weekly picks
    for stamp in keep - set(stamps[:7]):        # weekly picks are each week's newest
        same_week = [s for s in stamps if s.isocalendar()[:2] == stamp.isocalendar()[:2]]
        assert stamp == max(same_week)


def test_few_backups_are_all_kept():
    stamps = nightly(3)
    assert to_keep(stamps, 7, 4) == set(stamps)


def test_backups_lists_only_finished_archives(tmp_path):
    for name in (f"{PREFIX}20260928-023000.db.zst", f"{PREFIX}20260929-023000.db.zst",
                 ".partial-20260930-023000.db", ".partial-20260930-023000.db.zst", "notes.txt"):
        (tmp_path / name).write_text("")
    found = backups(tmp_path)
    assert [s for s, _ in found] == [datetime(2026, 9, 29, 2, 30), datetime(2026, 9, 28, 2, 30)]


def test_backup_check_goes_stale_after_one_missed_night(tmp_path):
    (tmp_path / f"{PREFIX}20260929-023000.db.zst").write_text("")
    (tmp_path / ".partial-20260930-023000.db.zst").write_text("")   # a failed night
    assert backup_check(str(tmp_path), datetime(2026, 9, 29, 8, 15))["status"] == "ok"
    assert backup_check(str(tmp_path), datetime(2026, 9, 30, 8, 15))["status"] == "STALE"


def test_backup_check_with_no_backups_is_stale(tmp_path):
    assert backup_check(str(tmp_path / "missing"), datetime(2026, 9, 29, 8, 15))["status"] == "STALE"


# --- off-site copy (R2) ---------------------------------------------------------
R2_NAMES = ("R2_ENDPOINT", "R2_BUCKET", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY")


class FakeS3:
    """upload_file / head_object / list_objects_v2 paginator, in memory."""

    def __init__(self, truncate=0, objects=()):
        self.store, self.truncate = {}, truncate
        for key, when in objects:
            self.store[key] = (0, when)

    def upload_file(self, path, bucket, key):
        self.store[key] = (os.path.getsize(path) - self.truncate, datetime(2026, 9, 30, 2, 33))

    def head_object(self, Bucket, Key):
        return {"ContentLength": self.store[Key][0]}

    def get_paginator(self, name):
        store = self.store

        class Pages:
            def paginate(self, Bucket, Prefix):
                yield {"Contents": [{"Key": k, "LastModified": w.replace(tzinfo=timezone.utc)}
                                    for k, (_, w) in store.items() if k.startswith(Prefix)]}
        return Pages()


def test_r2_client_is_none_without_settings(monkeypatch):
    for name in R2_NAMES:
        monkeypatch.delenv(name, raising=False)
    assert backup_db.r2_client() is None


def test_r2_client_refuses_partial_settings(monkeypatch):
    for name in R2_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("R2_BUCKET", "b")
    with pytest.raises(RuntimeError, match="R2_ENDPOINT"):
        backup_db.r2_client()


def test_upload_confirms_every_byte(tmp_path):
    archive = tmp_path / f"{PREFIX}20260930-023000.db.zst"
    archive.write_bytes(b"x" * 100)
    assert backup_db.upload_offsite(FakeS3(), "b", str(archive)) == archive.name
    with pytest.raises(RuntimeError, match="99 bytes"):
        backup_db.upload_offsite(FakeS3(truncate=1), "b", str(archive))


def test_newest_offsite_ignores_other_objects():
    s3 = FakeS3(objects=[(f"{PREFIX}20260928-023000.db.zst", datetime(2026, 9, 28, 2, 35)),
                         (f"{PREFIX}20260929-023000.db.zst", datetime(2026, 9, 29, 2, 34)),
                         (f"{PREFIX}notes.txt", datetime(2026, 9, 30, 9, 0))])
    assert backup_db.newest_offsite(s3, "b") == datetime(2026, 9, 29, 2, 34)
    assert backup_db.newest_offsite(FakeS3(), "b") is None


def test_offsite_check_states(monkeypatch):
    now = datetime(2026, 9, 30, 8, 15)
    monkeypatch.setattr("scripts.check_scraper_health.r2_client", lambda: None)
    assert offsite_check(now)["status"] == "disabled"
    s3 = FakeS3(objects=[(f"{PREFIX}20260930-023000.db.zst", datetime(2026, 9, 30, 2, 34))])
    monkeypatch.setattr("scripts.check_scraper_health.r2_client", lambda: (s3, "b"))
    assert offsite_check(now)["status"] == "ok"
    assert offsite_check(datetime(2026, 10, 1, 8, 15))["status"] == "STALE"

    def broken():
        raise ConnectionError("down")
    monkeypatch.setattr("scripts.check_scraper_health.r2_client", broken)
    result = offsite_check(now)
    assert result["status"] == "STALE" and "ConnectionError" in result["note"]


# --- files kept out of git (.git/info/exclude) ----------------------------------
def _git(cwd, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
                   cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    """A repo plus a second worktree. The main one holds a tracked file, a
    .gitignore'd one, two info/exclude'd ones, a plain untracked one and a
    .claude/ state file; the second worktree its own copy of one excluded file."""
    main = tmp_path / "proj"
    main.mkdir()
    _git(main, "init", "-q")
    (main / "app.py").write_text("tracked")
    (main / ".gitignore").write_text("settings.env\n")
    _git(main, "add", ".")
    _git(main, "commit", "-q", "-m", "init")
    (main / ".git" / "info" / "exclude").write_text("tool.py\nnotes/\n**/.claude/state.json\n")
    for rel in ("tool.py", "notes/a.md", "settings.env", "scratch.txt", ".claude/state.json"):
        (main / rel).parent.mkdir(parents=True, exist_ok=True)
        (main / rel).write_text(rel)
    other = tmp_path / "proj-staging"
    _git(main, "worktree", "add", "-q", str(other))
    (other / "tool.py").write_text("staging copy")
    return main.resolve(), other.resolve()


def test_private_files_are_exactly_the_info_exclude_matches(repo):
    main, other = repo
    # not the tracked file, not the .gitignore'd settings file, not plain
    # untracked scratch, not Claude Code's state
    assert backup_db.private_files(str(main)) == [
        (str(main), "notes/a.md"), (str(main), "tool.py"), (str(other), "tool.py")]


def test_archive_private_packs_every_worktree(repo, tmp_path):
    main, _ = repo
    dest = tmp_path / "backups"
    dest.mkdir()
    path, count = backup_db.archive_private(str(dest), "20261013-023000", 7, 4, root=str(main))
    assert count == 3 and os.path.basename(path) == f"{PRIVATE_PREFIX}20261013-023000.tar.zst"
    assert os.stat(path).st_mode & 0o777 == 0o600
    assert os.listdir(dest) == [os.path.basename(path)]             # no partials left behind
    raw = tmp_path / "out.tar"
    subprocess.run(["zstd", "-q", "-d", path, "-o", str(raw)], check=True)
    with tarfile.open(raw) as tar:
        assert sorted(tar.getnames()) == ["proj-staging/tool.py", "proj/notes/a.md", "proj/tool.py"]
        assert tar.extractfile("proj-staging/tool.py").read() == b"staging copy"


def test_archive_private_rotates_only_its_own_archives(repo, tmp_path):
    main, _ = repo
    dest = tmp_path / "backups"
    dest.mkdir()
    for name in (f"{PRIVATE_PREFIX}20261011-023000.tar.zst", f"{PRIVATE_PREFIX}20261012-023000.tar.zst",
                 f"{PREFIX}20261011-023000.db.zst"):
        (dest / name).write_text("")
    backup_db.archive_private(str(dest), "20261013-023000", 1, 0, root=str(main))
    assert sorted(os.listdir(dest)) == [f"{PREFIX}20261011-023000.db.zst",
                                        f"{PRIVATE_PREFIX}20261013-023000.tar.zst"]
    assert [s for s, _ in backups(dest, PRIVATE_NAME)] == [datetime(2026, 10, 13, 2, 30)]
    assert [s for s, _ in backups(dest)] == [datetime(2026, 10, 11, 2, 30)]


def test_archive_private_with_nothing_excluded(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    _git(plain, "init", "-q")
    (plain / "scratch.txt").write_text("untracked, not excluded")
    assert backup_db.archive_private(str(tmp_path), "20261013-023000", 7, 4, root=str(plain)) == (None, 0)


def test_private_offsite_check_states(monkeypatch):
    now = datetime(2026, 10, 14, 8, 15)
    db_only = FakeS3(objects=[(f"{PREFIX}20261014-023000.db.zst", datetime(2026, 10, 14, 2, 34))])
    monkeypatch.setattr("scripts.check_scraper_health.r2_client", lambda: (db_only, "b"))
    assert private_offsite_check(now)["status"] == "STALE"         # a DB archive doesn't count
    both = FakeS3(objects=[(f"{PREFIX}20261014-023000.db.zst", datetime(2026, 10, 14, 2, 34)),
                           (f"{PRIVATE_PREFIX}20261014-023000.tar.zst", datetime(2026, 10, 14, 2, 35))])
    monkeypatch.setattr("scripts.check_scraper_health.r2_client", lambda: (both, "b"))
    assert private_offsite_check(now)["status"] == "ok"
    assert offsite_check(now)["status"] == "ok"
    monkeypatch.setattr("scripts.check_scraper_health.r2_client", lambda: None)
    assert private_offsite_check(now)["status"] == "disabled"
