// Shared label maps for the alt-model experiment UI — single source for
// AltModelPanel (card strip), AltModelsTab (aggregates) and AltModelLens
// (feed toggle). Add new sweep models here once, not per-component.

export const MODEL_LABELS = {
  "deepseek/deepseek-v4-flash": "DeepSeek V4 Flash",
  "moonshotai/kimi-k3": "Kimi K3",
};

export const ARM_LABELS = {
  neutral: "Neutral host",
  originator: "Originator endpoint",
  control: "Gemini control",
};

export const modelLabel = (m) => MODEL_LABELS[m] || m;
export const armLabel = (a) => ARM_LABELS[a] || a;

// Models dropped from the experiment's UI surfaces (tab, feed lens). Sweep
// rows stay in the DB and the API still serves them — this is presentation-
// side retirement only, so the write-up's numbers remain reproducible.
export const RETIRED_MODELS = new Set([
  "moonshotai/kimi-k3", // evaluated, cleared, not proceeding to production
]);

export const isRetiredModel = (m) => RETIRED_MODELS.has(m);

// Per-model accent tints — wash the feed cards and lens bar under an active
// model lens so it's visually obvious you're not looking at production Gemini.
export const MODEL_TINTS = {
  "deepseek/deepseek-v4-flash": "#4d6bfe", // DeepSeek brand blue
  "moonshotai/kimi-k3": "#7c3aed",
};

export const modelTint = (m) => MODEL_TINTS[m] || "#14b8a6";

export const modelTintRgba = (m, alpha) => {
  const hex = modelTint(m);
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r},${g},${b},${alpha})`;
};
