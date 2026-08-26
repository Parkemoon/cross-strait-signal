"""Taiwan Coast Guard Administration enforcement statistics (Phase 2e, Part B).

The mirror series for the Coast Guard tracker: PRC vessels Taiwan's CGA
EXPELLED (驅離) and DETAINED (扣留) for trespass fishing, by month and by
county. Source: the CGA's monthly 績效統計月報, chapter 捌 取締非法越區捕魚 —
表8-1 (by month; annual rows back to 2013 + each month of the current year)
and 表8-3 (by county: 金門縣 / 連江縣 / 澎湖縣 / …, year-to-date). Deterministic
pdfplumber parse, no AI, no review gate (official statistics).

Discovery: the CGA site's monthly index node 404s to plain HTTP clients, but
the homepage sidebar links the latest ~5 reports as
`lp?ctNode=<id>&mp=999` with title "<ROC year>年<MM>月績效統計月報"; each report
page links chapter pages `ct?xItem=<id>&ctNode=<node>`, which link the table
PDFs under public/Attachment/. Yearbooks (`<ROC year>年海巡統計年報`) share the
chapter/table layout and feed the annual backfill.

Parsing: pdfplumber finds the header grid but the data rows fall outside it,
and extract_text() splits digits ("1 ,141"). So: take the column x-edges from
the union of the header cells, then bucket each word of each body line by its
x-centre and join. Labels are two lines (Chinese then English) with the
numbers on either — stitch by carrying the last Chinese label forward.
Same pdfplumber-table idiom as mac_poll_scraper.py.

⚑ Known gaps: the 2026-layout 表11-1 has no separate 取締越界非捕魚船舶
(dredger) column — dredgers are not captured; pre-2025 monthly reports were a
single narrative PDF (海巡績效統計概況) whose Table 8 this parser has not been
tested against.
"""
from __future__ import annotations

import io
import re
import sys
from typing import Iterable

import httpx
import pdfplumber

from scraper.utils.db import get_connection

BASE = "https://www.cga.gov.tw/GipOpen/wSite/"
HOME = BASE + "mp?mp=999"
UA = "cross-strait-signal/1.0 (+https://strait-signal.net; open-source OSINT dashboard)"

MONTHLY_RE = re.compile(r'href="(lp\?ctNode=(\d+)&mp=999[^"]*)"[^>]*title="(\d{3})年(\d{2})月績效統計月報"')
YEARBOOK_RE = re.compile(r'href="(lp\?ctNode=(\d+)&mp=999[^"]*)"[^>]*title="(\d{3})年海巡統計年報"')
CHAPTER_RE = re.compile(r'href="(ct\?xItem=(\d+)&ctNode=(\d+)&mp=999)"[^>]*title="([^"]*)"')
ATTACH_RE = re.compile(r'href="(public/Attachment/(f\d+)\.pdf)"[^>]*title="([^"]*)"')

CHAPTER_FISHING = "取締非法越區捕魚"
TABLE_BY_MONTH = "表8-1"
TABLE_BY_COUNTY = "表8-3"

# 表8-1 / 表8-3 leaf columns, left→right (14):
#   total: cases, vessels, prc, foreign, stateless
#   detention: cases, vessels, prc, foreign, stateless
#   expelling: cases, vessels, prc, foreign  (stateless col absent in the grid; appears as a 15th on some editions)
COL_NAMES = ["t_cases", "t_vessels", "t_prc", "t_foreign", "t_stateless",
             "d_cases", "d_vessels", "d_prc", "d_foreign", "d_stateless",
             "e_cases", "e_vessels", "e_prc", "e_foreign", "e_stateless"]

ROC_YEAR_RE = re.compile(r"^(\d{3})年")
# The yearbook prints its OWN year's annual row as a bare Gregorian year ("2025",
# no 年 prefix) — caught 2026-08-26: that row was skipped, so the months below it
# inherited report_year-1 and the 114 yearbook overwrote 2024 with 2025 values.
GREG_YEAR_RE = re.compile(r"^(20\d{2})$")
MONTH_RE = re.compile(r"^(\d{1,2})月")
COUNTY_RE = re.compile(r"^(總\s*計|全\s*國|[一-鿿]{2,3}(?:縣|市)|[一-鿿]+地區)")


def _client() -> httpx.Client:
    return httpx.Client(headers={"User-Agent": UA}, timeout=60.0, follow_redirects=True)


def _get(client: httpx.Client, path_or_url: str) -> str:
    url = path_or_url if path_or_url.startswith("http") else BASE + path_or_url
    r = client.get(url)
    r.raise_for_status()
    return r.text


def _get_bytes(client: httpx.Client, path: str) -> bytes:
    r = client.get(BASE + path)
    r.raise_for_status()
    return r.content


