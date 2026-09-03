// Alignment tag — System A (who is speaking). A typographic marker + abbrev
// in the alignment colour, replacing the old solid colour blocks.
// Full-saturation squares = committed positions / state organs; softer dots =
// leaning / centrist bands. The hollow square is reserved for TW government
// bodies acting in a state capacity (entities/speakers, not outlets).
export const BIAS_META = {
  green:             { colour: "var(--green)", marker: "■", label: "Green" },
  green_leaning:     { colour: "var(--gsoft)", marker: "●", label: "Green-leaning" },
  blue:              { colour: "var(--blue)",  marker: "■", label: "Blue" },
  blue_leaning:      { colour: "var(--bsoft)", marker: "●", label: "Blue-leaning" },
  centrist:          { colour: "var(--muted)", marker: "●", label: "Centrist" },
  china_centrist:    { colour: "var(--rose)",  marker: "●", label: "China-centrist" },
  state_official:    { colour: "var(--red)",   marker: "■", label: "PRC state" },
  state_nationalist: { colour: "var(--nat)",   marker: "■", label: "State nationalist" },
};

// Section feed → publication display name (LTN Politics → Liberty Times).
// Single source for the article card, the sidebar's source grouping and
// anything else that names an outlet in full.
export const PUBLICATION_NAMES = {
  // Liberty Times
  "LTN Politics":      "Liberty Times",
  "LTN World":         "Liberty Times",
  "LTN Business":      "Liberty Times",
  "LTN Defence":       "Liberty Times",
  // CNA
  "CNA Politics":      "CNA",
  "CNA Mainland":      "CNA",
  "CNA International": "CNA",
  "CNA Finance":       "CNA",
  // United Daily News
  "UDN":               "United Daily News",
  "UDN Breaking":      "United Daily News",
  "UDN International": "United Daily News",
  "UDN Business":      "United Daily News",
  // China Times
  "CT Cross-Strait":   "China Times",
  "CT Politics":       "China Times",
  "CT Military":       "China Times",
  "CT Opinion":        "China Times",
  // Single-feed sources — display names
  "YDN":                     "Youth Daily News",
  "Xinhua Chinese":          "Xinhua",
  "People's Daily Politics": "People's Daily",
  "China News Service":      "China News Service",
  "Global Times":            "Global Times",
  "The Paper":               "The Paper",
  "PRC MFA Spokesperson":    "MFA Spokesperson",
  "Taiwan Affairs Office":   "Taiwan Affairs Office",
  "Guancha":                 "Guancha",
  "Haixia Daobao":           "Haixia Daobao",
  "PLA Daily":               "PLA Daily",
  "Zaobao Cross-Strait":     "Zaobao",
  "BBC Chinese":             "BBC Chinese",
  "RTHK Greater China":      "RTHK",
  // Ming Pao
  "Ming Pao Cross-Strait":   "Ming Pao",
  "Ming Pao Editorial":      "Ming Pao",
  "Ming Pao Opinion":        "Ming Pao",
};

const SOURCE_ABBREV = {
  // TW — green (all LTN sections → LTN)
  "Liberty Times":     "LTN",
  "LTN Politics":      "LTN",
  "LTN World":         "LTN",
  "LTN Business":      "LTN",
  "LTN Defence":       "LTN",
  // TW — green_leaning (all CNA sections → CNA)
  "CNA Chinese":       "CNA",
  "CNA Politics":      "CNA",
  "CNA Mainland":      "CNA",
  "CNA International": "CNA",
  "CNA Finance":       "CNA",
  // TW — blue (all CT sections → CT)
  "CT Cross-Strait":   "CT",
  "CT Politics":       "CT",
  "CT Military":       "CT",
  "CT Opinion":        "CT",
  // TW — blue (all UDN sections → UDN)
  "UDN":                  "UDN",
  "UDN Cross-Strait":     "UDN",
  "UDN Breaking":         "UDN",
  "UDN International":    "UDN",
  "UDN Business":         "UDN",
  // TW — green_leaning (MND state media, under DPP executive)
  "YDN":               "YDN",
  // PRC — state_official
  "Xinhua Chinese":         "XH",
  "People's Daily Politics":"PD",
  "China News Service":     "CNS",
  "The Paper":              "TP",
  "Guangming Daily":        "GM",
  "Haixia Daobao":          "HXD",
  "PLA Daily":              "PLA",
  "PRC MFA Spokesperson":   "MFA",
  "Taiwan Affairs Office":  "TAO",
  "China Taiwan Net":       "CTN",
  // PRC — state_nationalist
  "Global Times":  "GT",
  "Guancha":       "GC",
  // HK — state_official (post-NSL)
  "RTHK Greater China": "RTHK",
  // HK — china_centrist
  "Ming Pao Cross-Strait": "MP",
  "Ming Pao Editorial":    "MP",
  "Ming Pao Opinion":      "MP",
  // UK — centrist
  "BBC Chinese": "BBC",
  // SG — centrist
  "Zaobao Cross-Strait": "ZB",
};

// Source place code → the label that opens the attribution ("which side is
// speaking" comes before "which outlet"). Codes are `sources.place`.
export const PLACE_LABEL = {
  PRC: "PRC", TW: "TAIWAN", HK: "HONG KONG", MO: "MACAO", SG: "SINGAPORE", UK: "UK",
};

/** Faint wash of an alignment colour for a card ground — the side tint. */
export const alignmentTint = (bias, pct = 6) => {
  const meta = BIAS_META[bias];
  return meta ? `color-mix(in srgb, ${meta.colour} ${pct}%, transparent)` : undefined;
};

/**
 * Alignment tag. `place` prepends the source's side ("TAIWAN · ■ Liberty
 * Times"); `full` names the publication in full on desktop and falls back
 * to the abbreviation under 768px (`.outlet-full` / `.outlet-abbr` in
 * index.css). Without either it is the compact "■ LTN" used in tight spots.
 */
export default function SourceBadge({ sourceName, bias, place, full = false }) {
  const meta = BIAS_META[bias] || { colour: "var(--muted)", marker: "●", label: bias || "Unclassified" };
  const abbrev = SOURCE_ABBREV[sourceName] || sourceName?.slice(0, 4).toUpperCase();
  const fullName = PUBLICATION_NAMES[sourceName] || sourceName;
  const placeLabel = place ? (PLACE_LABEL[place] || place.toUpperCase()) : null;

  return (
    <span
      title={`${sourceName} · ${meta.label}`}
      style={{
        color: meta.colour,
        fontSize: "9.5px",
        fontWeight: 700,
        fontFamily: "var(--font-mono)",
        letterSpacing: "0.08em",
        whiteSpace: "nowrap",
        cursor: "default",
      }}
    >
      {placeLabel && (
        <span style={{ color: "var(--muted)", fontWeight: 500, marginRight: "6px" }}>{placeLabel} ·</span>
      )}
      <span style={{ fontSize: "8px", marginRight: "4px", verticalAlign: "1px" }}>{meta.marker}</span>
      {full ? (
        <>
          <span className="outlet-full">{fullName}</span>
          <span className="outlet-abbr">{abbrev}</span>
        </>
      ) : abbrev}
    </span>
  );
}
