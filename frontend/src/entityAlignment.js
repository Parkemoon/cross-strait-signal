// Alignment marker for the Feed rail's KEY ENTITIES (Morning Brief §1.7):
// 6px SQUARE, filled = party or state organ, hollow = a Taiwan government
// body acting in a state capacity, none = a third-country actor or an
// entity this map does not know. Same rule as the feed metadata, the
// Voices attribution and the visit badges (BIAS_META / HOLLOW_AFFILIATIONS).
//
// Two sources, checked in order:
//   1. the curated key-figure roster (/api/stats/key-figures: side + party)
//      — passed in by the caller, so roster edits need no change here;
//   2. this file's ORGANISATIONS and PEOPLE tables, matched on the
//      lowercased English canonical name (entity_name_en) — substring for
//      organisations (the DB carries "(DPP)"-style suffixes and variants),
//      exact for people.
//
// PEOPLE is hand-curated like key_figures.json: a wrong party marker on a
// named politician is a credibility problem, so only affiliations that are
// a matter of public record belong here. Leave a name out rather than guess.
// Ministries are Taiwan's unless the name says otherwise: the corpus writes
// Beijing's as "PRC MFA" / "Ministry of National Defense of the PRC".

const G = "var(--green)";
const B = "var(--blue)";
const C = "var(--cyan)";
const R = "var(--red)";

// [needle (lowercase substring), colour, hollow]
const ORGANISATIONS = [
  // Taiwan parties — filled
  ["democratic progressive party", G, false],
  ["kuomintang", B, false],
  ["taiwan people's party", C, false],
  ["new power party", "var(--party-npp)", false],
  ["taiwan statebuilding party", "var(--party-tsp)", false],
  // Taiwan state bodies — hollow green
  ["mainland affairs council", G, true],
  ["executive yuan", G, true],
  ["legislative yuan", G, true],
  ["presidential office", G, true],
  ["office of the president", G, true],
  ["coast guard administration", G, true],
  ["straits exchange foundation", G, true],
  ["national security council", G, true],
  ["national security bureau", G, true],
  ["ministry of national defense (mnd)", G, true],
  ["ministry of national defense (mnd", G, true],
  ["ministry of economic affairs", G, true],
  ["ministry of the interior", G, true],
  ["central news agency", G, true],
  ["ocean affairs council", G, true],
  ["republic of china armed forces", G, true],
  ["roc armed forces", G, true],
  // PRC party / state — filled red
  ["taiwan affairs office", R, false],
  ["chinese communist party", R, false],
  ["communist party of china", R, false],
  ["people's liberation army", R, false],
  ["eastern theater command", R, false],
  ["china coast guard", R, false],
  ["state council", R, false],
  ["national people's congress", R, false],
  ["cppcc", R, false],
  ["prc ministry", R, false],
  ["prc mfa", R, false],
  ["ministry of foreign affairs of the prc", R, false],
  ["ministry of foreign affairs (prc", R, false],
  ["ministry of national defense (prc", R, false],
  ["association for relations across the taiwan straits", R, false],
  ["united front work department", R, false],
  ["china taiwan net", R, false],
  ["xinhua", R, false],
  ["global times", R, false],
  ["people's daily", R, false],
  ["china news service", R, false],
  ["cctv", R, false],
  ["fujian province", R, false],
];

// exact lowercased English name → [colour, hollow]
const PEOPLE = {
  // Taiwan — DPP
  "tsai ing-wen": [G, false],
  "hsiao bi-khim": [G, false],
  "chen shui-bian": [G, false],
  "lin chia-lung": [G, false],
  "puma shen": [G, false],
  "hung sun-han": [G, false],
  "wang ting-yu": [G, false],
  "ker chien-ming": [G, false],
  // Taiwan — KMT
  "han kuo-yu": [B, false],
  "chiang wan-an": [B, false],
  "lu shiow-yen": [B, false],
  "ma ying-jeou": [B, false],
  "fu kun-chi": [B, false],
  "johnny chiang": [B, false],
  "eric chu": [B, false],
  "hsiao tsu-tsen": [B, false],
  "andrew hsia": [B, false],
  "weng hsiao-ling": [B, false],
  "ko chih-en": [B, false],
  "lin chu-yin": [B, false],
  "chen i-hsin": [B, false],
  "wang hung-wei": [B, false],
  "hung hsiu-chu": [B, false],
  "lien chan": [B, false],
  // Taiwan — TPP
  "ko wen-je": [C, false],
  // PRC
  "wang huning": [R, false],
  "zhang han": [R, false],
  "chen binhua": [R, false],
  "wang yi": [R, false],
  "li qiang": [R, false],
  "wu qian": [R, false],
  "mao ning": [R, false],
  "lin jian": [R, false],
  "guo jiakun": [R, false],
};

/**
 * Resolve an entity's alignment marker.
 * @param name   entity_name_en as stored
 * @param type   entity_type ('person', 'organisation', 'military_unit', …)
 * @param figures the key-figures roster ([{name_en, side, party}]) or []
 * @returns {{colour: string, hollow: boolean} | null}
 */
export function entityAlignment(name, type, figures = []) {
  const key = (name || "").trim().toLowerCase();
  if (!key) return null;

  if (type === "person" || type == null) {
    const fig = figures.find((f) => (f.name_en || "").toLowerCase() === key);
    if (fig) {
      if (fig.party === "DPP") return { colour: G, hollow: false };
      if (fig.party === "KMT") return { colour: B, hollow: false };
      if (fig.party === "TPP") return { colour: C, hollow: false };
      if (fig.side === "PRC") return { colour: R, hollow: false };
      if (fig.side === "TW") return { colour: G, hollow: true };   // TW official without a party
    }
    const p = PEOPLE[key];
    if (p) return { colour: p[0], hollow: p[1] };
  }

  if (type !== "person") {
    for (const [needle, colour, hollow] of ORGANISATIONS) {
      if (key.includes(needle)) return { colour, hollow };
    }
  }
  return null;
}
