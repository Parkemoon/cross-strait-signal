const SENTIMENT_STYLES = {
  hostile: { color: "var(--accent-red)", label: "Hostile" },
  cooperative: { color: "var(--accent-green)", label: "Cooperative" },
  neutral: { color: "var(--text-muted)", label: "Neutral" },
  mixed: { color: "var(--accent-amber)", label: "Mixed" },
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
