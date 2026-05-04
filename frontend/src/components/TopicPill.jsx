const TOPIC_LABELS = {
  MIL_EXERCISE:    "Military Exercise",
  MIL_MOVEMENT:    "Force Movement",
  MIL_HARDWARE:    "Hardware",
  MIL_POLICY:      "Mil. Policy",
  DIP_STATEMENT:   "Diplomacy",
  DIP_VISIT:       "Diplomatic Visit",
  DIP_SANCTIONS:   "Sanctions",
  PARTY_VISIT:     "Party Visit",
  ECON_TRADE:      "Trade",
  ECON_INVEST:     "Investment",
  POL_DOMESTIC_TW: "TW Politics",
  POL_DOMESTIC_PRC:"PRC Politics",
  POL_TONGDU:      "統獨",
  INFO_WARFARE:    "Info Warfare",
  LEGAL_GREY:      "Grey Zone",
  TRANSPORT:       "Transport",
  INT_ORG:         "Intl Orgs",
  HUMANITARIAN:    "Humanitarian",
  US_PRC:          "US-PRC",
  US_TAIWAN:       "US-Taiwan",
  HK_MAC:          "HK/Macao",
  CULTURE:         "Culture",
  CYBER:           "Cyber",
  ARMS_SALES:      "Arms Sales",
  SPORT:           "Sport",
  ENERGY:          "Energy",
  SCI_TECH:        "Sci/Tech",
};

const TOPIC_COLORS = {
  MIL_EXERCISE:    "var(--accent-red)",
  MIL_MOVEMENT:    "var(--accent-red)",
  MIL_HARDWARE:    "var(--accent-red)",
  MIL_POLICY:      "var(--accent-amber)",
  DIP_STATEMENT:   "var(--accent-amber)",
  DIP_VISIT:       "var(--accent-amber)",
  DIP_SANCTIONS:   "var(--accent-amber)",
  PARTY_VISIT:     "var(--accent-amber)",
  ARMS_SALES:      "var(--accent-amber)",
  ECON_TRADE:      "var(--accent-green)",
  ECON_INVEST:     "var(--accent-green)",
  ENERGY:          "var(--accent-green)",
  SCI_TECH:        "var(--accent-green)",
  POL_DOMESTIC_TW: "var(--accent-purple)",
  POL_DOMESTIC_PRC:"var(--accent-purple)",
  POL_TONGDU:      "var(--accent-red)",
  INFO_WARFARE:    "var(--accent-red)",
  CYBER:           "var(--accent-red)",
  LEGAL_GREY:      "var(--accent-teal)",
  TRANSPORT:       "var(--accent-teal)",
  HK_MAC:          "var(--accent-teal)",
  CULTURE:         "var(--accent-teal)",
  SPORT:           "var(--accent-teal)",
  INT_ORG:         "var(--accent-blue)",
  HUMANITARIAN:    "var(--accent-blue)",
  US_PRC:          "var(--accent-blue)",
  US_TAIWAN:       "var(--accent-blue)",
};

export default function TopicPill({ topic, onClick }) {
  const color = TOPIC_COLORS[topic] || "var(--text-muted)";
  const label = TOPIC_LABELS[topic] || topic?.replace(/_/g, " ");

  return (
    <span
      onClick={onClick ? (e) => { e.stopPropagation(); onClick(topic); } : undefined}
      style={{
        border: `1px solid ${color}`,
        color: color,
        padding: "2px 10px",
        borderRadius: "2px",
        fontSize: "11px",
        fontFamily: "var(--font-mono)",
        letterSpacing: "0.3px",
        cursor: onClick ? "pointer" : "default",
        transition: "opacity 0.15s",
      }}
      title={onClick ? `Filter by ${label}` : undefined}
    >
      {label}
    </span>
  );
}