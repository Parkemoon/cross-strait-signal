const TOPIC_LABELS = {
  MIL_EXERCISE: "Military Exercise",
  MIL_MOVEMENT: "Force Movement",
  MIL_HARDWARE: "Hardware",
  DIP_STATEMENT: "Diplomacy",
  DIP_VISIT: "State Visit",
  DIP_SANCTIONS: "Sanctions",
  ECON_TRADE: "Trade",
  ECON_INVEST: "Investment",
  POL_DOMESTIC: "Domestic",
  POL_TONGDU: "統獨",
  INFO_WARFARE: "Info Warfare",
  LEGAL_GREY: "Grey Zone",
  HUMANITARIAN: "Humanitarian",
};

const TOPIC_COLORS = {
  MIL_EXERCISE: "var(--accent-red)",
  MIL_MOVEMENT: "var(--accent-red)",
  MIL_HARDWARE: "var(--accent-red)",
  DIP_STATEMENT: "var(--accent-amber)",
  DIP_VISIT: "var(--accent-amber)",
  DIP_SANCTIONS: "var(--accent-amber)",
  ECON_TRADE: "var(--accent-green)",
  ECON_INVEST: "var(--accent-green)",
  POL_DOMESTIC: "var(--accent-purple)",
  POL_TONGDU: "var(--accent-red)",
  INFO_WARFARE: "var(--accent-amber)",
  LEGAL_GREY: "var(--accent-teal)",
  HUMANITARIAN: "var(--accent-blue)",
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