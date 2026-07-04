#!/usr/bin/env python3
"""Refresh the current officials roster from Wikidata SPARQL.

Run manually after elections, reshuffles, or when officeholder hallucinations
are spotted in pipeline output:

    python scripts/refresh_officials.py

Output: scraper/processors/current_officials.json (committed to git so the
production server picks it up on the next git pull / deploy).

Roles with thin Wikidata coverage (TAO Director, MFA spokespersons, party
minor offices) go in scraper/processors/current_officials_manual.json — the
manual file wins on conflict.
"""

import json
import os
import sys
import time
from datetime import datetime, timezone

import requests

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

POSITIONS_PATH = os.path.join(SCRIPT_DIR, "officials_positions.json")
OUTPUT_PATH = os.path.join(PROJECT_ROOT, "scraper", "processors", "current_officials.json")
MANUAL_PATH = os.path.join(PROJECT_ROOT, "scraper", "processors", "current_officials_manual.json")
GLOSSARY_PATH = os.path.join(PROJECT_ROOT, "scraper", "processors", "glossary.json")
KEY_FIGURES_PATH = os.path.join(PROJECT_ROOT, "scraper", "processors", "key_figures.json")

SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
HEADERS = {"User-Agent": "cross-strait-signal/1.0 (github.com/Parkemoon/cross-strait-signal)"}
DELAY = 1.3  # seconds between SPARQL calls to avoid rate limiting


def load_romanisation_overrides():
    """Build zh_name → preferred_en_name map from glossary + key_figures."""
    overrides = {}
    try:
        with open(GLOSSARY_PATH, encoding="utf-8") as f:
            overrides.update(json.load(f))
    except Exception as e:
        print(f"  Warning: could not load glossary: {e}", file=sys.stderr)
    try:
        with open(KEY_FIGURES_PATH, encoding="utf-8") as f:
            figures = json.load(f)
        for fig in figures:
            zh = fig.get("name_zh", "")
            en = fig.get("name_en", "")
            if zh and en:
                overrides[zh] = en
    except Exception as e:
        print(f"  Warning: could not load key_figures: {e}", file=sys.stderr)
    return overrides


def sparql_query(sparql):
    """Run a SPARQL query against Wikidata; return bindings list (may be empty)."""
    try:
        r = requests.get(
            SPARQL_ENDPOINT,
            params={"query": sparql, "format": "json"},
            headers=HEADERS,
            timeout=30,
        )
        r.raise_for_status()
        return r.json()["results"]["bindings"]
    except requests.HTTPError as e:
        print(f"    HTTP error: {e}", file=sys.stderr)
    except Exception as e:
        print(f"    SPARQL error: {e}", file=sys.stderr)
    return []


def get_current_holder(qid):
    """Return dict for the current holder of position QID, or None."""
    sparql = f"""
SELECT ?holder ?holderLabel ?holderLabelZh ?start ?partyLabel WHERE {{
  ?holder p:P39 ?ps.
  ?ps ps:P39 wd:{qid}.
  ?ps pq:P580 ?start.
  FILTER NOT EXISTS {{ ?ps pq:P582 ?end }}
  OPTIONAL {{
    ?holder wdt:P102 ?party.
    ?party rdfs:label ?partyLabel.
    FILTER(LANG(?partyLabel) = "en")
  }}
  ?holder rdfs:label ?holderLabel.
  FILTER(LANG(?holderLabel) = "en")
  OPTIONAL {{
    ?holder rdfs:label ?holderLabelZh.
    FILTER(LANG(?holderLabelZh) = "zh")
  }}
}}
ORDER BY DESC(?start)
LIMIT 1
"""
    rows = sparql_query(sparql)
    if not rows:
        return None
    row = rows[0]
    return {
        "name_en": row["holderLabel"]["value"],
        "name_zh": row.get("holderLabelZh", {}).get("value", ""),
        "party": row.get("partyLabel", {}).get("value", ""),
        "since": row.get("start", {}).get("value", "")[:10],
    }


