#!/usr/bin/env python3
"""Pull portraits for people appearing in the Visits timeline.

Scans `cross_strait_visits` (approved rows by default) for named people on
both sides of each visit, resolves each name against Wikidata (with a
Chinese-Wikipedia fallback), and — in --apply mode — downloads the portrait
into `frontend/public/figures/visits/` plus a `manifest.json` the frontend
joins on by name. The manifest and images are committed like the
hand-curated key-figure portraits: review the diff, then commit and deploy.

Portrait sources, in order:
  1. Wikidata P18 (Commons image on the matched item);
  2. the matched item's zh-Wikipedia article lead/infobox image (covers
     items whose P18 is missing but whose zh article has a photo) — only
     when the file's licence is free (CC / public domain / GFDL; zh-wiki
     fair-use uploads are rejected);
  3. official party-site officer pages (`PARTY_SITES` — currently the KMT's
     黨務主管 / 中常委 / 副秘書長 grids on www1.kmt.org.tw, which carry one
     photo per officer with the name in the `alt`) — exact zh-name match
     against that grid. These are NOT free-licensed; they are the party's
     own press portraits published for public identification, used as such
     with a "Photo: <party> official site" attribution (Ed's call,
     2026-09-02). Add a site = one `PARTY_SITES` entry + a parser;
  4. `--manual "名字=https://…"` for a one-off URL the analyst has vetted
     (attribution derived from the host);
  5. nothing auto-pulled from Baidu Baike — Baike images are unlicensed, so
     the report prints a Baike lead URL per unresolved person for manual
     sourcing instead.

Matching is deliberately conservative — a wrong face on a named official is
the same credibility class as a misattributed quote:
  * the queried name must EXACTLY equal a zh-variant label/alias (or the
    English label for en-only rows) of the Wikidata item, or redirect to
    the zh-Wikipedia article linked to it;
  * the item must be a human (P31=Q5);
  * the item must look like a political actor: occupation (P106) in the
    politician/diplomat/civil-servant family, any position held (P39), or a
    politician-flavoured description;
  * if more than one candidate passes, NOBODY is auto-picked — the script
    prints the candidates and you rerun with --accept "名字=Q12345".

Key-figure ids that already carry a curated portrait are skipped (the
frontend prefers those anyway). Idempotent: existing manifest entries only
gain newly-seen name variants.

Usage:
  python scripts/fetch_visit_portraits.py                 # dry-run report
  python scripts/fetch_visit_portraits.py --apply         # download + write
  python scripts/fetch_visit_portraits.py --accept "洪秀柱=Q700313" --apply
  python scripts/fetch_visit_portraits.py --manual "連勝武=https://image.kmt.org.tw/people/x.jpg" --apply
  python scripts/fetch_visit_portraits.py --db /var/www/cross-strait-signal/db/cross_strait_signal.db
"""

import argparse
import hashlib
import json
import re
import sqlite3
import sys
import time
import urllib.parse
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "db" / "cross_strait_signal.db"
FIGURES_DIR = ROOT / "frontend" / "public" / "figures"
VISITS_DIR = FIGURES_DIR / "visits"
MANIFEST = VISITS_DIR / "manifest.json"
KEY_FIGURES = ROOT / "scraper" / "processors" / "key_figures.json"

WD_API = "https://www.wikidata.org/w/api.php"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
ZHWIKI_API = "https://zh.wikipedia.org/w/api.php"
UA = {"User-Agent": "CrossStraitSignal/1.0 (portrait fetch; contact: aeninon@gmail.com)"}
THUMB_WIDTH = 512
SLEEP = 0.4  # politeness between Wikimedia calls

