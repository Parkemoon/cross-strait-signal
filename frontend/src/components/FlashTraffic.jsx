import { useState, useEffect } from "react";
import ArticleCard from "./ArticleCard";

export default function FlashTraffic({ escalations: initialEscalations, onTopicClick, onEntityClick, onApprove }) {
  const [escalations, setEscalations] = useState(initialEscalations || []);

  useEffect(() => {
    setEscalations(initialEscalations || []);
  }, [initialEscalations]);

  const handleSignalOff = (articleId) => {
    setEscalations((prev) => prev.filter((e) => e.id !== articleId));
  };

  if (!escalations || escalations.length === 0) return null;

  return (
    <div style={{ marginBottom: "32px" }}>
      <div style={{ marginBottom: "14px" }}>
        <div style={{ height: "3px", background: "var(--accent-red)", marginBottom: "8px" }} />
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
          <span style={{
            fontFamily: "var(--font-mono)",
            fontSize: "11px",
            fontWeight: 600,
            letterSpacing: "0.14em",
            textTransform: "uppercase",
            color: "var(--accent-red)",
          }}>
            Priority Signals
          </span>
          <span style={{
            fontFamily: "var(--font-mono)",
            fontSize: "10px",
            color: "var(--text-muted)",
          }}>
            {escalations.length} active
          </span>
        </div>
      </div>

      <div
        className="signal-inverted"
        style={{
          background: "var(--bg-primary)",
          borderLeft: "3px solid var(--accent-red)",
          padding: "4px 20px 4px 20px",
          marginBottom: "24px",
        }}
      >
        {escalations.map((item) => (
          <ArticleCard
            key={item.id}
            article={item}
            onTopicClick={onTopicClick}
            onEntityClick={onEntityClick}
            onSignalOff={handleSignalOff}
            onApprove={onApprove}
          />
        ))}
      </div>
    </div>
  );
}
