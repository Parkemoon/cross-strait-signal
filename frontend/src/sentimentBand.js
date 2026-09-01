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
