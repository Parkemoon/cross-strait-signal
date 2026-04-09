const SENTIMENT_STYLES = {
  hostile:     { color: "#7c3aed", label: "Hostile" },
  cooperative: { color: "#f59e0b", label: "Cooperative" },
  neutral:     { color: "#6b7280", label: "Neutral" },
  mixed:       { color: "#94a3b8", label: "Mixed" },
};

export default function SentimentBadge({ sentiment, score }) {
  const style = SENTIMENT_STYLES[sentiment] || SENTIMENT_STYLES.neutral;

  return (
    <span
      style={{
        color: style.color,
        fontSize: "11px",
        fontWeight: 500,
        fontFamily: "var(--font-mono)",
      }}
    >
      {style.label}
      <span style={{ opacity: 0.6, marginLeft: "4px" }}>
        {score > 0 ? "+" : ""}
        {score?.toFixed(1)}
      </span>
    </span>
  );
}
