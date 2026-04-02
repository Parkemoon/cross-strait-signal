const TOPIC_COLORS = {
  MIL_EXERCISE: "#e53e3e",
  MIL_MOVEMENT: "#e53e3e",
  MIL_HARDWARE: "#c53030",
  DIP_STATEMENT: "#d69e2e",
  DIP_VISIT: "#d69e2e",
  DIP_SANCTIONS: "#dd6b20",
  ECON_TRADE: "#38a169",
  ECON_INVEST: "#38a169",
  POL_DOMESTIC: "#805ad5",
  POL_TONGDU: "#e53e3e",
  INFO_WARFARE: "#d69e2e",
  LEGAL_GREY: "#dd6b20",
  HUMANITARIAN: "#3182ce",
};

export default function TopicPill({ topic }) {
  const color = TOPIC_COLORS[topic] || "#718096";

  return (
    <span
      style={{
        border: `1px solid ${color}66`,
        color: color,
        padding: "2px 8px",
        borderRadius: "3px",
        fontSize: "11px",
        fontFamily: "'JetBrains Mono', 'Courier New', monospace",
        textTransform: "uppercase",
        letterSpacing: "0.5px",
      }}
    >
      {topic?.replace(/_/g, "-")}
    </span>
  );
}