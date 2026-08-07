import React, { useEffect, useState } from "react";
import { fetchAltModelAnalyses } from "../api";
import SentimentBadge from "./SentimentBadge";
import TopicPill from "./TopicPill";
import { modelLabel, ARM_LABELS, isRetiredModel } from "../altModels";

// Alt-model comparison strip (admin only — parent gates on !READ_ONLY).
// Shows how Chinese LLMs classified the same article next to the production
// Gemini analysis. Refusals render as findings, not failures. Renders
// nothing when the article hasn't been swept (most articles).

const ARM_STYLE = {
  neutral:    { label: ARM_LABELS.neutral, colour: "#6b7280" },
  originator: { label: ARM_LABELS.originator, colour: "#dc2626" },
  control:    { label: ARM_LABELS.control, colour: "#2563eb" },
};

function ArmChip({ arm }) {
  const s = ARM_STYLE[arm] || ARM_STYLE.neutral;
  return (
    <span style={{
      fontSize: "9px", fontFamily: "var(--font-mono)", textTransform: "uppercase",
      letterSpacing: "1px", color: s.colour, border: `1px solid ${s.colour}`,
      borderRadius: "3px", padding: "1px 6px",
    }}>
      {s.label}
    </span>
  );
}

function AltRow({ row }) {
  const label = modelLabel(row.model);
  return (
    <div style={{
      padding: "10px 12px", marginBottom: "8px",
      background: "var(--bg-inset, rgba(0,0,0,0.04))", borderRadius: "4px",
      border: "1px solid var(--border-subtle, rgba(0,0,0,0.08))",
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap", marginBottom: "6px" }}>
        <span style={{ fontSize: "11px", fontFamily: "var(--font-mono)", fontWeight: 600 }}>
          {label}
        </span>
        <ArmChip arm={row.arm} />
        {row.provider_used && (
          <span style={{ fontSize: "9px", color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
            via {row.provider_used}
          </span>
        )}
      </div>

      {row.outcome === "ok" && (
        <>
          <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap", marginBottom: "6px" }}>
            <TopicPill topic={row.topic_primary} />
            <SentimentBadge sentiment={row.sentiment} score={row.sentiment_score} />
            {row.urgency && (
              <span style={{ fontSize: "9px", fontFamily: "var(--font-mono)", textTransform: "uppercase", color: "var(--text-muted)" }}>
                {row.urgency}
              </span>
            )}
          </div>
          {row.summary_en && (
            <div style={{ fontSize: "12px", color: "var(--text-secondary)", lineHeight: 1.5 }}>
              {row.summary_en}
            </div>
          )}
          {row.sentiment_reasoning && (
            <div style={{ fontSize: "11px", fontStyle: "italic", color: "var(--text-muted)", marginTop: "4px" }}>
              {row.sentiment_reasoning}
            </div>
          )}
        </>
      )}

      {row.outcome === "refused" && (
        <div style={{
          border: "1px solid #dc2626", borderRadius: "4px", padding: "8px 10px",
          background: "rgba(220,38,38,0.06)",
        }}>
          <span style={{
            fontSize: "10px", fontFamily: "var(--font-mono)", fontWeight: 700,
            color: "#dc2626", textTransform: "uppercase", letterSpacing: "1px",
          }}>
            {row.finish_reason === "content_filter" ? "Filtered by provider" : "Refused"}
          </span>
          {row.refusal_text && (
            <div style={{ fontSize: "12px", color: "var(--text-secondary)", marginTop: "6px", whiteSpace: "pre-wrap" }}>
              {row.refusal_text}
            </div>
          )}
        </div>
      )}

      {(row.outcome === "parse_error" || row.outcome === "api_error") && (
        <span style={{ fontSize: "10px", fontFamily: "var(--font-mono)", color: "var(--text-muted)" }}>
          {row.outcome === "parse_error" ? "unparseable output" : "API error"}
          {row.error_text ? ` — ${row.error_text.slice(0, 120)}` : ""}
        </span>
      )}
    </div>
  );
}

export default function AltModelPanel({ article }) {
  const [rows, setRows] = useState(null);

  useEffect(() => {
    let alive = true;
    fetchAltModelAnalyses(article.id)
      .then((data) => { if (alive) setRows((data?.rows || []).filter((r) => !isRetiredModel(r.model))); })
      .catch(() => { if (alive) setRows([]); });
    return () => { alive = false; };
  }, [article.id]);

  if (!rows || rows.length === 0) return null;

  return (
    <div style={{ marginTop: "20px" }}>
      <h4 style={{
        fontSize: "11px", fontFamily: "var(--font-mono)", color: "var(--text-muted)",
        textTransform: "uppercase", letterSpacing: "1.5px", marginBottom: "12px",
      }}>
        Alternate Model Comparison
      </h4>

      {/* Production baseline from the article itself */}
      <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap", marginBottom: "10px" }}>
        <span style={{ fontSize: "11px", fontFamily: "var(--font-mono)", fontWeight: 600 }}>
          Production (Gemini)
        </span>
        <TopicPill topic={article.topic_primary} />
        <SentimentBadge sentiment={article.sentiment} score={article.sentiment_score} />
      </div>

      {rows.map((r) => <AltRow key={r.id} row={r} />)}

      <div style={{ fontSize: "9px", color: "var(--text-muted)", fontStyle: "italic" }}>
        Same production prompt; decoding config approximated (Gemini runs JSON mode +
        thinking). A model can also answer but sanitise — divergence, not refusal
        rate, is the censorship metric.
      </div>
    </div>
  );
}
