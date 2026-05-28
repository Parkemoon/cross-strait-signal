"""MAC poll scraper — Phase 2d pollster-direct ingestion (structured PDF).

MAC (大陸委員會) commissions Ipsos 即時民調 "民眾對兩岸相關議題之看法"
surveys (~quarterly) and publishes each release on its news site as a
News_Content page carrying three PDFs: 新聞稿 (press release), 結果摘要
(summary), and 配布表 (full distribution table). Only the 配布表 carries
machine-readable per-option percentages, so that is the one we parse.

Unlike TVBS/My-Formosa (prose → Step 3c AI extraction), MAC publishes
clean structured tables, so we parse deterministically with pdfplumber
and write straight to polls/poll_results as approved — the same trusted-
source pattern as the NCCU backfill. Question→canonical-key mapping is
config-driven (scraper/processors/mac_poll_questions.json), keyed on a
distinctive substring of each question, so re-runs of the recurring
battery auto-map and unrecognised questions are flagged, never guessed.

Binary-with-intensity questions are stored as the 3-option aggregate
(positive / negative / no-response) per the aggregate-vs-intensity rule
in .claude/rules/ai-pipeline.md — MAC prints that aggregate row directly
beneath the 4-point breakdown, so we read it rather than re-summing.
Multi-option questions (e.g. who is undermining strait peace) preserve
every option.

Discovery: MAC's 最新消息 listing mixes polls with statements and
condolences, so poll releases are identified by the presence of a 配布表
attachment (only poll releases carry one) rather than by title keywords.
"""
import io
import json
import os
import re
import sys
from datetime import datetime, timezone

import httpx
import pdfplumber

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from scraper.utils.db import get_connection

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

LIST_URL = 'https://www.mac.gov.tw/News.aspx?n=05B73310C5C3A632&sms=1A40B00E4C745211'
_QUESTION_MAP_PATH = os.path.join(
    os.path.dirname(__file__), '..', 'processors', 'mac_poll_questions.json')
_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
}
_NOOP_ZH = '未明確回答'
_NOOP_EN = 'No response'

# A 配布表 attachment block looks like:
#   <div class="hd">...<a title="...配布表">...</a></div>
#   <div class="ct">...<a href="https://ws.mac.gov.tw/.../<uuid>.pdf">pdf</a></div>
# inside one `file-download-multiple` <li>. Match the labelled block, then
# pull the PDF href that follows it.
_DOWNLOAD_BLOCK_RE = re.compile(
    r'file-download-multiple.*?title="([^"]*)".*?(https://ws\.mac\.gov\.tw/[^"\']*?\.pdf)',
    re.S)


def _load_question_map():
    with open(_QUESTION_MAP_PATH, encoding='utf-8') as f:
        return json.load(f)['questions']


def _fetch_text(url):
    with httpx.Client(timeout=30, follow_redirects=True, headers=_HEADERS) as client:
        r = client.get(url)
        r.raise_for_status()
        return r.text


def _fetch_bytes(url):
    with httpx.Client(timeout=60, follow_redirects=True, headers=_HEADERS) as client:
        r = client.get(url)
        r.raise_for_status()
        return r.content


def _strip_tags(s):
    return re.sub(r'<[^>]+>', '', s).strip()


def find_distribution_pdf(html):
    """Return (page_title, distribution_pdf_url) from a News_Content page,
    or (title, None) if the page has no 配布表 attachment (i.e. not a poll)."""
    title = None
    for m in re.finditer(r'<(h1|h2|h3)[^>]*>(.*?)</\1>', html, re.S):
        t = _strip_tags(m.group(2))
        # The release headline is the last/most-specific heading; skip the
        # standing 大陸委員會 / 最新消息 chrome headings.
        if t and t not in ('大陸委員會', '最新消息'):
            title = t
    pdf_url = None
    for label, url in _DOWNLOAD_BLOCK_RE.findall(html):
        if '配布表' in label:
            pdf_url = url
            break
    return title, pdf_url


def _pct(s):
    return float(str(s).strip().rstrip('%'))


def _roc_to_iso(roc_year, month, day):
    return f"{roc_year + 1911:04d}-{int(month):02d}-{int(day):02d}"


