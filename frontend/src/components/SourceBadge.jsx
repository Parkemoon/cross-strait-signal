const SOURCE_COLORS = {
  PRC: { bg: "var(--accent-red)", text: "#fff" },
  TW: { bg: "var(--accent-blue)", text: "#fff" },
};

const SOURCE_ABBREV = {
  "Taiwan Affairs Office": "TAO",
  "PRC MFA Spokesperson": "MFA",
  "Xinhua Chinese": "XH",
  "CNA Chinese": "CNA",
  "People's Daily Politics": "PD",
  "China News Service": "CNS",
  "Liberty Times": "LT",
  "Taipei Times": "TT",
  "Global Times Chinese": "GT",
  "CGTN World": "CGTN",
};

export default function SourceBadge({ sourceName, country }) {
  const colors = SOURCE_COLORS[country] || SOURCE_COLORS.PRC;
  const abbrev =
    SOURCE_ABBREV[sourceName] || sourceName?.slice(0, 3).toUpperCase();

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
      }}
    >
      {abbrev}
    </span>
  );
}
