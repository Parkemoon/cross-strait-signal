"""scripts/backup_db.py rotation and check_scraper_health.py's backup check."""
from datetime import datetime, timedelta

from scripts.backup_db import PREFIX, backups, to_keep
from scripts.check_scraper_health import backup_check


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