def _parse_fielded(text):
    """調查日期：115 年 5 月 22 日至 23 日、25 日至 26 日 → ('2026-05-22','2026-05-26').
    Day-only tokens inherit the most recent month."""
    line_m = re.search(r'調查日期[：:]\s*(.+)', text)
    line = line_m.group(1) if line_m else text
    year_m = re.search(r'(\d{2,3})\s*年', line)
    if not year_m:
        return None, None
    roc = int(year_m.group(1))
    pairs, last_month = [], None
    for m in re.finditer(r'(?:(\d{1,2})\s*月\s*)?(\d{1,2})\s*日', line):
        if m.group(1):
            last_month = int(m.group(1))
        if last_month is None:
            continue
        pairs.append((last_month, int(m.group(2))))
    if not pairs:
        return None, None
    return _roc_to_iso(roc, *pairs[0]), _roc_to_iso(roc, *pairs[-1])


def _parse_questions(pdf):
    """Return [{'text_zh': <whitespace-stripped>, 'table': <cell grid>}] for
    the substantive questions only — stops at the 基本資料 demographics page.
    A question line starts with `N. ` (digit-dot-space); percentage rows like
    `1.1%` start digit-dot-digit, so the `\\s` after the dot disambiguates."""
    out = []
    for page in pdf.pages:
        txt = page.extract_text() or ''
        if '基本資料' in txt:
            break
        starts = [m.start() for m in re.finditer(r'(?m)^\s*\d+\.\s', txt)]
        tables = page.extract_tables()
        qtexts = []
        for pos in starts:
            qmark = re.search(r'[？?]', txt[pos:])
            if not qmark:
                continue
            raw = txt[pos:pos + qmark.end()]
            raw = re.sub(r'^\s*\d+\.\s*', '', raw)
            qtexts.append(re.sub(r'\s+', '', raw))
        if len(qtexts) != len(tables):
            print(f"    WARNING: page has {len(qtexts)} questions but "
                  f"{len(tables)} tables — skipping page to avoid misalignment")
            continue
        for zh, tbl in zip(qtexts, tables):
            out.append({'text_zh': zh, 'table': tbl})
    return out


def _options_from_table(tbl, mapentry):
    """Turn a distribution table into [(label_zh, label_en, pct, order)].

    Binary-with-intensity (5-col header, 3 rows, aggregate row carries None
    in the intensity columns) → 3-option aggregate (positive/negative/no-op).
    Multi-option (2 rows) → every column preserved.
    The no-opinion column is always last in MAC's tables."""
    header = tbl[0]
    is_binary = len(tbl) >= 3 and any(c is None for c in tbl[-1])
    if is_binary:
        vals = [c for c in tbl[-1] if c is not None]  # [positive, negative, no-op]
        return [
            (header[1], mapentry['positive_en'], _pct(vals[0]), 0),
            (header[2], mapentry['negative_en'], _pct(vals[1]), 1),
            (_NOOP_ZH, _NOOP_EN, _pct(vals[2]), 2),
        ]
    pcts = tbl[1]
    opts_en = mapentry.get('options_en', {})
    last = len(header) - 1
    out = []
    for i, (lab, pct) in enumerate(zip(header, pcts)):
        if pct is None:
            continue
        if i == last:  # 不知道/無意見
            out.append((_NOOP_ZH, _NOOP_EN, _pct(pct), i))
        else:
            out.append((lab, opts_en.get(lab, lab), _pct(pct), i))
    return out


def parse_distribution_pdf(pdf_bytes):
    """Parse a 配布表 PDF into a structured dict (no DB access)."""
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        head = pdf.pages[0].extract_text() or ''
        fielded_start, fielded_end = _parse_fielded(head)
        sample_m = re.search(r'樣\s*本\s*數\s*[：:]\s*([\d,]+)', head)
        moe_m = re.search(r'抽樣誤差\s*[：:]\s*±?\s*([\d.]+)', head)
        conductor_m = re.search(r'調查單位\s*[：:]\s*(\S+)', head)
        questions = _parse_questions(pdf)
    return {
        'fielded_start': fielded_start,
        'fielded_end': fielded_end,
        'sample_size': int(sample_m.group(1).replace(',', '')) if sample_m else None,
        'margin_error': float(moe_m.group(1)) if moe_m else None,
        'conductor': conductor_m.group(1) if conductor_m else None,
        'questions': questions,
    }


def _match_question(zh, qmap):
    for entry in qmap:
        if entry['match'] in zh:
            return entry
    return None


def _ensure_question(conn, entry, text_zh):
    conn.execute(
        """INSERT OR IGNORE INTO poll_questions
               (question_key, question_text_zh, question_text_en, family, scale_type)
           VALUES (?, ?, ?, ?, ?)""",
        (entry['question_key'], text_zh, entry['text_en'],
         entry['family'], entry['scale_type']))
    row = conn.execute("SELECT id FROM poll_questions WHERE question_key = ?",
                       (entry['question_key'],)).fetchone()
    return row['id']


