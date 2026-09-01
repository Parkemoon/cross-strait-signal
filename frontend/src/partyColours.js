// Canonical Taiwan party colours — single source of truth, shared by the poll
// trend charts (PollsTab) and the Key Figures cards (figureAccent). Since the
// Morning Brief redesign these resolve through CSS custom properties defined
// in index.css (light + dark values), so every chart line and chip is
// theme-aware. The hues are muted paper-register derivatives of the
// Wikipedia-canonical party colours; majors ride the alignment tokens
// (DPP → --green, KMT → --blue, TPP → --cyan, PRC → --red).
//
// NB: these values are `var(...)` strings, valid anywhere CSS accepts a
// colour (inline styles, SVG fill/stroke, Recharts props). Never concatenate
// an alpha suffix onto them — use `color-mix(in srgb, <colour> 13%,
// transparent)` for tints.
//
// Collisions to be aware of (rare within one county race; the per-option
// colour_override is the escape hatch): TSP brick-red ≈ PRC red, GPT green ≈
// DPP green, NP gold ≈ NPP yellow, CUPP navy ≈ KMT navy.
export const PARTY_COLOURS = {
  DPP:  "var(--party-dpp)",
  KMT:  "var(--party-kmt)",
  TPP:  "var(--party-tpp)",
  NPP:  "var(--party-npp)",
  TSP:  "var(--party-tsp)",
  GPT:  "var(--party-gpt)",
  NP:   "var(--party-np)",
  PFP:  "var(--party-pfp)",
  CUPP: "var(--party-cupp)",
  IND:  "var(--party-ind)",
  PRC:  "var(--party-prc)",
};

// Picker labels (en + zh) and display order — the big-5 most likely to appear
// in 2026 local-election races first, then minor parties, then independent.
export const PARTY_ORDER = ["DPP", "KMT", "TPP", "NPP", "TSP", "GPT", "NP", "PFP", "CUPP", "IND"];

export const PARTY_LABELS = {
  DPP:  "DPP (民主進步黨)",
  KMT:  "KMT (中國國民黨)",
  TPP:  "TPP (台灣民眾黨)",
  NPP:  "NPP (時代力量)",
  TSP:  "TSP (台灣基進)",
  GPT:  "Green Party (台灣綠黨)",
  NP:   "New Party (新黨)",
  PFP:  "PFP (親民黨)",
  CUPP: "CUPP (統促黨)",
  IND:  "Independent (無黨籍)",
};

// Resolve a party code to its colour (a CSS var() string), or null.
export function partyColour(party) {
  return (party && PARTY_COLOURS[party]) || null;
}

// Translucent tint of any CSS colour (hex or var()) — the safe replacement
// for the old `${hex}22` concatenation, which var() strings break.
export function partyTint(colour, pct = 13) {
  return colour ? `color-mix(in srgb, ${colour} ${pct}%, transparent)` : null;
}
