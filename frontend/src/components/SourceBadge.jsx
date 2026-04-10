// Bias → background colour mapping
// PRC: red shades  |  TW green: green shades  |  TW blue: blue shades  |  centrist: grey
const BIAS_COLORS = {
  state_nationalist: { bg: "#b91c1c", text: "#fff" },   // deep red
  state_official:    { bg: "#dc2626", text: "#fff" },   // red
  green:             { bg: "#15803d", text: "#fff" },   // deep green
  green_leaning:     { bg: "#4ade80", text: "#14532d" },// light green, dark text
  blue:              { bg: "#1d4ed8", text: "#fff" },   // blue
  blue_leaning:      { bg: "#93c5fd", text: "#1e3a5f" },// light blue, dark text
  centrist:          { bg: "#6b7280", text: "#fff" },   // grey
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
  // PRC — state_nationalist
  "Global Times":  "GT",
  "Guancha":       "GC",
  // HK — state_official (post-NSL)
  "RTHK Greater China": "RTHK",
  // HK — centrist
  "Ming Pao Cross-Strait": "MP",
  "Ming Pao Editorial":    "MP",
  "Ming Pao Opinion":      "MP",
  // SG — centrist
  "Zaobao Cross-Strait": "ZB",
};

export default function SourceBadge({ sourceName, bias }) {
  const colors = BIAS_COLORS[bias] || { bg: "#6b7280", text: "#fff" };
  const abbrev = SOURCE_ABBREV[sourceName] || sourceName?.slice(0, 4).toUpperCase();

  return (
    <span
      style={{
        background: colors.bg,
        color: colors.text,
        padding: "2px 8px",
        borderRadius: "2px",
        fontSize: "10px",
        fontWeight: 600,
        fontFamily: "var(--font-mono)",
        letterSpacing: "0.5px",
        whiteSpace: "nowrap",
      }}
    >
      {abbrev}
    </span>
  );
}
