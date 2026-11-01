"""Scientific sentiment score calibration and Source x Topic baseline decomposition.

De-heaps the discrete 0.1-increment LLM sentiment_score using a camp-conditioned
continuous lexical probe (TF-IDF 1-2 gram + Ridge trained against the
Gemini-DeepSeek consensus target), clamps the blended score strictly inside its
editorial sentiment band (so band checks in review.py and sentimentBand.js never
trip), and computes the Empirical-Bayes Source x 24-Topic baseline expectation
(sentiment_baseline) and residual excess tone (sentiment_excess).

Pure Python / standard library implementation: zero PyTorch or scikit-learn
runtime dependency, <0.2 ms per article.
"""
from __future__ import annotations

import json
import math
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple

_MODEL_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "sentiment_calibration_model.json"
)
_TOKEN_RE = re.compile(r"\b[a-zA-Z][a-zA-Z\-]{1,}\b")


class CalibratedSentiment(NamedTuple):
    sentiment_score: float
    sentiment_score_raw: float
    sentiment_baseline: float
    sentiment_excess: float
    continuous_probe: float


def camp_of_bias(bias: str | None) -> str:
    b = (bias or "").strip()
    if b in ("green", "green_leaning"):
        return "green_camp"
    if b in ("blue", "blue_leaning"):
        return "blue_camp"
    if b in ("state_official", "state_nationalist"):
        return "prc_state"
    return "centrist_camp"


def raw_fits_band(score: float, sentiment_label: str | None) -> bool:
    """Return True if raw score is already consistent with the editorial label band."""
    lbl = (sentiment_label or "").strip().lower()
    if lbl == "hostile":
        return score <= -0.3
    if lbl == "cooperative":
        return score >= 0.3
    if lbl == "neutral":
        return abs(score) <= 0.3
    return True


def clamp_to_band(score: float, sentiment_label: str | None) -> float:
    """Clamp a continuous score strictly inside the editorial label band."""
    lbl = (sentiment_label or "").strip().lower()
    if lbl == "hostile":
        return float(min(-0.32, max(-0.98, score)))
    if lbl == "cooperative":
        return float(max(0.32, min(0.98, score)))
    if lbl == "neutral":
        return float(max(-0.28, min(0.28, score)))
    return float(max(-0.98, min(0.98, score)))


@lru_cache(maxsize=1)
def _load_model() -> dict:
    with open(_MODEL_PATH, encoding="utf-8") as f:
        return json.load(f)


def _strip_accents_unicode(text: str) -> str:
    norm = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in norm if not unicodedata.combining(ch))


def predict_continuous_probe(
    title_en: str | None,
    summary_en: str | None,
    key_quote_en: str | None = None,
    source_bias: str | None = None,
) -> float:
    """Predict continuous sentiment in [-1.0, 1.0] from English article fields."""
    model = _load_model()
    vocab: dict[str, int] = model["tfidf"]["vocab"]
    idf: list[float] = model["tfidf"]["idf"]
    camp = camp_of_bias(source_bias)
    camp_entry = model["camp_models"].get(camp) or model["camp_models"]["centrist_camp"]
    weights: list[float] = camp_entry["weights"]
    bias_val: float = float(camp_entry["bias"])

    t = (title_en or "").strip()
    s = (summary_en or "").strip()
    q = (key_quote_en or "").strip()
    text = f"{t} . {s} . QUOTE: {q}" if q else f"{t} . {s}"
    cleaned = _strip_accents_unicode(text).lower()
    tokens = _TOKEN_RE.findall(cleaned)
    if not tokens:
        return max(-1.0, min(1.0, round(bias_val, 4)))

    tf_counts: dict[int, int] = {}
    for tok in tokens:
        idx = vocab.get(tok)
        if idx is not None:
            tf_counts[idx] = tf_counts.get(idx, 0) + 1
    for i in range(len(tokens) - 1):
        bg = f"{tokens[i]} {tokens[i + 1]}"
        idx = vocab.get(bg)
        if idx is not None:
            tf_counts[idx] = tf_counts.get(idx, 0) + 1

    if not tf_counts:
        return max(-1.0, min(1.0, round(bias_val, 4)))

    weighted: list[tuple[int, float]] = []
    norm_sq = 0.0
    for idx, count in tf_counts.items():
        val = (1.0 + math.log(count)) * idf[idx]
        weighted.append((idx, val))
        norm_sq += val * val

    if norm_sq <= 0.0:
        return max(-1.0, min(1.0, round(bias_val, 4)))

    inv_norm = 1.0 / math.sqrt(norm_sq)
    dot = bias_val
    for idx, val in weighted:
        dot += (val * inv_norm) * weights[idx]

    return float(max(-1.0, min(1.0, dot)))


