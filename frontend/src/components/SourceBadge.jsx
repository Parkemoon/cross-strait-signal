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

export default function SourceBadge({ sourceName, bias }) {
  const meta = BIAS_META[bias] || { colour: "var(--muted)", marker: "●", label: bias || "Unclassified" };
  const abbrev = SOURCE_ABBREV[sourceName] || sourceName?.slice(0, 4).toUpperCase();

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
      <span style={{ fontSize: "8px", marginRight: "4px", verticalAlign: "1px" }}>{meta.marker}</span>
      {abbrev}
    </span>
  );
}
