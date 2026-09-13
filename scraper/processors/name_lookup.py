"""Name lookup worker — pipeline Step 3f.

Every Taiwan-side person the Tier-1 pass has extracted whose Chinese name
is not yet in the registry (or the committed glossary / canonical files)
gets looked up ONCE, in three tiers:

  1. Wikidata — exact zh / zh-tw / zh-hant label, humans only, batched
     through the SPARQL endpoint (the action API rate-limits after ~10
     calls). Auto-approved only when the item has Taiwan citizenship, its
     description does not read as a namesake of the model's role text, and
     the English label is not Hanyu-shaped. Anything less lands pending
     with the label as a candidate.
  2. Grounded search — a Gemini call with the Google Search tool asking for
     the established romanisation and the page it appears on; the page is
     fetched and the spelling must be on it. Lands PENDING (source
     'search'), never approved: a wrong canonical propagates to every
     later article, so the analyst signs these off.
  3. Generated — deterministic Hanyu → Wade-Giles (shared.romanisation),
     pending, low confidence, with the prod renderings as candidates.

Side comes from the model's own role text (shared.romanisation
.side_from_role); PRC-side names stay Hanyu Pinyin and are never looked
up. Idempotent: a name with ANY registry row is skipped, so each name
costs one lookup ever. CLI: scripts/lookup_names.py.
"""
from __future__ import annotations

import json
import re
import time
from collections import Counter, defaultdict

import requests

from scraper.utils.db import get_connection
from scraper.utils.usage_log import log_usage
from shared.entity_norm import load_canon, resolve_name_en
from shared.name_registry import known_forms, to_trad, upsert
from shared.romanisation import CJK_NAME, hanyu_markers, side_from_role, to_wade_giles

SPARQL = 'https://query.wikidata.org/sparql'
HEADERS = {"User-Agent": "cross-strait-signal/1.0 (github.com/Parkemoon/cross-strait-signal)",
           "Accept": "application/sparql-results+json"}
BATCH = 40
SEARCH_MODEL = "gemini-3.1-flash-lite"

OFFICE_ROLE = re.compile(r"legislat|minister|spokes|mayor|magistrate|secretary|chair|director|official|council|"
                         r"deputy|premier|president|representative|diplomat|commissioner|governor|caucus", re.I)
NAMESAKE_DESC = re.compile(r"gamer|player|singer|actor|actress|footballer|dynasty|athlete|rapper|youtuber|model\b|"
                           r"painter|composer|novelist|swimmer|cyclist|racing|wrestler|boxer|\b1[0-8]\d\d\b", re.I)
POLITICAL_DESC = re.compile(r"politic|legislat|minister|mayor|official|diplomat|bureaucrat|secretary|magistrate|"
                            r"council|party|governor|president|premier", re.I)


# ── candidates ──────────────────────────────────────────────────────────