def ingest_mac_poll_page(news_url, html=None):
    """Ingest one MAC poll release (a News_Content page URL).

    Returns a short status dict. Idempotent on (pollster_id, source_url)."""
    conn = get_connection()
    try:
        pollster = conn.execute(
            "SELECT id FROM pollsters WHERE slug = 'mac'").fetchone()
        if not pollster:
            print("  MAC pollster not found — run seed_sources.py first")
            return {'status': 'error', 'reason': 'no_pollster'}
        pollster_id = pollster['id']

        existing = conn.execute(
            "SELECT id FROM polls WHERE pollster_id = ? AND source_url = ?",
            (pollster_id, news_url)).fetchone()
        if existing:
            return {'status': 'skipped', 'reason': 'already_ingested',
                    'poll_id': existing['id']}

        if html is None:
            html = _fetch_text(news_url)
        title, pdf_url = find_distribution_pdf(html)
        if not pdf_url:
            return {'status': 'skipped', 'reason': 'no_distribution_pdf'}

        parsed = parse_distribution_pdf(_fetch_bytes(pdf_url))
        if not parsed['fielded_start'] or not parsed['questions']:
            return {'status': 'error', 'reason': 'parse_empty'}

        qmap = _load_question_map()
        resolved, unmapped = [], []
        for q in parsed['questions']:
            entry = _match_question(q['text_zh'], qmap)
            if entry:
                resolved.append((entry, q))
            else:
                unmapped.append(q['text_zh'][:40])
        if not resolved:
            return {'status': 'error', 'reason': 'no_questions_mapped',
                    'unmapped': unmapped}

        moe = f"±{parsed['margin_error']}%" if parsed['margin_error'] else 'n/a'
        conductor = parsed['conductor'] or '益普索'
        methodology = (
            f"委託：大陸委員會；調查：{conductor}；樣本數 {parsed['sample_size']}；"
            f"抽樣誤差 {moe}；調查期間 {parsed['fielded_start']}～{parsed['fielded_end']}。"
            f"即時民調「民眾對兩岸相關議題之看法」。")

        cur = conn.execute(
            """INSERT INTO polls
                   (pollster_id, fielded_start, fielded_end, sample_size,
                    methodology_note, source_url, notes,
                    approval_status, reviewed_by, reviewed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'approved', 'scraper:mac_poll', ?)""",
            (pollster_id, parsed['fielded_start'], parsed['fielded_end'],
             parsed['sample_size'], methodology, news_url, title,
             datetime.now(timezone.utc).isoformat()))
        poll_id = cur.lastrowid

        n_results = 0
        for entry, q in resolved:
            qid = _ensure_question(conn, entry, q['text_zh'])
            for label_zh, label_en, pct, order in _options_from_table(q['table'], entry):
                conn.execute(
                    """INSERT INTO poll_results
                           (poll_id, question_id, option_label_zh, option_label_en,
                            option_order, percentage)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (poll_id, qid, label_zh, label_en, order, pct))
                n_results += 1

        conn.commit()
        return {'status': 'ingested', 'poll_id': poll_id, 'title': title,
                'questions': len(resolved), 'results': n_results,
                'unmapped': unmapped}
    finally:
        conn.close()


def scrape_mac_polls():
    """Enumerate MAC's 最新消息 listing, ingest any poll release (one carrying
    a 配布表 attachment) not already in the DB. Run-pipeline entry point."""
    print("\nScraping: MAC 即時民調")
    try:
        listing = _fetch_text(LIST_URL)
    except Exception as e:
        print(f"  listing fetch failed — {e}")
        return 0

    urls, seen = [], set()
    for m in re.finditer(r'href="([^"]*News_Content\.aspx[^"]*)"', listing):
        href = m.group(1)
        if href.startswith('/'):
            href = 'https://www.mac.gov.tw' + href
        if 'News_Content' in href and href not in seen:
            seen.add(href)
            urls.append(href)
    print(f"  Found {len(urls)} releases on listing")

    new_count = 0
    for url in urls:
        try:
            res = ingest_mac_poll_page(url)
        except Exception as e:
            print(f"    {url}: ingest failed — {e}")
            continue
        if res['status'] == 'ingested':
            new_count += 1
            print(f"  New poll: {res['title'][:60]} "
                  f"({res['questions']} q, {res['results']} rows)")
            if res.get('unmapped'):
                print(f"    unmapped questions skipped: {res['unmapped']}")
    print(f"  Ingested {new_count} new MAC polls")
    return new_count


if __name__ == '__main__':
    if len(sys.argv) > 1:
        print(json.dumps(ingest_mac_poll_page(sys.argv[1]), ensure_ascii=False, indent=2))
    else:
        scrape_mac_polls()
