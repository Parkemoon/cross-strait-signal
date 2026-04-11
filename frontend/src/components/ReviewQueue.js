import { useState, useEffect } from "react";
import { fetchReviewQueue, resolveReview, updateArticleTranslation } from "../api";

const SENTIMENT_OPTIONS = ["hostile", "cooperative", "neutral", "mixed"];
const TOPIC_OPTIONS = [
  "MIL_EXERCISE", "MIL_MOVEMENT", "MIL_HARDWARE", "MIL_POLICY",
  "DIP_STATEMENT", "DIP_VISIT", "DIP_SANCTIONS", "PARTY_VISIT",
  "ECON_TRADE", "ECON_INVEST", "ENERGY", "SCI_TECH", "POL_DOMESTIC_TW", "POL_DOMESTIC_PRC", "POL_TONGDU",
  "INFO_WARFARE", "CYBER", "LEGAL_GREY", "HUMANITARIAN", "TRANSPORT", "INT_ORG",
  "CULTURE", "SPORT", "ARMS_SALES", "US_PRC", "US_TAIWAN", "HK_MAC",
];

const SENTIMENT_COLOURS = {
  hostile: "#c0392b",
  cooperative: "#27ae60",
  neutral: "#7f8c8d",
  mixed: "#e67e22",
};

