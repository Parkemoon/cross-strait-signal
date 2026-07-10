"""scraper/processors/positions.json — shape validation for the hand-curated
Positions & Legal Status content. This is the guard-rail for the co-writing
sessions: a malformed or half-filled entry fails the suite (which runs before
every deploy) instead of rendering broken on the page."""
import json
import os
import re

import pytest

CONTENT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "scraper", "processors", "positions.json"
)

ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

ACTOR_KEYS = {
    "id", "name_en", "name_zh", "short_name", "depth", "iso", "intro_en",
    "legal_foundation", "current_position", "sub_positions", "misconceptions",
    "hooks",
}
LEGAL_KEYS = {
    "id", "title_en", "title_zh", "romanisation", "summary_en",
    "effective_date", "not_say_en", "sources",
}
POSITION_KEYS = {
    "id", "position_en", "formulation_zh", "romanisation", "formulation_en",
    "as_stated", "stated_by", "nuance_en", "sources",
}
MISCONCEPTION_KEYS = {"id", "myth_en", "actually_en", "sources"}
SOURCE_KEYS = {"label", "url", "date", "lang"}


@pytest.fixture(scope="module")
def content():
    with open(CONTENT_PATH, encoding="utf-8") as f:
        return json.load(f)


def _check_sources(sources, where):
    assert isinstance(sources, list), f"{where}: sources must be a list"
    for s in sources:
        assert set(s) <= SOURCE_KEYS, f"{where}: unknown source keys {set(s) - SOURCE_KEYS}"
        assert s.get("label") and s.get("url"), f"{where}: source needs label + url"
        if s.get("date"):
            assert ISO_DATE.match(s["date"]), f"{where}: source date not ISO: {s['date']}"


def _check_date(value, where, required=False):
    if value:
        assert ISO_DATE.match(value), f"{where}: not an ISO date: {value!r}"
    elif required:
        pytest.fail(f"{where}: date required once entry is filled")


def test_json_parses_and_top_level(content):
    assert content["_meta"]["version"] == 1
    _check_date(content["_meta"]["last_reviewed"], "_meta.last_reviewed", required=True)
    assert isinstance(content["actors"], list) and content["actors"]
    assert isinstance(content["concepts"], list) and content["concepts"]


def test_actor_shapes(content):
    seen = set()
    for a in content["actors"]:
        where = f"actor {a.get('id')}"
        assert set(a) == ACTOR_KEYS, f"{where}: keys {set(a) ^ ACTOR_KEYS}"
        assert a["id"] not in seen, f"duplicate actor id {a['id']}"
        seen.add(a["id"])
        assert a["depth"] in ("full", "brief"), where
        assert a["name_en"] and a["name_zh"] and a["short_name"], where
        assert set(a["hooks"]) == {"diplomacy_iso", "entity_names_en"}, where

        for it in a["legal_foundation"]:
            w = f"{where}.legal_foundation.{it.get('id')}"
            assert set(it) == LEGAL_KEYS, f"{w}: keys {set(it) ^ LEGAL_KEYS}"
            assert it["id"] and it["title_en"], w
            _check_date(it["effective_date"], w)
            _check_sources(it["sources"], w)
            # A written entry must be dated and sourced.
            if it["summary_en"]:
                assert it["effective_date"], f"{w}: filled entry needs effective_date"
                assert it["sources"], f"{w}: filled entry needs >=1 source"

        for it in a["current_position"]:
            w = f"{where}.current_position.{it.get('id')}"
            assert set(it) == POSITION_KEYS, f"{w}: keys {set(it) ^ POSITION_KEYS}"
            assert it["id"], w
            assert it["formulation_en"] or it["formulation_zh"], f"{w}: needs a formulation"
            _check_date(it["as_stated"], w)
            _check_sources(it["sources"], w)
            if it["position_en"]:
                assert it["as_stated"], f"{w}: filled entry needs as_stated"
                assert it["sources"], f"{w}: filled entry needs >=1 source"

        for sp in a["sub_positions"]:
            w = f"{where}.sub_positions.{sp.get('id')}"
            assert sp["id"] and sp["label_en"] and sp["party"], w
            for it in sp["items"]:
                wi = f"{w}.{it.get('id')}"
                assert set(it) == POSITION_KEYS, f"{wi}: keys {set(it) ^ POSITION_KEYS}"
                _check_date(it["as_stated"], wi)
                _check_sources(it["sources"], wi)
                if it["position_en"]:
                    assert it["as_stated"] and it["sources"], f"{wi}: filled entry needs date + source"

        for it in a["misconceptions"]:
            w = f"{where}.misconceptions.{it.get('id')}"
            assert set(it) == MISCONCEPTION_KEYS, f"{w}: keys {set(it) ^ MISCONCEPTION_KEYS}"
            _check_sources(it["sources"], w)
            if it["myth_en"] or it["actually_en"]:
                assert it["myth_en"] and it["actually_en"], f"{w}: myth and reality both required"
                assert it["sources"], f"{w}: filled entry needs >=1 source"


def test_concept_shapes_and_reading_refs(content):
    actor_ids = {a["id"] for a in content["actors"]}
    sub_ids = {sp["id"] for a in content["actors"] for sp in a["sub_positions"]}
    valid_refs = actor_ids | sub_ids

    seen = set()
    for c in content["concepts"]:
        where = f"concept {c.get('id')}"
        assert c["id"] not in seen, f"duplicate concept id {c['id']}"
        seen.add(c["id"])
        assert c["title_en"] and c["title_zh"], where
        assert isinstance(c["readings"], list) and c["readings"], f"{where}: needs readings"
        for r in c["readings"]:
            w = f"{where}.reading[{r.get('actor_id')}]"
            assert r["actor_id"] in valid_refs, f"{w}: unknown actor_id {r['actor_id']!r}"
            assert r["label_en"], w
            _check_sources(r["sources"], w)
            if r["reading_en"]:
                assert r["sources"], f"{w}: filled reading needs >=1 source"


def test_party_keys_are_known(content):
    # Mirror of frontend/src/partyColours.js PARTY_COLOURS — keep in lockstep.
    known = {"DPP", "KMT", "TPP", "NPP", "TSP", "GPT", "NP", "PFP", "CUPP", "IND", "PRC"}
    for a in content["actors"]:
        for sp in a["sub_positions"]:
            assert sp["party"] in known, f"{a['id']}.{sp['id']}: unknown party {sp['party']!r}"


def test_api_route_serves_content():
    from fastapi.testclient import TestClient
    from api.main import app

    client = TestClient(app)
    res = client.get("/api/positions/")
    assert res.status_code == 200
    body = res.json()
    assert "actors" in body and "concepts" in body and "_meta" in body
    assert not any(k.startswith("_comment") for k in body)