# P106 occupations that read as "political actor"
POLITICAL_OCCUPATIONS = {
    "Q82955",    # politician
    "Q193391",   # diplomat
    "Q212238",   # civil servant
    "Q1097498",  # ruler/statesperson
    "Q189290",   # military officer
}
DESC_HINTS = re.compile(
    r"politician|political|minister|official|diplomat|legislat|mayor|magistrate|"
    r"party (?:chair|leader|official)|"
    r"政治|官員|官员|部長|部长|委員|委员|市長|市长|縣長|县长|主席|外交|立法|將領|将领",
    re.I,
)
FREE_LICENCE = re.compile(r"cc[- ]|creative commons|public domain|pd[- ]|gfdl|attribution", re.I)

# Names that are organisations, not people. The 2–4 char zh gate does most of
# the work; these catch English-only delegation rows.
ORG_WORDS = re.compile(
    r"delegation|association|government|committee|office|group|council|"
    r"department|ministry|university|forum|federation|chamber|company|party\b",
    re.I,
)
CJK = re.compile(r"^[一-鿿·]{2,4}$")

ZH_LANGS = ["zh", "zh-hans", "zh-hant", "zh-tw", "zh-cn", "zh-hk"]

# Official party sites whose officer pages carry one press portrait per person.
# Not free-licensed — the party's own public-identification photos, credited as
# such. `pages` are fetched lazily, only when a Wikimedia lookup has failed.
# Each parser yields (name_zh, image_url, page_url, stable_id).
KMT_PEOPLE_RE = re.compile(
    r'<a href="\?mid=(?P<mid>\d+)&(?:amp;)?pid=(?P<pid>\d+)">\s*'
    r'<img[^>]+src="(?P<src>https://image\.kmt\.org\.tw/people/[^"]+)"[^>]+alt="(?P<name>[^"]+)"',
)


def _parse_kmt(html, page_url):
    for m in KMT_PEOPLE_RE.finditer(html):
        yield (m.group("name").strip(), m.group("src"),
               f"https://www1.kmt.org.tw/people.aspx?mid={m.group('mid')}&pid={m.group('pid')}",
               m.group("pid"))


# TAO 机构设置 leadership block: <a href=PROFILE><img src=IMG></a> … <h3><a href=PROFILE title="吴 玺">
# Names carry an inner space when two characters long; the page is gb2312.
TAO_PEOPLE_RE = re.compile(
    r'<a href="(?P<profile>https?://www\.gwytb\.gov\.cn/jgsz/bld/(?P<slug>[a-z]+)/)"[^>]*>\s*'
    r'<img src="(?P<src>https://www\.gwytb\.gov\.cn/jgsz/bld/[^"]+)"[^>]*/?>\s*</a>(?:</a>)?\s*'
    r'<h3><a[^>]+title="(?P<name>[^"]+)"',
)


def _parse_tao(html, page_url):
    for m in TAO_PEOPLE_RE.finditer(html):
        name = re.sub(r"\s+", "", m.group("name"))
        yield (name, m.group("src"), m.group("profile"), m.group("slug"))


PARTY_SITES = {
    "kmt": {
        "label": "Kuomintang official site (kmt.org.tw)",
        "pages": [
            "https://www1.kmt.org.tw/people.aspx?mid=21",   # 黨務主管
            "https://www1.kmt.org.tw/people.aspx?mid=22",   # 中常委
            "https://www1.kmt.org.tw/people.aspx?mid=233",  # 副秘書長
        ],
        "parser": _parse_kmt,
    },
    "tao": {
        "label": "Taiwan Affairs Office official site (gwytb.gov.cn)",
        "pages": ["https://www.gwytb.gov.cn/jgsz/"],          # 机构设置 → 主任 / 副主任
        "encoding": "gb18030",                                # page declares gb2312
        "parser": _parse_tao,
    },
}
SITE_LICENCE = "Official site press portrait (not free-licensed; identification use)"
BROWSER_UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) CrossStraitSignal/1.0 portrait fetch"}
HOST_LABELS = {
    "kmt.org.tw": "Kuomintang official site (kmt.org.tw)",
    "dpp.org.tw": "Democratic Progressive Party official site (dpp.org.tw)",
    "tpp.org.tw": "Taiwan People's Party official site (tpp.org.tw)",
    "gwytb.gov.cn": "Taiwan Affairs Office (gwytb.gov.cn)",
    "mac.gov.tw": "Mainland Affairs Council (mac.gov.tw)",
    "ly.gov.tw": "Legislative Yuan (ly.gov.tw)",
}