def lookup_source_topic_baseline(
    source_name: str | None,
    topic_primary: str | None,
    source_bias: str | None = None,
) -> float:
    """Return the Empirical-Bayes expected sentiment score for (source_name, topic_primary)."""
    model = _load_model()
    b = model["baselines"]
    src = (source_name or "").strip()
    top = (topic_primary or "").strip()
    cell_key = f"{src}|||{top}"
    if cell_key in b["cells"]:
        return float(b["cells"][cell_key])

    mu_0 = float(b["mu_0"])
    if src in b["alpha_source"]:
        alpha_s = float(b["alpha_source"][src])
    else:
        alpha_s = float(b["camp_alpha"].get(camp_of_bias(source_bias), 0.0))
    beta_t = float(b["beta_topic"].get(top, 0.0))
    return round(max(-0.98, min(0.98, mu_0 + alpha_s + beta_t)), 3)


def calibrate_sentiment_score(
    raw_score: float | None,
    sentiment_label: str | None,
    source_name: str | None,
    source_bias: str | None,
    topic_primary: str | None,
    title_en: str | None = None,
    summary_en: str | None = None,
    key_quote_en: str | None = None,
    continuous_pred: float | None = None,
    preserve_exact_score: bool = False,
) -> CalibratedSentiment | None:
    """Compute calibrated score, raw score, Source x Topic baseline, and excess tone.

    When preserve_exact_score=True (used when an analyst has explicitly set a
    score_override), sentiment_score is kept at raw_score and sentiment_excess
    is computed directly against the Source x Topic baseline.
    """
    if raw_score is None:
        return None
    raw_f = float(raw_score)
    baseline = lookup_source_topic_baseline(source_name, topic_primary, source_bias)

    if continuous_pred is None:
        cont = predict_continuous_probe(
            title_en=title_en,
            summary_en=summary_en,
            key_quote_en=key_quote_en,
            source_bias=source_bias,
        )
    else:
        cont = float(max(-1.0, min(1.0, continuous_pred)))

    if preserve_exact_score or not raw_fits_band(raw_f, sentiment_label):
        cal = round(raw_f, 2)
    else:
        blended = round(0.55 * raw_f + 0.45 * cont, 2)
        cal = round(clamp_to_band(blended, sentiment_label), 2)

    excess = round(cal - baseline, 3)
    return CalibratedSentiment(
        sentiment_score=cal,
        sentiment_score_raw=round(raw_f, 2),
        sentiment_baseline=round(baseline, 3),
        sentiment_excess=excess,
        continuous_probe=round(cont, 4),
    )


def refresh_article_sentiment_excess(conn, article_id: int) -> None:
    """Recompute sentiment_baseline and sentiment_excess after an analyst override."""
    row = conn.execute(
        """
        SELECT ai.sentiment_score, ai.topic_primary, s.name AS source_name, s.bias AS source_bias
        FROM ai_analysis ai
        JOIN articles a ON a.id = ai.article_id
        LEFT JOIN sources s ON s.id = a.source_id
        WHERE ai.article_id = ?
        """,
        (article_id,),
    ).fetchone()
    if not row or row[0] is None:
        return
    score = float(row[0])
    baseline = lookup_source_topic_baseline(row[2], row[1], row[3])
    excess = round(score - baseline, 3)
    conn.execute(
        """
        UPDATE ai_analysis
        SET sentiment_baseline = ?, sentiment_excess = ?
        WHERE article_id = ?
        """,
        (round(baseline, 3), excess, article_id),
    )

