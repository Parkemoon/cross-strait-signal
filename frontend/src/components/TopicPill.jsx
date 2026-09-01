// Topic label — deliberately uncoloured since the Morning Brief restyle.
// The metadata line colours exactly two things: the alignment tag (System A)
// and the sentiment score (System B); giving topics their own hues was a
// third colour system fighting the other two.
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
