import { useState, useEffect } from "react";
import ArticleCard from "./ArticleCard";

export default function FlashTraffic({ escalations: initialEscalations, onTopicClick, onEntityClick }) {
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
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          gap: "10px",
          marginBottom: "14px",
        }}
      >
        <h2
          style={{
            fontFamily: "var(--font-headline)",
            fontSize: "20px",
            fontWeight: 400,
            color: "var(--accent-red)",
          }}
        >
          Priority Signals
        </h2>
        <span
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "11px",
            color: "var(--text-muted)",
          }}
        >
          {escalations.length} active
        </span>
      </div>

      <div
        style={{
          borderLeft: "3px solid var(--accent-red)",
          paddingLeft: "16px",
        }}
      >
        {escalations.map((item) => (
          <ArticleCard
            key={item.id}
            article={item}
            onTopicClick={onTopicClick}
            onEntityClick={onEntityClick}
            onSignalOff={handleSignalOff}
          />
        ))}
      </div>

      <div
        style={{
          height: "1px",
          background: "var(--border-color)",
          marginTop: "8px",
          marginBottom: "8px",
        }}
      />
    </div>
  );
}