def get_former_holders(qid, since_date):
    """Return list of former holders of position QID whose term ended after since_date."""
    sparql = f"""
SELECT DISTINCT ?holder ?holderLabel ?holderLabelZh ?start ?end ?partyLabel WHERE {{
  ?holder p:P39 ?ps.
  ?ps ps:P39 wd:{qid}.
  ?ps pq:P580 ?start.
  ?ps pq:P582 ?end.
  FILTER(?end >= "{since_date}T00:00:00Z"^^xsd:dateTime)
  OPTIONAL {{
    ?holder wdt:P102 ?party.
    ?party rdfs:label ?partyLabel.
    FILTER(LANG(?partyLabel) = "en")
  }}
  ?holder rdfs:label ?holderLabel.
  FILTER(LANG(?holderLabel) = "en")
  OPTIONAL {{
    ?holder rdfs:label ?holderLabelZh.
    FILTER(LANG(?holderLabelZh) = "zh")
  }}
}}
ORDER BY DESC(?end)
"""
    rows = sparql_query(sparql)
    results = []
    seen = set()
    for row in rows:
        name_en = row["holderLabel"]["value"]
        if name_en in seen:
            continue
        seen.add(name_en)
        start = row.get("start", {}).get("value", "")[:10]
        end = row.get("end", {}).get("value", "")[:10]
        results.append({
            "name_en": name_en,
            "name_zh": row.get("holderLabelZh", {}).get("value", ""),
            "party": row.get("partyLabel", {}).get("value", ""),
            "term": f"{start} to {end}",
        })
    return results


def apply_override(entry, overrides):
    """Replace name_en with our preferred romanisation if zh name is in overrides."""
    zh = entry.get("name_zh", "")
    if zh and zh in overrides:
        entry["name_en"] = overrides[zh]
    return entry


def main():
    with open(POSITIONS_PATH, encoding="utf-8") as f:
        config = json.load(f)

    overrides = load_romanisation_overrides()

    current = []
    former = []
    missing = []

    positions = config["positions"]
    total = len(positions)

    for i, pos in enumerate(positions, 1):
        qid = pos["wikidata_qid"]
        role_en = pos["role_en"]
        country = pos.get("country", "")
        since = pos.get("include_former_since", "2016-01-01")

        print(f"[{i}/{total}] {role_en} ({qid})")

        holder = get_current_holder(qid)
        time.sleep(DELAY)

        if holder:
            holder = apply_override(holder, overrides)
            current.append({"role": role_en, "country": country, **holder})
            print(f"  → Current: {holder['name_en']} (since {holder['since']})")
        else:
            missing.append(role_en)
            print(f"  → No current holder found — add to current_officials_manual.json if needed")

        formers = get_former_holders(qid, since)
        time.sleep(DELAY)

        for entry in formers:
            entry = apply_override(entry, overrides)
            former.append({"role": role_en, "country": country, **entry})
        if formers:
            names = ", ".join(e["name_en"] for e in formers[:4])
            print(f"  → Former ({len(formers)}): {names}")

    # Merge manual gap-fill if present; manual entries win on (role, country) conflict
    if os.path.exists(MANUAL_PATH):
        with open(MANUAL_PATH, encoding="utf-8") as f:
            manual = json.load(f)
        manual_keys = {(e["role"], e.get("country", "")) for e in manual.get("current", [])}
        current = [e for e in current if (e["role"], e.get("country", "")) not in manual_keys]
        current.extend(manual.get("current", []))
        manual_former_keys = {(e["role"], e["name_en"]) for e in manual.get("former", [])}
        former = [e for e in former if (e["role"], e["name_en"]) not in manual_former_keys]
        former.extend(manual.get("former", []))
        print(f"\nMerged {len(manual.get('current', []))} current + {len(manual.get('former', []))} former from manual file.")

    # Guard against a Wikidata outage silently gutting the roster: sparql_query()
    # returns [] on any error, so a rate-limited run can resolve almost no
    # office-holders and would otherwise overwrite a healthy file with a near-
    # empty one (which the AI pipeline then trusts). Refuse if the new roster is
    # far smaller than the existing one.
    prev_current = 0
    if os.path.exists(OUTPUT_PATH):
        try:
            with open(OUTPUT_PATH, encoding="utf-8") as f:
                prev_current = len(json.load(f).get("current", []))
        except Exception:
            prev_current = 0
    floor = max(10, int(prev_current * 0.6))
    if len(current) < floor:
        print(f"\nABORT: only {len(current)} current office-holders resolved "
              f"(expected >= {floor}). This looks like a Wikidata outage or "
              f"rate-limit — NOT overwriting {OUTPUT_PATH}. Re-run when Wikidata "
              f"is healthy.", file=sys.stderr)
        sys.exit(1)

    output = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "current": current,
        "former": former,
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*50}")
    print(f"Done. {len(current)} current, {len(former)} former entries written.")
    print(f"Output: {OUTPUT_PATH}")
    if missing:
        print(f"\nPositions with no Wikidata result ({len(missing)}) — add to manual file:")
        for role in missing:
            print(f"  - {role}")
    print("\nReview the output, then: git add scraper/processors/current_officials.json && git commit && ./deploy.sh")


if __name__ == "__main__":
    main()