def api_get(url, **params):
    params.setdefault("format", "json")
    r = requests.get(url, params=params, headers=UA, timeout=30)
    r.raise_for_status()
    time.sleep(SLEEP)
    return r.json()


def slugify(name_en, qid):
    if not name_en:
        return qid.lower()
    parts = re.sub(r"[^A-Za-z\s-]", "", name_en).lower().split()
    if not parts:
        return qid.lower()
    # match the existing convention: Cheng Li-wun -> cheng_liwun
    return "_".join(p.replace("-", "") for p in parts)


def looks_like_person(name_en, name_zh):
    if name_zh and CJK.match(name_zh):
        return True
    if name_zh:  # zh present but long / mixed → org
        return False
    return bool(name_en) and not ORG_WORDS.search(name_en) and len(name_en.split()) <= 4


def collect_people(db_path, include_pending):
    statuses = "('approved','pending')" if include_pending else "('approved')"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        f"""SELECT visitor_name_en   AS en, visitor_name_zh   AS zh, visitor_figure_id   AS fid
            FROM cross_strait_visits WHERE approval_status IN {statuses}
            UNION
            SELECT counterpart_name_en, counterpart_name_zh, counterpart_figure_id
            FROM cross_strait_visits WHERE approval_status IN {statuses}"""
    ).fetchall()
    conn.close()
    return [{"en": r["en"], "zh": r["zh"], "fid": r["fid"]}
            for r in rows if (r["en"] or r["zh"])]


