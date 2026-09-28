// Framing-sentiment band colour — System B, single source of truth.
// ±0.3 neutral band (boundary values are neutral, matching the About
// legend's "−0.3 to +0.3 Neutral"): hostile = purple, cooperative = amber,
// neutral = grey. Used by the masthead ticker, the rail gauges, and the
// trend chart — import this, never re-implement the thresholds.
export function bandColour(score) {
  if (score == null) return "var(--muted)";
  if (score > 0.3) return "var(--coop)";
  if (score < -0.3) return "var(--hostile)";
  return "var(--neut)";
}

const LABEL_BAND = {
  hostile: "var(--hostile)",
  cooperative: "var(--coop)",
  neutral: "var(--neut)",
};

// Whether a sentiment label and score agree — the band the score falls in
// must be the label's band ('mixed' takes any score). The review desk uses
// this so an override can't leave a score that colours the other way; the
// API applies the same rule (api/routes/review.py _score_problem).
export function scoreFitsLabel(label, score) {
  const band = LABEL_BAND[label];
  if (!band) return true;
  return score != null && bandColour(score) === band;
}
