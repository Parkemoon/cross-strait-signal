const SENTIMENT_STYLES = {
  escalatory: { color: "#e53e3e", label: "ESCALATORY" },
  conciliatory: { color: "#38a169", label: "CONCILIATORY" },
  neutral: { color: "#718096", label: "NEUTRAL" },
  ambiguous: { color: "#d69e2e", label: "AMBIGUOUS" },
};

export default function SentimentBadge({ sentiment, score }) {
  const style = SENTIMENT_STYLES[sentiment] || SENTIMENT_STYLES.neutral;

  return (
    <span
      style={{
        color: style.color,
        fontSize: "11px",
        fontWeight: 600,
        fontFamily: "'JetBrains Mono', 'Courier New', monospace",
      }}
    >
      {style.label} ({score > 0 ? "+" : ""}{score?.toFixed(1)})
    </span>
  );
}