function ReviewCard({ item, onResolved }) {
  const [mode, setMode] = useState(null); // null | 'override'
  const [overrides, setOverrides] = useState({
    sentiment_override: item.sentiment,
    topic_override: item.topic_primary,
    escalation_override: item.is_escalation_signal,
    note: "",
  });
  const [translations, setTranslations] = useState({
    title_en_override: item.title_en_override || item.title_en || "",
    summary_en_override: item.summary_en_override || item.summary_en || "",
    key_quote_override: item.key_quote_override || item.key_quote_en || item.key_quote || "",
  });
  const [submitting, setSubmitting] = useState(false);

  // Save any changed translation fields, then resolve
  async function handleResolve(resolution) {
    setSubmitting(true);
    // Only send fields that differ from the AI originals
    const translationUpdates = {};
    if (translations.title_en_override !== (item.title_en || ""))
      translationUpdates.title_en_override = translations.title_en_override;
    if (translations.summary_en_override !== (item.summary_en || ""))
      translationUpdates.summary_en_override = translations.summary_en_override;
    if (translations.key_quote_override !== (item.key_quote_en || item.key_quote || ""))
      translationUpdates.key_quote_override = translations.key_quote_override;
    if (Object.keys(translationUpdates).length > 0) {
      await updateArticleTranslation(item.article_id, translationUpdates);
    }
    await resolveReview(item.analysis_id, {
      resolution,
      ...(resolution === "overridden" ? overrides : { note: overrides.note }),
    });
    onResolved(item.analysis_id);
  }

  const biasColour = {
    green: "#27ae60",
    green_leaning: "#52be80",
    blue: "#2980b9",
    blue_leaning: "#5dade2",
    state_official: "#8e44ad",
    state_nationalist: "#c0392b",
  }[item.bias] || "var(--text-muted)";

  return (
    <div
      style={{
        background: "var(--bg-card)",
        border: "1px solid var(--border-color)",
        borderLeft: "3px solid #e67e22",
        borderRadius: "6px",
        padding: "20px",
        marginBottom: "16px",
      }}
    >
      {/* Header row */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "10px" }}>
        <div style={{ flex: 1 }}>
          <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "4px" }}>
            <span
              style={{
                fontSize: "10px",
                fontFamily: "var(--font-mono)",
                color: biasColour,
                textTransform: "uppercase",
                letterSpacing: "1px",
              }}
            >
              {item.source_name}
            </span>
            <span style={{ fontSize: "10px", color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
              {item.published_at ? new Date(item.published_at).toLocaleString("en-GB", { dateStyle: "short", timeStyle: "short" }) : "—"}
            </span>
          </div>
          <h3
            style={{
              fontFamily: "var(--font-headline)",
              fontSize: "18px",
              fontWeight: 400,
              color: "var(--text-primary)",
              margin: 0,
              lineHeight: 1.3,
            }}
          >
            {item.title_en || item.title_original}
          </h3>
          {item.title_en && item.title_original !== item.title_en && (
            <p style={{ fontSize: "12px", color: "var(--text-muted)", fontFamily: "var(--font-mono)", margin: "4px 0 0" }}>
              {item.title_original}
            </p>
          )}
        </div>
        
        <a href={item.url}
          target="_blank"
          rel="noreferrer"
          style={{
            fontSize: "11px",
            fontFamily: "var(--font-mono)",
            color: "var(--accent)",
            textDecoration: "none",
            marginLeft: "16px",
            whiteSpace: "nowrap",
          }}
        >
          {"Source \u2197"}
        </a>
      </div>

      {/* Summary */}
      {item.summary_en && (
        <p style={{ fontSize: "14px", color: "var(--text-secondary)", lineHeight: 1.6, margin: "0 0 14px" }}>
          {item.summary_en}
        </p>
      )}

      {/* AI classifications */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: "10px",
          marginBottom: "14px",
        }}
      >
        {[
          { label: "Topic", value: item.topic_primary },
          {
            label: "Sentiment",
            value: item.sentiment,
            colour: SENTIMENT_COLOURS[item.sentiment],
          },
          { label: "Urgency", value: item.urgency },
          { label: "Confidence", value: item.confidence ? `${Math.round(item.confidence * 100)}%` : "—" },
        ].map(({ label, value, colour }) => (
          <div
            key={label}
            style={{
              background: "var(--bg-secondary)",
              borderRadius: "4px",
              padding: "8px 12px",
            }}
          >
            <span style={{ fontSize: "10px", fontFamily: "var(--font-mono)", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "1px", display: "block", marginBottom: "2px" }}>
              {label}
            </span>
            <span style={{ fontSize: "13px", fontFamily: "var(--font-mono)", color: colour || "var(--text-primary)", fontWeight: 600 }}>
              {value || "—"}
            </span>
          </div>
        ))}
      </div>

      {/* Flag reason */}
      <div
        style={{
          background: "var(--bg-secondary)",
          borderRadius: "4px",
          padding: "10px 12px",
          marginBottom: "14px",
          borderLeft: "2px solid #e67e22",
        }}
      >
        <span style={{ fontSize: "10px", fontFamily: "var(--font-mono)", color: "#e67e22", textTransform: "uppercase", letterSpacing: "1px", display: "block", marginBottom: "4px" }}>
          Flagged reason
        </span>
        <span style={{ fontSize: "12px", fontFamily: "var(--font-mono)", color: "var(--text-secondary)" }}>
          {item.review_reason}
        </span>
      </div>

      {/* Translation editing — always visible so you can correct before any action */}
      {(
        <div
          style={{
            background: "var(--bg-secondary)",
            borderRadius: "4px",
            padding: "14px",
            marginBottom: "14px",
            display: "grid",
            gridTemplateColumns: "1fr",
            gap: "10px",
          }}
        >
          <div>
            <label style={{ fontSize: "10px", fontFamily: "var(--font-mono)", color: "#f59e0b", textTransform: "uppercase", letterSpacing: "1px", display: "block", marginBottom: "4px" }}>
              Headline
            </label>
            <input
              type="text"
              value={translations.title_en_override}
              onChange={(e) => setTranslations({ ...translations, title_en_override: e.target.value })}
              style={{
                width: "100%",
                padding: "6px 8px",
                background: "var(--bg-card)",
                color: "var(--text-primary)",
                border: "1px solid var(--border-color)",
                borderRadius: "4px",
                fontSize: "13px",
                fontFamily: "var(--font-body)",
                boxSizing: "border-box",
              }}
            />
          </div>
          <div>
            <label style={{ fontSize: "10px", fontFamily: "var(--font-mono)", color: "#f59e0b", textTransform: "uppercase", letterSpacing: "1px", display: "block", marginBottom: "4px" }}>
              Summary
            </label>
            <textarea
              value={translations.summary_en_override}
              onChange={(e) => setTranslations({ ...translations, summary_en_override: e.target.value })}
              rows={3}
              style={{
                width: "100%",
                padding: "6px 8px",
                background: "var(--bg-card)",
                color: "var(--text-primary)",
                border: "1px solid var(--border-color)",
                borderRadius: "4px",
                fontSize: "13px",
                fontFamily: "var(--font-body)",
                resize: "vertical",
                boxSizing: "border-box",
              }}
            />
          </div>
          <div>
            <label style={{ fontSize: "10px", fontFamily: "var(--font-mono)", color: "#f59e0b", textTransform: "uppercase", letterSpacing: "1px", display: "block", marginBottom: "4px" }}>
              Key quote translation
            </label>
            <input
              type="text"
              value={translations.key_quote_override}
              onChange={(e) => setTranslations({ ...translations, key_quote_override: e.target.value })}
              style={{
                width: "100%",
                padding: "6px 8px",
                background: "var(--bg-card)",
                color: "var(--text-primary)",
                border: "1px solid var(--border-color)",
                borderRadius: "4px",
                fontSize: "13px",
                fontFamily: "var(--font-body)",
                boxSizing: "border-box",
              }}
            />
          </div>
        </div>
      )}

      {/* Classification overrides */}
      {mode === "override" && (
        <div
          style={{
            background: "var(--bg-secondary)",
            borderRadius: "4px",
            padding: "14px",
            marginBottom: "14px",
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: "10px",
          }}
        >
          <div>
            <label style={{ fontSize: "10px", fontFamily: "var(--font-mono)", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "1px", display: "block", marginBottom: "4px" }}>
              Sentiment
            </label>
            <select
              value={overrides.sentiment_override}
              onChange={(e) => setOverrides({ ...overrides, sentiment_override: e.target.value })}
              style={{
                width: "100%",
                padding: "6px 8px",
                background: "var(--bg-card)",
                color: "var(--text-primary)",
                border: "1px solid var(--border-color)",
                borderRadius: "4px",
                fontSize: "13px",
                fontFamily: "var(--font-mono)",
              }}
            >
              {SENTIMENT_OPTIONS.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>

          <div>
            <label style={{ fontSize: "10px", fontFamily: "var(--font-mono)", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "1px", display: "block", marginBottom: "4px" }}>
              Topic
            </label>
            <select
              value={overrides.topic_override}
              onChange={(e) => setOverrides({ ...overrides, topic_override: e.target.value })}
              style={{
                width: "100%",
                padding: "6px 8px",
                background: "var(--bg-card)",
                color: "var(--text-primary)",
                border: "1px solid var(--border-color)",
                borderRadius: "4px",
                fontSize: "13px",
                fontFamily: "var(--font-mono)",
              }}
            >
              {TOPIC_OPTIONS.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>

          <div>
            <label style={{ fontSize: "10px", fontFamily: "var(--font-mono)", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "1px", display: "block", marginBottom: "4px" }}>
              Escalation signal
            </label>
            <select
              value={overrides.escalation_override}
              onChange={(e) => setOverrides({ ...overrides, escalation_override: e.target.value === "true" })}
              style={{
                width: "100%",
                padding: "6px 8px",
                background: "var(--bg-card)",
                color: "var(--text-primary)",
                border: "1px solid var(--border-color)",
                borderRadius: "4px",
                fontSize: "13px",
                fontFamily: "var(--font-mono)",
              }}
            >
              <option value="false">No</option>
              <option value="true">Yes</option>
            </select>
          </div>

          <div>
            <label style={{ fontSize: "10px", fontFamily: "var(--font-mono)", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "1px", display: "block", marginBottom: "4px" }}>
              Note
            </label>
            <input
              type="text"
              value={overrides.note}
              onChange={(e) => setOverrides({ ...overrides, note: e.target.value })}
              placeholder="Optional editorial note"
              style={{
                width: "100%",
                padding: "6px 8px",
                background: "var(--bg-card)",
                color: "var(--text-primary)",
                border: "1px solid var(--border-color)",
                borderRadius: "4px",
                fontSize: "13px",
                fontFamily: "var(--font-body)",
                boxSizing: "border-box",
              }}
            />
          </div>
        </div>
      )}

      {/* Action buttons */}
      <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
        {mode !== "override" && (
          <>
            <button
              onClick={() => handleResolve("confirmed")}
              disabled={submitting}
              style={{
                padding: "7px 16px",
                background: "#27ae60",
                color: "#fff",
                border: "none",
                borderRadius: "4px",
                cursor: "pointer",
                fontSize: "12px",
                fontFamily: "var(--font-mono)",
                fontWeight: 600,
              }}
            >
              ✓ Confirm AI
            </button>
            <button
              onClick={() => setMode("override")}
              style={{
                padding: "7px 16px",
                background: "var(--bg-card)",
                color: "var(--text-primary)",
                border: "1px solid var(--border-color)",
                borderRadius: "4px",
                cursor: "pointer",
                fontSize: "12px",
                fontFamily: "var(--font-mono)",
              }}
            >
              ✎ Override
            </button>
            <button
              onClick={() => handleResolve("dismissed")}
              disabled={submitting}
              style={{
                padding: "7px 16px",
                background: "var(--bg-card)",
                color: "var(--text-muted)",
                border: "1px solid var(--border-color)",
                borderRadius: "4px",
                cursor: "pointer",
                fontSize: "12px",
                fontFamily: "var(--font-mono)",
              }}
            >
              ✕ Dismiss
            </button>
          </>
        )}
        {mode === "override" && (
          <>
            <button
              onClick={() => handleResolve("overridden")}
              disabled={submitting}
              style={{
                padding: "7px 16px",
                background: "#2980b9",
                color: "#fff",
                border: "none",
                borderRadius: "4px",
                cursor: "pointer",
                fontSize: "12px",
                fontFamily: "var(--font-mono)",
                fontWeight: 600,
              }}
            >
              ✓ Save Override
            </button>
            <button
              onClick={() => setMode(null)}
              style={{
                padding: "7px 16px",
                background: "var(--bg-card)",
                color: "var(--text-muted)",
                border: "1px solid var(--border-color)",
                borderRadius: "4px",
                cursor: "pointer",
                fontSize: "12px",
                fontFamily: "var(--font-mono)",
              }}
            >
              Cancel
            </button>
          </>
        )}
      </div>
    </div>
  );
}

export default function ReviewQueue({ onClose }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchReviewQueue().then((data) => {
      setItems(Array.isArray(data) ? data : []);
      setLoading(false);
    });
  }, []);

  function handleResolved(analysisId) {
    setItems((prev) => prev.filter((i) => i.analysis_id !== analysisId));
  }

  return (
    <div style={{ padding: "28px 32px" }}>
      {/* Section header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "6px" }}>
        <h2
          style={{
            fontFamily: "var(--font-headline)",
            fontSize: "24px",
            fontWeight: 400,
            color: "var(--text-primary)",
            margin: 0,
          }}
        >
          Review Queue
        </h2>
        <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
          <span style={{ fontSize: "11px", fontFamily: "var(--font-mono)", color: "var(--text-muted)" }}>
            {items.length} pending
          </span>
          <button
            onClick={onClose}
            style={{
              padding: "6px 14px",
              background: "var(--bg-card)",
              color: "var(--text-secondary)",
              border: "1px solid var(--border-color)",
              borderRadius: "4px",
              cursor: "pointer",
              fontSize: "12px",
              fontFamily: "var(--font-mono)",
            }}
          >
            ← Signal Feed
          </button>
        </div>
      </div>

      {/* Divider */}
      <div style={{ height: "2px", background: "var(--text-primary)", marginBottom: "20px", opacity: 0.15 }} />

      {loading ? (
        <p style={{ color: "var(--text-muted)", fontFamily: "var(--font-mono)", fontSize: "13px", padding: "40px 0" }}>
          Loading...
        </p>
      ) : items.length === 0 ? (
        <p style={{ color: "var(--text-muted)", fontFamily: "var(--font-mono)", fontSize: "13px", padding: "40px 0" }}>
          No articles pending review.
        </p>
      ) : (
        items.map((item) => (
          <ReviewCard key={item.analysis_id} item={item} onResolved={handleResolved} />
        ))
      )}
    </div>
  );
}