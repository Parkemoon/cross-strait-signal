import { useState, useEffect } from "react";
import ArticleCard from "./ArticleCard";

// "Top of the Brief" — the active escalation signals, numbered like a
// briefing document's lead items. Full ArticleCards inside (admin controls
// intact); the big --dot numeral carries the hierarchy instead of the old
// inverted colour plate.
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
    <div style={{ marginBottom: "28px" }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: "10px", marginBottom: "12px" }}>
        <span style={{
          fontFamily: "var(--font-mono)",
          fontSize: "9.5px",
          fontWeight: 600,
          letterSpacing: "0.24em",
          textTransform: "uppercase",
          color: "var(--hostile)",
        }}>
          Top of the Brief
        </span>
        <span style={{ flex: 1, borderBottom: "1px solid var(--hair)" }} />
        <span style={{
          fontFamily: "var(--font-mono)",
          fontSize: "9px",
          color: "var(--pale)",
          letterSpacing: "0.08em",
        }}>
          {escalations.length} ACTIVE {escalations.length === 1 ? "SIGNAL" : "SIGNALS"}
        </span>
      </div>

      {escalations.map((item, i) => (
        <div key={item.id} style={{
          display: "flex",
          gap: "16px",
          paddingTop: i > 0 ? "6px" : 0,
          borderTop: i > 0 ? "1px solid var(--soft)" : "none",
          marginTop: i > 0 ? "6px" : 0,
        }}>
          <span style={{
            fontFamily: "var(--font-headline)",
            fontSize: "30px",
            color: "var(--dot)",
            lineHeight: 1,
            flexShrink: 0,
            paddingTop: "16px",
          }}>
            {i + 1}
          </span>
          <div style={{ flex: 1, minWidth: 0 }}>
            <ArticleCard
              article={item}
              onTopicClick={onTopicClick}
              onEntityClick={onEntityClick}
              onSignalOff={handleSignalOff}
              onApprove={onApprove}
            />
          </div>
        </div>
      ))}
    </div>
  );
}
