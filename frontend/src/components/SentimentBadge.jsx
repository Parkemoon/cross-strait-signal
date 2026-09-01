// Framing-sentiment badge — System B colours (how the other side is framed):
// hostile = purple, cooperative = amber, neutral/mixed = grey. Tokens live in
// index.css; never reuse red/green here (those mean political alignment).
const SENTIMENT_STYLES = {
  hostile:     { color: "var(--hostile)", label: "Hostile" },
  cooperative: { color: "var(--coop)", label: "Cooperative" },
  neutral:     { color: "var(--neut)", label: "Neutral" },
  mixed:       { color: "var(--neut)", label: "Mixed" },
};

export default function SentimentBadge({ sentiment, score }) {
  const style = SENTIMENT_STYLES[sentiment] || SENTIMENT_STYLES.neutral;

  return (
    <span
      style={{
        color: style.color,
        fontSize: "10px",
        fontWeight: 600,
        letterSpacing: "0.08em",
        textTransform: "uppercase",
        fontFamily: "var(--font-mono)",
      }}
    >
      ◆ {score > 0 ? "+" : ""}{score?.toFixed(1)} {style.label}
    </span>
  );
}
