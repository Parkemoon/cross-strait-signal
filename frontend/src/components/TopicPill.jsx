// Topic label — deliberately uncoloured since the Morning Brief restyle.
// The metadata line colours exactly two things: the alignment tag (System A)
// and the sentiment score (System B); giving topics their own hues was a
// third colour system fighting the other two.
const TOPIC_LABELS = {
  // 24 active categories
  MIL_EXERCISE:       "Military Exercise",
  MIL_MOVEMENT:       "Force Movement",
  MIL_HARDWARE:       "Hardware",
  MIL_POLICY:         "Mil. Policy",
  ARMS_SALES:         "Arms Sales",
  MARITIME_GREY:      "Maritime Grey-Zone",
  SEC_LAWFARE:        "Espionage & Lawfare",
  INFO_CYBER:         "Info & Cyber",
  POL_TONGDU:         "統獨",
  CROSS_STRAIT_REG:   "Cross-Strait Reg.",
  CULTURE:            "Culture",
  UNITED_FRONT_INTEG: "United Front",
  PARTY_VISIT:        "Party Visit",
  US_RELATIONS:       "US Relations",
  INTL_RELATIONS:     "Third-Country Dip.",
  DIP_VISIT:          "Diplomatic Visit",
  INT_ORG:            "Intl Orgs",
  DIP_SANCTIONS:      "Sanctions",
  POL_DOMESTIC_TW:    "TW Politics",
  POL_DOMESTIC_PRC:   "PRC Politics",
  HK_MAC:             "HK/Macao",
  ECON_TRADE:         "Trade & Economy",
  SCI_TECH:           "Sci/Tech",
  TRANSPORT:          "Transport",
  // Legacy fallback labels for historical alt-model sweep rows
  DIP_STATEMENT:      "Diplomacy",
  ECON_INVEST:        "Investment",
  INFO_WARFARE:       "Info Warfare",
  LEGAL_GREY:         "Grey Zone",
  HUMANITARIAN:       "Humanitarian",
  US_PRC:             "US-PRC",
  US_TAIWAN:          "US-Taiwan",
  CYBER:              "Cyber",
  SPORT:              "Sport",
  ENERGY:             "Energy",
};

export default function TopicPill({ topic, onClick }) {
  const label = TOPIC_LABELS[topic] || topic?.replace(/_/g, " ");

  return (
    <span
      onClick={onClick ? (e) => { e.stopPropagation(); onClick(topic); } : undefined}
      onMouseEnter={onClick ? (e) => { e.currentTarget.style.color = "var(--ink)"; } : undefined}
      onMouseLeave={onClick ? (e) => { e.currentTarget.style.color = "var(--faint)"; } : undefined}
      style={{
        color: "var(--faint)",
        fontSize: "9px",
        fontFamily: "var(--font-mono)",
        letterSpacing: "0.08em",
        textTransform: "uppercase",
        cursor: onClick ? "pointer" : "default",
        lineHeight: 1.4,
        whiteSpace: "nowrap",
      }}
      title={onClick ? `Filter by ${label}` : undefined}
    >
      {label}
    </span>
  );
}
