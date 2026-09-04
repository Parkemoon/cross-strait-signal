"""Sentiment score → band, the Python twin of frontend/src/sentimentBand.js.

One place for the ±0.3 thresholds on the server side (the digest and the
LinkedIn proposer both print banded scores). Keep in step with
`bandColour` in sentimentBand.js — the bands are locked project-wide
(CLAUDE.md → Sentiment colour convention).
"""
from __future__ import annotations

HOSTILE_MAX = -0.3
COOPERATIVE_MIN = 0.3


def sentiment_band(score: float | None) -> str | None:
    """'hostile' / 'neutral' / 'cooperative', or None for a missing score."""
    if score is None:
        return None
    if score <= HOSTILE_MAX:
        return 'hostile'
    if score >= COOPERATIVE_MIN:
        return 'cooperative'
    return 'neutral'
