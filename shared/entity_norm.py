"""Entity-name canonicalisation shared by the AI write path
(scraper/processors/ai_pipeline.py) and the historical back-fill
(scripts/renormalise_entities.py).

These used to implement DIFFERENT semantics: the pipeline ran an
open-ended bidirectional prefix scan over every canonical key, which
corrupted title-prepended names ('國防部長顧立雄' startswith '國防部' →
"Ministry of National Defense"), while the back-fill was exact-only
BECAUSE of that corruption — so a canonical edit could never repair the
very rows the pipeline had mislabelled. One resolver, three explicit
tiers, both callers:

  1. exact        — zh name is a key in `canonical` (always safe).
  2. title-strip  — a role word from `title_tokens` appears in the name;
                    the part after it (title-first: 國防部長顧立雄) or
                    before it (name-first: 賴清德總統) exact-matches
                    `canonical`. High precision: the remainder must be an
                    exact canonical key.
  3. fold-prefix  — the name extends one of the opt-in `fold_prefixes`
                    (each itself a canonical key): 漢光41號演習 → 漢光.
                    Longest prefix wins so 解放軍海軍陸戰隊 folds to the
                    navy, not the bare PLA. Only listed keys participate —
                    this replaces the old any-key prefix scan.

The tables live in scraper/processors/entity_canonical.json:
  { "canonical": {zh: en}, "title_tokens": [...], "fold_prefixes": [...] }
A legacy flat {zh: en} file is tolerated (treated as canonical-only).
"""
import json
import os

CANON_PATH = os.path.join(
    os.path.dirname(__file__), '..', 'scraper', 'processors', 'entity_canonical.json'
)


def load_canon(path=None):
    """Load entity_canonical.json into the structure resolve_name_en expects.
    Tolerates the legacy flat {zh: en} shape (canonical-only, no strip/fold)."""
    with open(path or CANON_PATH, encoding='utf-8') as f:
        raw = json.load(f)
    if 'canonical' not in raw:  # legacy flat file
        raw = {'canonical': raw}
    canonical = raw['canonical']
    title_tokens = sorted(raw.get('title_tokens', []), key=len, reverse=True)
    fold_prefixes = sorted(
        (k for k in raw.get('fold_prefixes', []) if k in canonical),
        key=len, reverse=True)
    return {
        'canonical': canonical,
        'title_tokens': title_tokens,
        'fold_prefixes': fold_prefixes,
    }


def resolve_name_en(zh_name, canon):
    """Return the canonical English name for a Chinese entity name, or None
    when no tier matches. `canon` is the structure from load_canon()."""
    if not zh_name:
        return None
    canonical = canon['canonical']

    # Tier 1: exact match wins outright, before any stripping — otherwise a
    # title token inside a legitimate key (院長 in 立法院長…) could reroute it.
    # Single-character keys are allowed here (an explicit entry like 習 is a
    # deliberate call); the strip/fold tiers below require 2+ characters.
    if zh_name in canonical:
        return canonical[zh_name]
    if len(zh_name) < 2:
        return None

    # Tier 2: title-strip. Longest token first so 副總統 is tried before 總統.
    for tok in canon['title_tokens']:
        if tok not in zh_name:
            continue
        tail = zh_name.rsplit(tok, 1)[1]      # title-first: 國防部長顧立雄
        if len(tail) >= 2 and tail in canonical:
            return canonical[tail]
        # Name-first (賴清德總統) only counts when the token IS the ending —
        # otherwise 總統府秘書長潘孟安 would head-match 總統府 and resolve a
        # person row to "Presidential Office".
        if zh_name.endswith(tok):
            head = zh_name[:-len(tok)]
            if len(head) >= 2 and head in canonical:
                return canonical[head]

    # Tier 3: opt-in fold prefixes (longest first).
    for key in canon['fold_prefixes']:
        if zh_name.startswith(key):
            return canonical[key]

    return None