def collect_unresolved(conn, days=14, limit=100, canon=None):
    """Taiwan-side person names from recently analysed articles with no
    registry row and no JSON canonical entry. One dict per traditional
    name: forms seen, mentions, renderings, roles, first article."""
    canon = canon or load_canon()
    rows = conn.execute("""
        SELECT e.entity_name AS zh, e.entity_name_en AS en, e.entity_role AS role, a.id AS aid, a.published_at
        FROM entities e JOIN articles a ON a.id = e.article_id
        WHERE e.entity_type = 'person' AND a.is_hidden = 0 AND a.ai_processed = 1
          AND a.published_at >= date('now', ?)
        ORDER BY a.published_at ASC""", (f'-{days} days',)).fetchall()
    # surname + title forms (賴總統, 顧部長) are not names — the resolver's
    # title-strip handles the full ones and the bare ones must not be registered
    title_tokens = canon.get('title_tokens') or []
    groups = {}
    for r in rows:
        zh = (r['zh'] or '').strip()
        if not CJK_NAME.match(zh) or any(t in zh for t in title_tokens):
            continue
        key = to_trad(zh)
        g = groups.setdefault(key, {'zh_trad': key, 'forms': Counter(), 'renderings': Counter(), 'roles': Counter(),
                                    'tw': 0, 'prc': 0, 'first_aid': r['aid'], 'mentions': 0})
        g['forms'][zh] += 1
        g['renderings'][(r['en'] or '').strip()] += 1
        g['roles'][(r['role'] or '').strip()[:80]] += 1
        g['mentions'] += 1
        side = side_from_role(r['role'])
        if side == 'TW':
            g['tw'] += 1
        elif side == 'PRC':
            g['prc'] += 1
    out = []
    for g in groups.values():
        if g['tw'] == 0 or g['prc'] >= g['tw']:
            continue
        if any(resolve_name_en(f, canon) for f in g['forms']) or resolve_name_en(g['zh_trad'], canon):
            continue
        if known_forms(conn, g['zh_trad']) is not None:
            continue
        g['role_hint'] = g['roles'].most_common(1)[0][0] if g['roles'] else ''
        out.append(g)
    out.sort(key=lambda g: -g['mentions'])
    return out[:limit]


# ── tier 1: Wikidata ────────────────────────────────────────────────────

def wikidata_batch(names):
    """{zh_trad: [hit, …]} — humans with an exact zh/zh-tw/zh-hant label."""
    values = ' '.join(f'"{n}"@{lang}' for n in names for lang in ('zh-tw', 'zh', 'zh-hant'))
    q = f"""
SELECT ?zh ?item ?itemLabel ?itemDescription
       (GROUP_CONCAT(DISTINCT ?cLabel; separator="|") AS ?cit) (COUNT(DISTINCT ?pos) AS ?npos)
WHERE {{
  VALUES ?zh {{ {values} }}
  ?item rdfs:label ?zh ; wdt:P31 wd:Q5 .
  OPTIONAL {{ ?item wdt:P27 ?c . ?c rdfs:label ?cLabel . FILTER(lang(?cLabel) = "en") }}
  OPTIONAL {{ ?item p:P39 ?pos }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
GROUP BY ?zh ?item ?itemLabel ?itemDescription
"""
    bindings = None
    for i in range(4):
        r = requests.get(SPARQL, params={'query': q, 'format': 'json'}, headers=HEADERS, timeout=120)
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(10 * (i + 1))
            continue
        r.raise_for_status()
        bindings = r.json()['results']['bindings']
        break
    if bindings is None:
        raise RuntimeError(f'Wikidata SPARQL failed: {r.status_code}')
    hits = defaultdict(list)
    for row in bindings:
        qid = row['item']['value'].rsplit('/', 1)[-1]
        label = row.get('itemLabel', {}).get('value')
        cit = [c for c in row.get('cit', {}).get('value', '').split('|') if c]
        cit = ['Taiwan' if c in ('Taiwan', 'Republic of China') else 'PRC' if c == "People's Republic of China" else c for c in cit]
        hits[to_trad(row['zh']['value'])].append({
            'qid': qid, 'en': None if not label or label == qid else label,
            'desc': row.get('itemDescription', {}).get('value') or '',
            'citizenship': cit, 'positions': int(row.get('npos', {}).get('value', 0))})
    for hs in hits.values():
        hs.sort(key=lambda h: ('Taiwan' not in h['citizenship'], -h['positions']))
    return hits


