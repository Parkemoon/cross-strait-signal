// Canonical Taiwan party colours — single source of truth, shared by the poll
// trend charts (PollsTab) and the Key Figures cards (figureAccent). Values are
// the Wikipedia-canonical party colours. `PRC` is kept (red) for PRC-side
// figures, state-pollster chips, and CCP series — it is not a party row in the
// picker. `IND` = independent / non-aligned.
//
// Collisions to be aware of (rare within one county race; the per-option
// colour_override is the escape hatch): TSP brick-red ≈ PRC red, GPT green ≈
// DPP green, NP gold ≈ NPP yellow, CUPP navy ≈ KMT navy.
export const PARTY_COLOURS = {
  DPP:  "#1B9431",
  KMT:  "#000099",
  TPP:  "#28C7C7",
  NPP:  "#FFE31A",
  TSP:  "#A73F24",
  GPT:  "#3AB483",
  NP:   "#FFD700",
  PFP:  "#FF6310",
  CUPP: "#253686",
  IND:  "#6b7280",
  PRC:  "#dc2626",
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

// Resolve a party code to its hex, or null when unknown.
export function partyColour(party) {
  return (party && PARTY_COLOURS[party]) || null;
}
