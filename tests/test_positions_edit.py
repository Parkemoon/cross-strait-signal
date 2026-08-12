"""_apply_text_edit — the validation core of PATCH /api/positions/text.

The endpoint lets the admin PositionsTab rewrite individual string fields in
positions.json. These tests pin the guard-rails: strings only, no structural
keys, no authoring-doc keys, paths must resolve.
"""
import pytest

from api.routes.positions import _apply_text_edit

SAMPLE = {
    "_comment": "authoring docs",
    "_meta": {"version": 1, "last_reviewed": "2026-07-10"},
    "actors": [
        {
            "id": "prc",
            "depth": "full",
            "intro_en": "",
            "legal_foundation": [
                {"id": "asl", "summary_en": "old", "sources": [{"label": "x", "url": "u"}]}
            ],
        }
    ],
    "concepts": [
        {"id": "c1", "what_en": "", "readings": [{"actor_id": "prc", "reading_en": ""}]}
    ],
}


def test_edits_nested_string_and_preserves_original():
    out = _apply_text_edit(SAMPLE, ["actors", 0, "legal_foundation", 0, "summary_en"], "new")
    assert out["actors"][0]["legal_foundation"][0]["summary_en"] == "new"
    # deep-copied — the input object is untouched
    assert SAMPLE["actors"][0]["legal_foundation"][0]["summary_en"] == "old"


def test_edits_meta_and_reading():
    out = _apply_text_edit(SAMPLE, ["_meta", "last_reviewed"], "2026-08-12")
    assert out["_meta"]["last_reviewed"] == "2026-08-12"
    out = _apply_text_edit(SAMPLE, ["concepts", 0, "readings", 0, "reading_en"], "r")
    assert out["concepts"][0]["readings"][0]["reading_en"] == "r"


@pytest.mark.parametrize(
    "path,value",
    [
        (["actors", 0, "id"], "x"),                      # protected leaf
        (["concepts", 0, "readings", 0, "actor_id"], "x"),  # protected leaf
        (["actors", 0, "depth"], "brief"),               # protected leaf
        (["_comment"], "x"),                             # authoring doc
        (["nope", 0], "x"),                              # bad root
        (["actors", 5, "intro_en"], "x"),                # index out of range
        (["actors", 0, "missing_key"], "x"),             # unknown key
        (["actors", 0, "legal_foundation"], "x"),        # leaf is a list, not str
        (["actors", 0, "legal_foundation", 0], "x"),     # ends at list position
        (["_meta", "version"], "2"),                     # leaf is an int, not str
        ([], "x"),                                       # empty path
        (["actors", True, "intro_en"], "x"),             # bool masquerading as index
    ],
)
def test_rejected_edits(path, value):
    with pytest.raises(ValueError):
        _apply_text_edit(SAMPLE, path, value)


def test_rejects_non_string_value():
    with pytest.raises(ValueError):
        _apply_text_edit(SAMPLE, ["actors", 0, "intro_en"], 42)
