// Framing-sentiment badge — System B colours (how the other side is framed):
// hostile = purple, cooperative = amber, neutral/mixed = grey. Tokens live in
// index.css; never reuse red/green here (those mean political alignment).
const SENTIMENT_STYLES = {
  hostile:     { color: "var(--hostile)", label: "Hostile" },
  cooperative: { color: "var(--coop)", label: "Cooperative" },
  neutral:     { color: "var(--neut)", label: "Neutral" },
  mixed:       { color: "var(--neut)", label: "Mixed" },
};

function fmtSigned(v, digits = 2) {
  if (v == null || Number.isNaN(v)) return "";
  return `${v > 0 ? "+" : ""}${v.toFixed(digits)}`;
}

export default function SentimentBadge({ sentiment, score, excess, baseline, rawScore }) {
  const style = SENTIMENT_STYLES[sentiment] || SENTIMENT_STYLES.neutral;
  const showExcess = excess != null && Math.abs(excess) >= 0.20;
  const excessColor =
    excess <= -0.20
      ? "var(--hostile)"
      : excess >= 0.20
      ? "var(--coop)"
      : "var(--muted)";

  const tooltipParts = [];
  if (score != null) {
    tooltipParts.push(
      rawScore != null && Math.abs(rawScore - score) >= 0.005
        ? `Calibrated ${fmtSigned(score, 2)} (raw ${fmtSigned(rawScore, 2)})`
        : `Score ${fmtSigned(score, 2)}`
    );
  }
  if (baseline != null) {
    tooltipParts.push(`Outlet x topic norm ${fmtSigned(baseline, 2)}`);
  }
  if (excess != null) {
    tooltipParts.push(`Excess tone ${fmtSigned(excess, 2)}`);
  }
  const titleText = tooltipParts.length > 0 ? tooltipParts.join(" · ") : undefined;

  return (
    <span
      title={titleText}
      style={{
        display: "inline-flex",
        alignItems: "baseline",
        gap: "6px",
        fontFamily: "var(--font-mono)",
      }}
    >
      <span
        style={{
          color: style.color,
          fontSize: "10px",
          fontWeight: 600,
          letterSpacing: "0.08em",
          textTransform: "uppercase",
        }}
      >
        ◆ {score != null ? fmtSigned(score, 2) : ""} {style.label}
      </span>
      {showExcess && (
        <span
          style={{
            color: excessColor,
            fontSize: "9px",
            fontWeight: 500,
            letterSpacing: "0.04em",
            opacity: 0.85,
          }}
        >
          ({fmtSigned(excess, 2)} vs norm)
        </span>
      )}
    </span>
  );
}