# --- discovery -------------------------------------------------------------
def discover_reports(client: httpx.Client) -> tuple[list[dict], list[dict]]:
    """(monthly, yearbooks) linked from the homepage sidebar. Monthly items:
    {roc_year, year, month, node, path}; yearbooks: {roc_year, year, node, path}."""
    html = _get(client, HOME)
    monthly, seen = [], set()
    for path, node, ry, mm in MONTHLY_RE.findall(html):
        if node in seen:
            continue
        seen.add(node)
        monthly.append({"roc_year": int(ry), "year": int(ry) + 1911, "month": int(mm), "node": node, "path": path})
    yearbooks, seen = [], set()
    for path, node, ry in YEARBOOK_RE.findall(html):
        if node in seen:
            continue
        seen.add(node)
        yearbooks.append({"roc_year": int(ry), "year": int(ry) + 1911, "node": node, "path": path})
    monthly.sort(key=lambda m: (m["year"], m["month"]), reverse=True)
    yearbooks.sort(key=lambda y: y["year"], reverse=True)
    return monthly, yearbooks


def fishing_tables(client: httpx.Client, report_path: str) -> dict[str, str]:
    """{'表8-1': attachment path, '表8-3': ...} for one report (monthly or yearbook)."""
    html = _get(client, report_path)
    chapter = None
    for path, _x, _n, title in CHAPTER_RE.findall(html):
        if CHAPTER_FISHING in title:
            chapter = path
            break
    if not chapter:
        raise RuntimeError(f"chapter {CHAPTER_FISHING} not found in {report_path}")
    chtml = _get(client, chapter)
    out = {}
    for path, _fid, title in ATTACH_RE.findall(chtml):
        for key in (TABLE_BY_MONTH, TABLE_BY_COUNTY):
            if title.replace("　", " ").startswith(key) and key not in out:
                out[key] = path
    return out


# --- PDF parsing -------------------------------------------------------------
def _column_edges(table) -> list[tuple[float, float]]:
    xs = set()
    for row in table.rows:
        for cell in row.cells:
            if cell is not None:
                xs.add(round(cell[0], 1))
                xs.add(round(cell[2], 1))
    xs = sorted(xs)
    return [(xs[i], xs[i + 1]) for i in range(len(xs) - 1) if xs[i + 1] - xs[i] > 4]


def _num(s: str):
    s = s.replace(",", "").replace(" ", "").replace("ⓡ", "").replace("ⓟ", "").strip()
    if s in ("", "-", "－", "—", "…"):
        return 0
    try:
        return int(s)
    except ValueError:
        try:
            return float(s)
        except ValueError:
            return None


def parse_table(pdf_bytes: bytes) -> list[tuple[str, list]]:
    """[(chinese_label, [values per leaf column])] for the body rows of a CGA
    statistical table (表8-1 or 表8-3 layout)."""
    rows_out = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        page = pdf.pages[0]
        tables = page.find_tables()
        if not tables:
            return []
        t = tables[0]
        cols = _column_edges(t)
        header_bottom = t.rows[-1].bbox[3]
        words = page.extract_words(x_tolerance=1.5)
        body = [w for w in words if w["top"] > header_bottom - 2]
        lines: dict[int, list] = {}
        for w in body:
            lines.setdefault(round(w["top"] / 3), []).append(w)
        label_x1 = cols[0][0]
        carried = ""
        for key in sorted(lines):
            ws = sorted(lines[key], key=lambda w: w["x0"])
            label_words = [w["text"] for w in ws if w["x1"] <= label_x1 + 1]
            label = " ".join(label_words).strip()
            cells = []
            for (cx0, cx1) in cols:
                txt = "".join(w["text"] for w in ws if cx0 - 0.5 <= (w["x0"] + w["x1"]) / 2 <= cx1 + 0.5)
                cells.append(_num(txt))
            has_numbers = any(isinstance(v, (int, float)) and v != 0 for v in cells)
            zh = re.sub(r"[A-Za-z.()（）%％ⓡⓟ\-]+", " ", label).strip()
            zh = re.sub(r"\s+", "", zh)
            if zh:
                carried = zh
            if has_numbers and carried:
                rows_out.append((carried, cells))
    return rows_out


def _record(cells: list) -> dict | None:
    if len(cells) < 14:
        return None
    vals = dict(zip(COL_NAMES, cells + [0] * (15 - len(cells))))
    return vals


# --- ingest ------------------------------------------------------------------
def _categories(v: dict) -> list[dict]:
    return [
        {"category": "fishing_all", "cases": v["t_cases"], "expelled": v["e_vessels"], "detained": v["d_vessels"]},
        {"category": "fishing_prc", "cases": None, "expelled": v["e_prc"], "detained": v["d_prc"]},
        {"category": "fishing_foreign", "cases": None, "expelled": v["e_foreign"], "detained": v["d_foreign"]},
        {"category": "fishing_stateless", "cases": None, "expelled": v.get("e_stateless", 0), "detained": v["d_stateless"]},
    ]


