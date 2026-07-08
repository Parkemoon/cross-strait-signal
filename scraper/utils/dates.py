"""Shared date helpers for scrapers (CODE_REVIEW_2026-07-03 §4.9).

ROC-calendar conversion was copied in six scrapers (mac_economic,
mac_macro, mac_poll, mnd_incursion, tw_nia_population, trade_access) and
URL-date extraction in three (guancha, fjsen, taiwan_cn). The primitives
live here; scrapers keep their source-specific parsing around them
(mac_macro's month-range handling, mac_economic's YTD guards, etc.).
"""
import re
from datetime import datetime, timezone

# Minguo epoch: ROC year 1 = 1912, so Gregorian = ROC + 1911.
ROC_YEAR_OFFSET = 1911

_ROC_LABEL_RE = re.compile(r'^\s*(\d{1,3})年')


def roc_year_to_gregorian(roc_year):
    """ROC year (int or numeric str) → Gregorian year int."""
    return int(roc_year) + ROC_YEAR_OFFSET


def roc_date_to_iso(roc_year, month, day):
    """(ROC year, month, day) → 'YYYY-MM-DD'. Accepts ints or numeric strs."""
    return f"{roc_year_to_gregorian(roc_year):04d}-{int(month):02d}-{int(day):02d}"


def roc_label_year(label):
    """ROC year label like '112年' (optionally with a suffix) → 2023, or
    None when the label doesn't start with a ROC year."""
    m = _ROC_LABEL_RE.match(label or '')
    if not m:
        return None
    return roc_year_to_gregorian(m.group(1))


def roc_compact_to_iso(roc):
    """Compact ROC date like '1021129' or '970319' → '2013-11-29' /
    '2008-03-19', or None when unparseable. ROC years are 3-digit since
    100 (=2011); anything shorter is 2-digit."""
    if not roc:
        return None
    s = str(roc).strip()
    if not s.isdigit():
        return None
    if len(s) == 7:
        year, month, day = roc_year_to_gregorian(s[:3]), int(s[3:5]), int(s[5:7])
    elif len(s) == 6:
        year, month, day = roc_year_to_gregorian(s[:2]), int(s[2:4]), int(s[4:6])
    else:
        return None
    return f'{year:04d}-{month:02d}-{day:02d}'


def parse_url_date(url, pattern):
    """Extract a published date from a URL via a regex with (year, month,
    day) groups. Returns an ISO datetime string (UTC midnight) or None
    when the pattern doesn't match / the date is invalid — callers decide
    their own fallback (guancha/fjsen deliberately stamp now() so an
    unmatched URL still gets a feed position; that choice stays visible
    at the call site instead of hiding in a shared default)."""
    m = re.search(pattern, url or '')
    if not m:
        return None
    try:
        return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                        tzinfo=timezone.utc).isoformat()
    except ValueError:
        return None