def decide_wikidata(cand, hits):
    """(status, en, note, qid, confidence) for the best Wikidata hit, or
    None when there is no usable hit. Approves only the clean case."""
    if not hits:
        return None
    top = hits[0]
    qid, en, desc, cit = top['qid'], top['en'], top['desc'], top['citizenship']
    roles = ' '.join(cand['roles'])
    n = len(hits)
    tag = f"Wikidata {qid}" + (f" ({n} namesakes)" if n > 1 else "")
    if cit and 'Taiwan' not in cit:
        # a PRC (or other) person the role heuristic mis-sided, or a namesake:
        # propose the item's own label (Hanyu for a PRC person is right) and
        # let the analyst settle which it is
        return ('pending', en, f"{tag}: citizenship {', '.join(cit)} — {desc}; PRC person mis-sided, or a namesake", qid, 0.3)
    if not en:
        return ('pending', None, f"{tag}: no English label — {desc}", qid, 0.3)
    if NAMESAKE_DESC.search(desc) and OFFICE_ROLE.search(roles) and not POLITICAL_DESC.search(desc):
        return ('pending', None, f"{tag} looks like a namesake: {desc}", qid, 0.3)
    if hanyu_markers(en):
        return ('pending', None, f"{tag} label is Hanyu-shaped: {en} — {desc}", qid, 0.4)
    if 'Taiwan' in cit or re.search(r'taiwan', desc, re.I):
        return ('approved', en, f"{tag}: {desc}", qid, 0.9)
    return ('pending', None, f"{tag}: {en} — {desc}; no citizenship on the item", qid, 0.5)


# ── tier 2: grounded search ─────────────────────────────────────────────

def _client():
    from scraper.utils.llm import get_gemini_client
    return get_gemini_client()