def rows_by_month(pdf_bytes: bytes, report_year: int) -> list[dict]:
    """表8-1 → annual rows (period 'YYYY') + month rows of report_year ('YYYY-MM')."""
    out = []
    # 表8-1 lists annual rows (2013…), then the trailing months of the PREVIOUS
    # year, then the current year's annual row, then its months — so a month
    # row belongs to the most recent annual row above it, not the report year.
    # Early-year reports (Jan–May) print NO annual row for the new year, so the
    # month sequence simply wraps (… 11月 12月 1月 2月) — advance the year when
    # the month number goes backwards (caught 2026-08-25: 2025 Jan–May were
    # being overwritten with 2026 values).
    year_ctx = report_year - 1
    last_month = 0
    for label, cells in parse_table(pdf_bytes):
        v = _record(cells)
        if not v:
            continue
        m = ROC_YEAR_RE.match(label)
        g = GREG_YEAR_RE.match(label)
        if m or g:
            year_ctx = int(m.group(1)) + 1911 if m else int(g.group(1))
            last_month = 0
            period, gran = str(year_ctx), "year"
        else:
            m = MONTH_RE.match(label)
            if not m:
                continue
            month = int(m.group(1))
            if month <= last_month:
                year_ctx += 1
            last_month = month
            period, gran = f"{year_ctx}-{month:02d}", "month"
        for c in _categories(v):
            out.append({"period": period, "granularity": gran, "region": "TW", **c})
    return out


def rows_by_county(pdf_bytes: bytes, period: str, granularity: str) -> list[dict]:
    """表8-3 → per-county rows for the report's period (year-to-date for a
    monthly report; the full year for a yearbook)."""
    out = []
    for label, cells in parse_table(pdf_bytes):
        v = _record(cells)
        if not v:
            continue
        m = COUNTY_RE.match(label)
        if not m:
            continue
        region = m.group(1).replace(" ", "")
        if region in ("總計", "全國"):
            region = "TW"
        if region.endswith("地區"):
            continue  # regional subtotals — counties are enough
        for c in _categories(v):
            out.append({"period": period, "granularity": granularity, "region": region, **c})
    return out


def upsert(conn, rows: Iterable[dict], source: str, source_ref: str, source_url: str) -> int:
    n = 0
    for r in rows:
        conn.execute(
            """INSERT INTO cga_enforcement (period, granularity, region, category, cases, expelled, detained,
                                            source, source_ref, source_url)
               VALUES (:period, :granularity, :region, :category, :cases, :expelled, :detained, :source, :source_ref, :source_url)
               ON CONFLICT(period, granularity, region, category, source) DO UPDATE SET
                 cases=excluded.cases, expelled=excluded.expelled, detained=excluded.detained,
                 source_ref=excluded.source_ref, source_url=excluded.source_url, scraped_at=datetime('now')""",
            {**r, "source": source, "source_ref": source_ref, "source_url": source_url},
        )
        n += 1
    conn.commit()
    return n


def ingest_report(conn, client: httpx.Client, rep: dict, kind: str) -> int:
    """kind = 'monthly' | 'yearbook'."""
    tables = fishing_tables(client, rep["path"])
    label = (f"{rep['roc_year']}年{rep['month']:02d}月績效統計月報" if kind == "monthly"
             else f"{rep['roc_year']}年海巡統計年報")
    n = 0
    if TABLE_BY_MONTH in tables:
        pdf = _get_bytes(client, tables[TABLE_BY_MONTH])
        rows = rows_by_month(pdf, rep["year"])
        n += upsert(conn, rows, kind, f"{label} {TABLE_BY_MONTH}", BASE + tables[TABLE_BY_MONTH])
    if TABLE_BY_COUNTY in tables:
        pdf = _get_bytes(client, tables[TABLE_BY_COUNTY])
        if kind == "monthly":
            # 表8-3 in a monthly report is a YEAR-TO-DATE snapshot through the
            # report month (not that month's delta). It is keyed by the report
            # month so consumers can pick the newest snapshot per year; the
            # yearbook's 表8-3 (full year, granularity 'year') is the final word.
            rows = rows_by_county(pdf, f"{rep['year']}-{rep['month']:02d}", "month")
        else:
            rows = rows_by_county(pdf, str(rep["year"]), "year")
        n += upsert(conn, rows, kind, f"{label} {TABLE_BY_COUNTY}", BASE + tables[TABLE_BY_COUNTY])
    return n


def _already_have(conn, rep: dict) -> bool:
    ref = f"{rep['roc_year']}年{rep['month']:02d}月績效統計月報"
    return conn.execute("SELECT 1 FROM cga_enforcement WHERE source_ref LIKE ? LIMIT 1", (ref + "%",)).fetchone() is not None


def scrape_cga_stats(db_path: str | None = None, force: bool = False) -> int:
    """Pipeline entry point: ingest every monthly report linked from the
    homepage that we haven't stored yet (normally 0 or 1 per month)."""
    conn = get_connection(db_path)
    total = 0
    with _client() as client:
        monthly, _ = discover_reports(client)
        for rep in monthly:
            if not force and _already_have(conn, rep):
                continue
            try:
                n = ingest_report(conn, client, rep, "monthly")
                print(f"  [cga] {rep['roc_year']}年{rep['month']:02d}月: {n} rows")
                total += n
            except Exception as e:  # noqa: BLE001
                print(f"  [cga] {rep['roc_year']}年{rep['month']:02d}月 FAILED: {type(e).__name__}: {e}", file=sys.stderr)
    conn.close()
    return total