def curated_portraits():
    """(ids, lowercased names+aliases) of key figures with a curated portrait.

    The name set catches DB rows whose figure_id never resolved (extracted
    before the figure joined key_figures.json) — without it such a row would
    re-download a duplicate portrait. Canonical names only, NOT aliases: the
    frontend resolver can fall back on exactly name_en/name_zh, so skipping
    on an alias spelling would leave that row with no portrait at all."""
    try:
        figs = json.loads(KEY_FIGURES.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return set(), set()
    with_portrait = [f for f in figs if f.get("portrait")]
    ids = {f["id"] for f in with_portrait}
    names = {n.strip().lower() for f in with_portrait
             for n in (f.get("name_en"), f.get("name_zh")) if n}
    return ids, names


def load_manifest():
    if MANIFEST.exists():
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    return {}


def manifest_name_index(manifest):
    idx = {}
    for qid, entry in manifest.items():
        for n in entry.get("names", []):
            idx[n.strip().lower()] = qid
    return idx


def search_candidates(name, lang):
    data = api_get(WD_API, action="wbsearchentities", search=name,
                   language=lang, uselang=lang, type="item", limit="10")
    return [hit["id"] for hit in data.get("search", [])]


def get_entities(qids):
    if not qids:
        return {}
    data = api_get(WD_API, action="wbgetentities", ids="|".join(qids[:20]),
                   props="labels|aliases|descriptions|claims|sitelinks",
                   languages="|".join(ZH_LANGS + ["en"]))
    return data.get("entities", {})


def claim_values(entity, prop):
    out = []
    for c in entity.get("claims", {}).get(prop, []):
        dv = c.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(dv, dict) and "id" in dv:
            out.append(dv["id"])
        elif isinstance(dv, str):
            out.append(dv)
    return out


def name_forms(entity, langs):
    forms = set()
    for lang in langs:
        lbl = entity.get("labels", {}).get(lang, {}).get("value")
        if lbl:
            forms.add(lbl)
        for a in entity.get("aliases", {}).get(lang, []):
            forms.add(a["value"])
    return forms


def is_political(entity):
    if set(claim_values(entity, "P106")) & POLITICAL_OCCUPATIONS:
        return True
    if entity.get("claims", {}).get("P39"):
        return True
    for lang in ("en", "zh"):
        desc = entity.get("descriptions", {}).get(lang, {}).get("value", "")
        if desc and DESC_HINTS.search(desc):
            return True
    return False


def zhwiki_pageimage(title):
    """Lead/infobox image filename for a zh-wiki article, or None."""
    data = api_get(ZHWIKI_API, action="query", titles=title, redirects="1",
                   converttitles="1", prop="pageimages", piprop="name")
    for page in data.get("query", {}).get("pages", {}).values():
        if "missing" in page:
            continue
        name = page.get("pageimage")
        if name:
            return f"File:{name}" if not name.startswith("File:") else name
    return None


def zhwiki_item_for_title(title):
    """(wikibase QID, pageimage filename) for an exact/redirected zh title."""
    data = api_get(ZHWIKI_API, action="query", titles=title, redirects="1",
                   converttitles="1", prop="pageprops|pageimages",
                   ppprop="wikibase_item", piprop="name")
    for page in data.get("query", {}).get("pages", {}).values():
        if "missing" in page:
            continue
        qid = page.get("pageprops", {}).get("wikibase_item")
        img = page.get("pageimage")
        return qid, (f"File:{img}" if img and not img.startswith("File:") else img)
    return None, None


def image_ref_for(entity):
    """('commons'|'zhwiki', 'File:…') or (None, reason)."""
    p18 = claim_values(entity, "P18")
    if p18:
        return "commons", f"File:{p18[0]}"
    sitelink = entity.get("sitelinks", {}).get("zhwiki", {}).get("title")
    if sitelink:
        img = zhwiki_pageimage(sitelink)
        if img:
            return "zhwiki", img
        return None, "no P18 and the zh-wiki article has no lead image"
    return None, "no P18 and no zh-wiki article"


def entity_passes(entity, name, match_langs):
    if "Q5" not in claim_values(entity, "P31"):
        return False
    fold = {f.lower() for f in name_forms(entity, match_langs)}
    if name.lower() not in fold:
        return False
    return is_political(entity)


def resolve(name_zh, name_en, accepts):
    """Return (qid, entity, image_ref, note); qid None when unresolved.

    When a single item matched but carries no usable image, `entity` is still
    returned (qid None) so callers can reuse its name forms — e.g. the
    simplified spelling a PRC official site lists under."""
    forced = accepts.get(name_zh) or accepts.get(name_en)
    if forced:
        ents = get_entities([forced])
        if forced in ents:
            src, ref = image_ref_for(ents[forced])
            if src:
                return forced, ents[forced], (src, ref), "forced via --accept"
            return None, ents[forced], None, f"--accept {forced}: {ref}"
        return None, None, None, f"--accept {forced}: item not found"

    tried, imageless = [], None
    for name, langs in ((name_zh, ["zh", "zh-tw"]), (name_en, ["en"])):
        if not name:
            continue
        qids = []
        for lang in langs:
            for q in search_candidates(name, lang):
                if q not in qids:
                    qids.append(q)
        # zh fallback: exact zh-wiki title (redirect-aware, catches names the
        # entity search misses because the item lacks that alias)
        wiki_qid = None
        if name is name_zh:
            wiki_qid, _ = zhwiki_item_for_title(name)
            if wiki_qid and wiki_qid not in qids:
                qids.append(wiki_qid)
        if not qids:
            tried.append(f"'{name}': no search hits")
            continue
        ents = get_entities(qids)
        match_langs = ZH_LANGS if name is name_zh else ["en"]
        passed = []
        for qid in qids:
            e = ents.get(qid)
            if not e:
                continue
            if entity_passes(e, name, match_langs):
                passed.append(qid)
            elif qid == wiki_qid and "Q5" in claim_values(e, "P31") and is_political(e):
                # the zh-wiki title resolved (possibly via redirect) even though
                # no label equals the queried spelling — the redirect IS the
                # alias proof
                passed.append(qid)
        if len(passed) == 1:
            qid = passed[0]
            src, ref = image_ref_for(ents[qid])
            if src:
                return qid, ents[qid], (src, ref), f"matched on '{name}'"
            tried.append(f"'{name}' → {qid}: {ref}")
            imageless = imageless or ents[qid]
            continue
        if len(passed) > 1:
            opts = "; ".join(
                f"{q} ({ents[q].get('descriptions', {}).get('en', {}).get('value', '?')})"
                for q in passed)
            return None, None, None, \
                f"AMBIGUOUS '{name}': {opts} — rerun with --accept \"{name}=Qxxxx\""
        tried.append(f"'{name}': no candidate passed (human+exact-label+political)")
    return None, imageless, None, "; ".join(tried) or "no usable name"


def fetch_image(image_ref):
    """Download a portrait; returns (bytes, ext, page_url, attribution, licence).

    Raises RuntimeError for zh-wiki local files under a non-free licence."""
    src, filename = image_ref
    api = COMMONS_API if src == "commons" else ZHWIKI_API
    data = api_get(api, action="query", titles=filename,
                   prop="imageinfo", iiprop="url|extmetadata",
                   iiurlwidth=str(THUMB_WIDTH))
    pages = data.get("query", {}).get("pages", {})
    info = next(iter(pages.values()), {}).get("imageinfo", [{}])[0]
    thumb = info.get("thumburl") or info.get("url")
    if not thumb:
        raise RuntimeError(f"no image URL for {filename}")
    meta = info.get("extmetadata", {})
    licence = meta.get("LicenseShortName", {}).get("value", "").strip()
    if src == "zhwiki" and not FREE_LICENCE.search(licence or ""):
        raise RuntimeError(f"{filename}: non-free licence {licence!r} — not publishable")
    artist = re.sub(r"<[^>]+>", "", meta.get("Artist", {}).get("value", "")).strip()
    attribution = "Photo: " + " / ".join(
        x for x in (artist or None, "Wikimedia Commons" if src == "commons" else "Wikipedia (zh)",
                    licence or None) if x)
    r = requests.get(thumb, headers=UA, timeout=60)
    r.raise_for_status()
    time.sleep(SLEEP)
    ext = Path(thumb.split("?")[0]).suffix.lower().lstrip(".") or "jpg"
    if ext not in ("jpg", "jpeg", "png"):
        ext = "jpg"  # svg thumbs come back rasterised
    page_url = info.get("descriptionurl") or ""
    return r.content, ext, page_url, attribution, licence


def baike_lead(name_zh, name_en):
    name = name_zh or name_en
    return f"https://baike.baidu.com/item/{urllib.parse.quote(name)}"


_SITE_INDEX = None


def party_site_index():
    """name_zh → (site_key, image_url, page_url, stable_id), built lazily.

    Fetches every `PARTY_SITES` page once per run. A name that appears twice
    with DIFFERENT photos is dropped (ambiguous — same rule as Wikidata)."""
    global _SITE_INDEX
    if _SITE_INDEX is not None:
        return _SITE_INDEX
    idx, clash = {}, set()
    for key, site in PARTY_SITES.items():
        for page in site["pages"]:
            try:
                r = requests.get(page, headers=BROWSER_UA, timeout=30)
                r.raise_for_status()
            except requests.RequestException as e:
                print(f"  ! {key}: {page} unreachable ({e}) — skipping", file=sys.stderr)
                continue
            text = r.content.decode(site["encoding"], errors="replace") if site.get("encoding") else r.text
            for name, img, page_url, sid in site["parser"](text, page):
                prev = idx.get(name)
                if prev and prev[1] != img:
                    clash.add(name)
                idx.setdefault(name, (key, img, page_url, sid))
            time.sleep(SLEEP)
    for name in clash:
        idx.pop(name, None)
    _SITE_INDEX = idx
    return idx


def host_label(url):
    host = urllib.parse.urlparse(url).netloc.lower()
    for suffix, label in HOST_LABELS.items():
        if host == suffix or host.endswith("." + suffix):
            return label
    return host


def fetch_url_image(url):
    """Download an arbitrary image URL; returns (bytes, ext)."""
    r = requests.get(url, headers=BROWSER_UA, timeout=60)
    r.raise_for_status()
    ctype = r.headers.get("Content-Type", "").split(";")[0].strip().lower()
    ext = {"image/png": "png", "image/jpeg": "jpg", "image/jpg": "jpg"}.get(ctype)
    if not ext:
        ext = Path(urllib.parse.urlparse(url).path).suffix.lower().lstrip(".")
        if ext not in ("jpg", "jpeg", "png"):
            raise RuntimeError(f"{url}: not a JPEG/PNG ({ctype or 'unknown type'})")
    return r.content, "jpg" if ext == "jpeg" else ext


def site_key(prefix, sid, name):
    """Manifest key for a non-Wikidata entry, e.g. kmt:2547 / manual:lien_shengwu.

    A zh-only name has no ASCII slug, so it falls back to a short hash of the
    name — two zh-only manual entries must not collide on key or filename."""
    if sid:
        return f"{prefix}:{sid}"
    slug = slugify(name, "")
    return f"{prefix}:{slug or hashlib.sha1(name.encode('utf-8')).hexdigest()[:10]}"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--apply", action="store_true", help="download images + write manifest")
    ap.add_argument("--include-pending", action="store_true",
                    help="also cover people on pending (unreviewed) visits")
    ap.add_argument("--accept", action="append", default=[], metavar="NAME=QID",
                    help="force a Wikidata item for an ambiguous name (repeatable)")
    ap.add_argument("--manual", action="append", default=[], metavar="NAME=URL",
                    help="use a vetted image URL for a name Wikimedia can't supply "
                         "(official party / government sites; repeatable)")
    ap.add_argument("--no-party-sites", action="store_true",
                    help="skip the PARTY_SITES officer-page fallback")
    args = ap.parse_args()

    accepts = {}
    for a in args.accept:
        name, _, qid = a.partition("=")
        if not qid.startswith("Q"):
            ap.error(f"--accept wants NAME=QID, got {a!r}")
        accepts[name.strip()] = qid.strip()
    manuals = {}
    for m in args.manual:
        name, _, url = m.partition("=")
        if not url.startswith("http"):
            ap.error(f"--manual wants NAME=URL, got {m!r}")
        manuals[name.strip()] = url.strip()

    curated_ids, curated_names = curated_portraits()
    manifest = load_manifest()
    name_idx = manifest_name_index(manifest)

    people = collect_people(args.db, args.include_pending)
    seen_keys, todo = set(), []
    for p in people:  # merge DB rows that share a zh or en spelling
        key = (p["zh"] or p["en"]).strip().lower()
        if key not in seen_keys:
            seen_keys.add(key)
            todo.append(p)

    done, skipped, unresolved = [], [], []

    def record(key, fname, name_en, names, attribution, licence, page_url, label, note):
        """Write one manifest entry (Wikidata- or site-sourced) and index its names."""
        manifest[key] = {
            "file": fname,
            "name_en": name_en,
            "names": names,
            "attribution": attribution,
            "licence": licence,
            "source_url": page_url,
        }
        for n in names:
            name_idx[n.lower()] = key
        done.append((label, f"{key} → {fname} ({note})"))

    for p in todo:
        label = p["zh"] or p["en"]
        if (p["fid"] and p["fid"] in curated_ids) \
                or (p["zh"] or "").strip().lower() in curated_names \
                or (p["en"] or "").strip().lower() in curated_names:
            skipped.append((label, f"curated key-figure portrait ({p['fid'] or 'matched by name'})"))
            continue
        hit_qid = name_idx.get((p["zh"] or "").lower()) or name_idx.get((p["en"] or "").lower())
        if hit_qid:
            entry = manifest[hit_qid]
            new = [n for n in (p["zh"], p["en"]) if n and n not in entry["names"]]
            if new:
                entry["names"].extend(new)
                done.append((label, f"already in manifest ({hit_qid}); added variants {new}"))
            else:
                skipped.append((label, f"already in manifest ({hit_qid})"))
            continue
        if not looks_like_person(p["en"], p["zh"]):
            skipped.append((label, "looks like an organisation/delegation"))
            continue

        qid, entity, image_ref, note = resolve(p["zh"], p["en"], accepts)
        if not qid:
            # Fallbacks for people Wikimedia can't supply: an analyst-vetted URL,
            # then the official party-site officer grids (exact zh-name match).
            url = manuals.get(p["zh"] or "") or manuals.get(p["en"] or "")
            src_label, page_url, key = None, "", None
            if url:
                src_label, page_url, key = host_label(url), url, site_key("manual", None, p["en"] or p["zh"])
                note = f"{note}; manual URL"
            elif not args.no_party_sites and p["zh"]:
                # the DB spelling first, then the matched-but-imageless item's
                # label/alias forms (bridges 彭慶恩 ↔ 彭庆恩 on a PRC site)
                zh_forms = [p["zh"]] + [n for n in name_forms(entity, ZH_LANGS) if n != p["zh"]] \
                    if entity else [p["zh"]]
                sidx = party_site_index()
                hit = next((sidx[n] for n in zh_forms if n in sidx), None)
                if hit:
                    skey, url, page_url, sid = hit
                    src_label, key = PARTY_SITES[skey]["label"], site_key(skey, sid, p["en"])
                    note = f"{note}; found on {src_label}"
            if not url:
                unresolved.append((label, f"{note}\n{'':30}lead: {baike_lead(p['zh'], p['en'])}"))
                continue
            name_en = p["en"] or (entity or {}).get("labels", {}).get("en", {}).get("value") or p["zh"]
            names = sorted({n for n in [p["zh"], p["en"]]
                            + (list(name_forms(entity, ZH_LANGS)) if entity else []) if n})
            if args.apply:
                try:
                    blob, ext = fetch_url_image(url)
                except (requests.RequestException, RuntimeError) as e:
                    unresolved.append((label, f"{key}: {e}\n{'':30}lead: {baike_lead(p['zh'], p['en'])}"))
                    continue
                VISITS_DIR.mkdir(parents=True, exist_ok=True)
                fname = f"{slugify(name_en, key.replace(':', '_'))}.{ext}"
                (VISITS_DIR / fname).write_bytes(blob)
            else:
                fname = f"<dry-run:{key.split(':')[0]}>"
            record(key, fname, name_en, names, f"Photo: {src_label}", SITE_LICENCE, page_url, label, note)
            continue

        name_en = p["en"] or entity.get("labels", {}).get("en", {}).get("value")
        names = sorted({n for n in [p["zh"], p["en"]]
                        + list(name_forms(entity, ZH_LANGS)) if n})
        if args.apply:
            try:
                blob, ext, page_url, attribution, licence = fetch_image(image_ref)
            except RuntimeError as e:
                unresolved.append((label, f"{qid}: {e}\n{'':30}lead: {baike_lead(p['zh'], p['en'])}"))
                continue
            VISITS_DIR.mkdir(parents=True, exist_ok=True)
            fname = f"{slugify(name_en, qid)}.{ext}"
            (VISITS_DIR / fname).write_bytes(blob)
        else:
            fname, page_url, attribution, licence = f"<dry-run:{image_ref[0]}>", "", "", ""
        record(qid, fname, name_en, names, attribution, licence, page_url, label, note)

    if args.apply:
        VISITS_DIR.mkdir(parents=True, exist_ok=True)
        MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")

    mode = "APPLIED" if args.apply else "DRY-RUN (no downloads, manifest untouched)"
    print(f"\n== fetch_visit_portraits — {mode} ==")
    for title, rows in (("Resolved", done), ("Skipped", skipped), ("Unresolved", unresolved)):
        print(f"\n{title} ({len(rows)}):")
        for label, note in rows:
            print(f"  {label:<28} {note}")
    if not args.apply and done:
        print("\nRe-run with --apply to download these portraits and write the manifest.")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
