"""glossary.json and entity_canonical.json must agree on person names.

The write path layers the registry (seeded from BOTH files) over the canon,
and the history repair reads the canon; when the two files disagreed on
one person (江啟臣, 2026-09-13) the spelling ping-ponged between them. Since
the 2026-09-14 harmonisation every person is in both files, in both
scripts, with one English form — this test keeps it that way.
"""
import importlib.util
import json
import os
import sys

import pytest

REPO = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, REPO)

from shared.name_registry import to_simp, to_trad  # noqa: E402

_spec = importlib.util.spec_from_file_location('seed_name_registry', os.path.join(REPO, 'scripts', 'seed_name_registry.py'))
_seed = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_seed)
person_entries = _seed.person_entries


@pytest.fixture(scope='module')
def files():
    with open(os.path.join(REPO, 'scraper', 'processors', 'glossary.json'), encoding='utf-8') as f:
        glossary = json.load(f)
    with open(os.path.join(REPO, 'scraper', 'processors', 'entity_canonical.json'), encoding='utf-8') as f:
        canon = json.load(f)['canonical']
    return glossary, canon


def _by_trad(mapping):
    out = {}
    for zh, en in mapping.items():
        out.setdefault(to_trad(zh), en.strip())
    return out


def test_shared_keys_carry_one_english_form(files):
    glossary, canon = files
    g, c = _by_trad(glossary), _by_trad(canon)
    clashes = {k: (g[k], c[k]) for k in g if k in c and g[k] != c[k]}
    assert not clashes, f"glossary and canon disagree: {clashes}"


def test_every_person_is_in_both_files(files):
    glossary, canon = files
    gp = dict(person_entries(_by_trad(glossary)))
    cp = dict(person_entries(_by_trad(canon)))
    missing_from_canon = sorted(set(gp) - set(cp))
    missing_from_glossary = sorted(set(cp) - set(gp))
    assert not missing_from_canon, f"people only in glossary.json: {missing_from_canon}"
    assert not missing_from_glossary, f"people only in entity_canonical.json: {missing_from_glossary}"


def test_every_person_has_both_scripts(files):
    glossary, canon = files
    gaps = []
    for name, mapping in (('glossary', glossary), ('canon', canon)):
        for zh, _ in person_entries(mapping):
            simp, trad = to_simp(zh), to_trad(zh)
            if simp != trad and (simp not in mapping or trad not in mapping):
                gaps.append((name, zh))
    assert not gaps, f"person keys missing their other-script twin: {gaps}"
