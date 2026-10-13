import { useState, useEffect, useMemo } from "react";
import ArticleCard from "./ArticleCard";
import SourceBadge, { PUBLICATION_NAMES } from "./SourceBadge";
import SentimentBadge from "./SentimentBadge";
import { groupSignals } from "../signalGroups";

const TOGGLE = {
  padding: 0, background: "transparent", border: "none", cursor: "pointer",
  display: "flex", alignItems: "baseline", flexWrap: "wrap", gap: "4px 10px", textAlign: "left",
  fontFamily: "var(--font-mono)", fontSize: "8.5px", letterSpacing: "0.08em",
  color: "var(--muted)", textTransform: "uppercase",
};

// The rest of a topic's signals, folded under its lead card: which outlets
// carried it at a glance (alignment-coloured, one badge per publication),
// the headlines on demand.
function MoreReports({ items }) {
  const [open, setOpen] = useState(false);
  if (!items.length) return null;
  const outlets = [];
  const seen = new Set();
  for (const a of items) {
    const name = PUBLICATION_NAMES[a.source_name] || a.source_name;
    if (!seen.has(name)) { seen.add(name); outlets.push(a); }
  }
  return (
    <div style={{ padding: "8px 0 4px 15px" }}>
      <button onClick={() => setOpen(!open)} aria-expanded={open} style={TOGGLE}>
        <span>{open ? "▾" : "▸"} {items.length} more {items.length === 1 ? "report" : "reports"}</span>
        {/* pointer-events off: SourceBadge's own default cursor would make
            half of the toggle look unclickable */}
        <span style={{ display: "contents", pointerEvents: "none" }}>
          {outlets.map((a) => <SourceBadge key={a.source_name} sourceName={a.source_name} bias={a.bias} />)}
        </span>
      </button>
      {open && items.map((a) => (
        <div key={a.id} style={{ padding: "7px 0", borderTop: "1px solid var(--soft)", marginTop: "6px" }}>
          <div style={{ display: "flex", gap: "10px", alignItems: "baseline", flexWrap: "wrap" }}>
            <SourceBadge sourceName={a.source_name} bias={a.bias} place={a.source_place} full />
            <span style={{ fontFamily: "var(--font-mono)", fontSize: "9px", letterSpacing: "0.08em", color: "var(--faint)" }}>
              {a.published_at?.slice(0, 10)}
            </span>
            {a.sentiment && <SentimentBadge sentiment={a.sentiment} score={a.sentiment_score} />}
          </div>
          <a href={a.url} target="_blank" rel="noopener noreferrer"
             style={{ display: "block", fontFamily: "var(--font-body)", fontSize: "13px", lineHeight: 1.45,
                      color: "var(--body)", textDecoration: "none", marginTop: "3px" }}>
            {a.title_en_override || a.title_en || a.title_original}
          </a>
        </div>
      ))}
    </div>
  );
}

// "Top of the Brief" — the active escalation signals, one numbered item per
// topic like a briefing document's lead items (grouping rule in
// signalGroups.js). The lead is a full ArticleCard (admin controls intact);
// the topic's other reports fold under it. The big --dot numeral carries the
// hierarchy instead of the old inverted colour plate.
export default function FlashTraffic({ escalations: initialEscalations, onTopicClick, onEntityClick, onApprove }) {
  const [escalations, setEscalations] = useState(initialEscalations || []);

  useEffect(() => {
    setEscalations(initialEscalations || []);
  }, [initialEscalations]);

  // Turning the lead's flag off promotes the topic's next report.
  const handleSignalOff = (articleId) => {
    setEscalations((prev) => prev.filter((e) => e.id !== articleId));
  };

  const groups = useMemo(() => groupSignals(escalations), [escalations]);

  if (groups.length === 0) return null;

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
          {groups.length} ACTIVE {groups.length === 1 ? "SIGNAL" : "SIGNALS"}
        </span>
      </div>

      {groups.map((g, i) => (
        <div key={g.topic} style={{
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
              key={g.lead.id}
              article={g.lead}
              onTopicClick={onTopicClick}
              onEntityClick={onEntityClick}
              onSignalOff={handleSignalOff}
              onApprove={onApprove}
            />
            <MoreReports items={g.more} />
          </div>
        </div>
      ))}
    </div>
  );
}
