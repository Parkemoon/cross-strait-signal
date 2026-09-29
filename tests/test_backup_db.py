"""scripts/backup_db.py rotation and off-site copy, and the two backup
checks in check_scraper_health.py."""
import os
from datetime import datetime, timedelta, timezone

import pytest

from scripts import backup_db
from scripts.backup_db import PREFIX, backups, to_keep
from scripts.check_scraper_health import backup_check, offsite_check


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
