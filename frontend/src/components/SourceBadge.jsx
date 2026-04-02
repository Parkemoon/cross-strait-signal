const SOURCE_COLORS = {
  PRC: { bg: "#e53e3e22", border: "#e53e3e", text: "#e53e3e" },
  TW: { bg: "#3182ce22", border: "#3182ce", text: "#3182ce" },
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
  const abbrev = SOURCE_ABBREV[sourceName] || sourceName?.slice(0, 3).toUpperCase();

  return (
    <span
      style={{
        background: colors.bg,
        border: `1px solid ${colors.border}`,
        color: colors.text,
        padding: "2px 8px",
        borderRadius: "3px",
        fontSize: "11px",
        fontWeight: 700,
        fontFamily: "'JetBrains Mono', 'Courier New', monospace",
        letterSpacing: "0.5px",
      }}
    >
      {abbrev}
    </span>
  );
}