def grounded_search(cand, client=None):
    """Ask Gemini with Google Search for the established romanisation and a
    page it appears on. Returns {'en', 'url', 'confidence', 'sources'} or
    None. Never trusted on its own — see verify_url."""
    from google.genai import types
    client = client or _client()
    zh = cand['zh_trad']
    prompt = (
        f"What is the established English romanisation of the Taiwanese person 「{zh}」"
        f" ({cand.get('role_hint') or 'role unknown'})? Prefer the spelling used by official Taiwan sources"
        f" (Legislative Yuan, ministries, county governments, party sites) or English-language Taiwan media"
        f" (Focus Taiwan, Taipei Times). Taiwanese names use Wade-Giles or the person's own preferred"
        f" spelling, not Hanyu Pinyin. Return only JSON: {{\"en\": \"<spelling>\", \"url\": \"<page where that"
        f" exact spelling appears>\", \"confidence\": <0-1>}} or {{\"en\": null}} if you cannot find it.")
    resp = client.models.generate_content(
        model=SEARCH_MODEL, contents=prompt,
        config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())],
                                           max_output_tokens=1000,
                                           thinking_config=types.ThinkingConfig(thinking_level='low')))
    log_usage('name_lookup', SEARCH_MODEL, resp)
    text = resp.text or ''
    m = re.search(r'\{.*\}', text, re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    sources = []
    try:
        gm = resp.candidates[0].grounding_metadata
        for ch in (gm.grounding_chunks or []) if gm else []:
            if ch.web and ch.web.uri:
                sources.append(ch.web.uri)
    except Exception:
        pass
    en = (data.get('en') or '').strip() or None
    if not en:
        return None
    return {'en': en, 'url': data.get('url') or (sources[0] if sources else None),
            'confidence': float(data.get('confidence') or 0.5), 'sources': sources}


def verify_url(url, en, timeout=15):
    """True when the exact spelling appears on the page (case-insensitive,
    tags stripped). A grounding redirect URL is followed."""
    if not url or not en:
        return False
    try:
        r = requests.get(url, headers={"User-Agent": HEADERS["User-Agent"]}, timeout=timeout, allow_redirects=True)
        if r.status_code >= 400:
            return False
        text = re.sub(r'<[^>]+>', ' ', r.text)
        return en.lower() in text.lower()
    except Exception:
        return False


# ── driver ──────────────────────────────────────────────────────────────

def _candidates_list(cand, extra=()):
    out = [{'form': f, 'source': 'prod rendering', 'n': n} for f, n in cand['renderings'].most_common(4) if f]
    out += list(extra)
    return out


def lookup_new_names(days=14, limit=60, conn=None, use_search=True, verbose=True):
    """Run the three tiers over every unresolved Taiwan-side name. Returns
    a summary dict; rows land in name_registry."""
    own = conn is None
    conn = conn or get_connection()
    canon = load_canon()
    cands = collect_unresolved(conn, days=days, limit=limit, canon=canon)
    summary = Counter()
    if verbose:
        print(f"  {len(cands)} unresolved Taiwan-side name(s)")
    for b in range(0, len(cands), BATCH):
        batch = cands[b:b + BATCH]
        try:
            hits = wikidata_batch([c['zh_trad'] for c in batch])
        except Exception as e:
            print(f"  Wikidata batch failed — {e}; names left for the next run")
            summary['wikidata_error'] += 1
            continue
        for cand in batch:
            zh = cand['zh_trad']
            role = cand.get('role_hint') or ''
            majority = cand['renderings'].most_common(1)[0][0] if cand['renderings'] else None
            generated = to_wade_giles(zh)
            extra = []
            if generated:
                extra.append({'form': generated, 'source': 'generated Wade-Giles'})
            decision = decide_wikidata(cand, hits.get(zh, []))
            if decision:
                status, en, note, qid, conf = decision
                wd_en = hits[zh][0]['en']
                if wd_en:
                    extra.insert(0, {'form': wd_en, 'source': f'Wikidata {qid}'})
                proposal = en or (majority if majority and not hanyu_markers(majority) else generated)
                side = 'PRC' if 'PRC person' in note else 'TW'
                upsert(conn, zh, proposal, side, 'wikidata', status, qid=qid, evidence_note=note, role_hint=role,
                       candidates=_candidates_list(cand, extra), mentions=cand['mentions'],
                       first_article_id=cand['first_aid'], confidence=conf)
                conn.commit()  # per name: a batch-long write lock starved the 6-hourly tick (2026-09-13)
                summary[f'wikidata_{status}'] += 1
                if verbose:
                    print(f"    {zh} → {proposal} [{status}] {note[:80]}")
                continue
            found = None
            if use_search:
                try:
                    found = grounded_search(cand)
                except Exception as e:
                    print(f"    {zh}: search failed — {e}")
                    summary['search_error'] += 1
            if found and found['en'] and not hanyu_markers(found['en']):
                verified = verify_url(found['url'], found['en'])
                note = (f"search: '{found['en']}' {'verified on' if verified else 'NOT found on'} {found['url'] or 'no url'}")
                upsert(conn, zh, found['en'], 'TW', 'search', 'pending', evidence_url=found['url'], evidence_note=note,
                       role_hint=role, candidates=_candidates_list(cand, extra), mentions=cand['mentions'],
                       first_article_id=cand['first_aid'], confidence=0.8 if verified else 0.4)
                conn.commit()  # per name: a batch-long write lock starved the 6-hourly tick (2026-09-13)
                summary['search_verified' if verified else 'search_unverified'] += 1
                if verbose:
                    print(f"    {zh} → {found['en']} [pending] {note[:80]}")
                continue
            proposal = majority if majority and not hanyu_markers(majority) else generated
            upsert(conn, zh, proposal, 'TW', 'generated', 'pending',
                   evidence_note="no Wikidata item; " + ("search found nothing" if use_search else "search off")
                   + (f"; proposal is {'the prod majority rendering' if proposal == majority else 'generated Wade-Giles'}" if proposal else ""),
                   role_hint=role, candidates=_candidates_list(cand, extra), mentions=cand['mentions'],
                   first_article_id=cand['first_aid'], confidence=0.3)
            conn.commit()  # per name: a batch-long write lock starved the 6-hourly tick (2026-09-13)
            summary['generated_pending'] += 1
            if verbose:
                print(f"    {zh} → {proposal} [pending, generated]")
        conn.commit()
        time.sleep(1)
    if own:
        conn.close()
    if verbose:
        print(f"  done: {dict(summary)}")
    return dict(summary)
