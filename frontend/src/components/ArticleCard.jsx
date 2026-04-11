import { useState } from "react";
import SourceBadge from "./SourceBadge";
import TopicPill from "./TopicPill";
import SentimentBadge from "./SentimentBadge";
import { createNote, hideArticle, toggleSignal, approveArticle, updateArticleTranslation, updateEntityName } from "../api";
import { fetchArticleCluster } from "../api";
import { READ_ONLY } from "../readOnly";

const SENTIMENT_OPTIONS = ["hostile", "cooperative", "neutral", "mixed"];
const TOPIC_OPTIONS = [
  "MIL_EXERCISE", "MIL_MOVEMENT", "MIL_HARDWARE", "MIL_POLICY",
  "DIP_STATEMENT", "DIP_VISIT", "DIP_SANCTIONS", "PARTY_VISIT", "ARMS_SALES",
  "ECON_TRADE", "ECON_INVEST", "ENERGY",
  "POL_DOMESTIC_TW", "POL_DOMESTIC_PRC", "POL_TONGDU",
  "US_PRC", "US_TAIWAN", "HK_MAC",
  "INFO_WARFARE", "CYBER", "LEGAL_GREY",
  "CULTURE", "SPORT", "TRANSPORT", "INT_ORG", "HUMANITARIAN",
];

// Inline field editor — pencil icon that expands to textarea + save/cancel
function FieldEditor({ label, value, onSave }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value || "");
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    if (!draft.trim()) return;
    setSaving(true);
    await onSave(draft.trim());
    setSaving(false);
    setEditing(false);
  };

  if (editing) {
    return (
      <span style={{ display: "block" }}>
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          rows={3}
          style={{
            width: "100%",
            padding: "6px 8px",
            background: "var(--bg-primary)",
            color: "var(--text-primary)",
            border: "1px solid #f59e0b",
            borderRadius: "3px",
            fontSize: "inherit",
            fontFamily: "inherit",
            lineHeight: "inherit",
            resize: "vertical",
            boxSizing: "border-box",
          }}
          autoFocus
        />
        <span style={{ display: "flex", gap: "6px", marginTop: "4px" }}>
          <button
            onClick={handleSave}
            disabled={saving}
            style={{
              padding: "3px 10px",
              background: "#f59e0b",
              color: "#fff",
              border: "none",
              borderRadius: "3px",
              fontSize: "11px",
              fontFamily: "var(--font-mono)",
              cursor: "pointer",
            }}
          >
            {saving ? "…" : "Save"}
          </button>
          <button
            onClick={() => { setDraft(value || ""); setEditing(false); }}
            style={{
              padding: "3px 10px",
              background: "transparent",
              color: "var(--text-muted)",
              border: "1px solid var(--border-color)",
              borderRadius: "3px",
              fontSize: "11px",
              fontFamily: "var(--font-mono)",
              cursor: "pointer",
            }}
          >
            Cancel
          </button>
        </span>
      </span>
    );
  }

  return (
    <span
      style={{ display: "inline", cursor: "default" }}
      title={label}
    >
      {value}
      {!READ_ONLY && value && (
        <button
          onClick={(e) => { e.stopPropagation(); setDraft(value); setEditing(true); }}
          title={`Edit ${label}`}
          style={{
            background: "none",
            border: "none",
            cursor: "pointer",
            color: "var(--text-muted)",
            fontSize: "11px",
            padding: "0 4px",
            lineHeight: 1,
            verticalAlign: "middle",
            opacity: 0.6,
          }}
        >
          ✎
        </button>
      )}
    </span>
  );
}

// Inline editor for a single entity's English name
function EntityTag({ articleId, entity, onEntityClick }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(entity.entity_name_en || entity.entity_name);
  const [displayName, setDisplayName] = useState(entity.entity_name_en || entity.entity_name);
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    const trimmed = draft.trim();
    if (!trimmed || trimmed === displayName) { setEditing(false); return; }
    setSaving(true);
    await updateEntityName(articleId, entity.id, trimmed);
    setDisplayName(trimmed);
    setSaving(false);
    setEditing(false);
  };

  if (editing) {
    return (
      <span style={{ display: "inline-flex", alignItems: "center", gap: "4px", background: "var(--tag-bg)", padding: "3px 8px", borderRadius: "2px" }}>
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") handleSave(); if (e.key === "Escape") { setDraft(displayName); setEditing(false); } }}
          style={{
            width: "140px", padding: "1px 4px", fontSize: "12px",
            fontFamily: "var(--font-body)", background: "var(--bg-primary)",
            color: "var(--text-primary)", border: "1px solid #f59e0b",
            borderRadius: "2px", outline: "none",
          }}
          autoFocus
        />
        <button
          onClick={handleSave}
          disabled={saving}
          style={{ background: "#f59e0b", color: "#fff", border: "none", borderRadius: "2px", padding: "1px 6px", fontSize: "11px", cursor: "pointer" }}
        >
          {saving ? "…" : "✓"}
        </button>
        <button
          onClick={() => { setDraft(displayName); setEditing(false); }}
          style={{ background: "transparent", color: "var(--text-muted)", border: "1px solid var(--border-color)", borderRadius: "2px", padding: "1px 6px", fontSize: "11px", cursor: "pointer" }}
        >
          ✕
        </button>
      </span>
    );
  }

  return (
    <span
      style={{
        display: "inline-flex", alignItems: "center", gap: "2px",
        background: "var(--tag-bg)", color: "var(--tag-text)",
        padding: "3px 10px", borderRadius: "2px", fontSize: "12px",
        fontFamily: "var(--font-body)",
      }}
    >
      <span
        onClick={onEntityClick ? (evt) => { evt.stopPropagation(); onEntityClick(displayName); } : undefined}
        style={{ cursor: onEntityClick ? "pointer" : "default" }}
      >
        {displayName}
      </span>
      <span style={{ opacity: 0.5, marginLeft: "2px" }}>{entity.entity_type}</span>
      {!READ_ONLY && (
        <button
          onClick={(e) => { e.stopPropagation(); setEditing(true); }}
          title="Correct entity name"
          style={{
            background: "none", border: "none", cursor: "pointer",
            color: "var(--text-muted)", fontSize: "11px", padding: "0 2px",
            lineHeight: 1, opacity: 0.6,
          }}
        >
          ✎
        </button>
      )}
    </span>
  );
}

export default function ArticleCard({ article, onTopicClick, onEntityClick, onSignalOff, onApprove }) {
  const [expanded, setExpanded] = useState(false);
  const [noteText, setNoteText] = useState("");
  const [sentimentOverride, setSentimentOverride] = useState("");
  const [topicOverride, setTopicOverride] = useState("");
  const [noteSaved, setNoteSaved] = useState(false);
  const [clusterArticles, setClusterArticles] = useState(null);
  const [clusterLoading, setClusterLoading] = useState(false);
  const [hidden, setHidden] = useState(false);
  const [isSignal, setIsSignal] = useState(article.is_escalation_signal === 1);
  const [scoreOverride, setScoreOverride] = useState("");
  const [approved, setApproved] = useState(!!article.analyst_approved);
  const [titleOverride, setTitleOverride] = useState(article.title_en_override || null);
  const [summaryOverride, setSummaryOverride] = useState(article.summary_en_override || null);
  const [quoteOverride, setQuoteOverride] = useState(article.key_quote_override || null);

  const handleSaveNote = async () => {
    if (!noteText.trim() && !sentimentOverride && !topicOverride) return;
    await createNote({
      article_id: article.id,
      note_text: noteText,
      sentiment_override: sentimentOverride || null,
      topic_override: topicOverride || null,
      score_override: scoreOverride !== "" ? parseFloat(scoreOverride) : null,
    });
    setNoteSaved(true);
    setTimeout(() => setNoteSaved(false), 2000);
  };

  const handleExpand = async () => {
  const newExpanded = !expanded;
  setExpanded(newExpanded);
  if (newExpanded && article.cluster_size > 1 && clusterArticles === null) {
    setClusterLoading(true);
    const data = await fetchArticleCluster(article.id);
    setClusterArticles(data.cluster || []);
    setClusterLoading(false);
  }
};

  const handleHide = async (e) => {
    e.stopPropagation();
    await hideArticle(article.id);
    setHidden(true);
  };

  const handleApprove = async (e) => {
    e.stopPropagation();
    await approveArticle(article.id);
    setApproved(true);
    if (onApprove) onApprove();
  };

  const handleSaveTranslation = async (field, value) => {
    await updateArticleTranslation(article.id, { [field]: value });
    if (field === "title_en_override") setTitleOverride(value);
    if (field === "summary_en_override") setSummaryOverride(value);
    if (field === "key_quote_override") setQuoteOverride(value);
  };

  const handleToggleSignal = async (e) => {
    e.stopPropagation();
    const result = await toggleSignal(article.id);
    setIsSignal(result.is_escalation_signal === 1);
    if (result.is_escalation_signal === 0 && onSignalOff) {
      onSignalOff(article.id);
    }
  };

  const selectStyle = {
    padding: "6px 8px",
    background: "var(--bg-card)",
    color: "var(--text-primary)",
    border: "1px solid var(--border-color)",
    borderRadius: "3px",
    fontSize: "12px",
    fontFamily: "var(--font-mono)",
    cursor: "pointer",
  };

  const labelStyle = {
    fontSize: "10px",
    fontFamily: "var(--font-mono)",
    color: "var(--text-muted)",
    textTransform: "uppercase",
    letterSpacing: "1px",
    display: "block",
    marginBottom: "4px",
  };

  const displayTitle = titleOverride || article.title_en || article.title_original;
  const displaySummary = summaryOverride || article.summary_en;
  const displayQuote = quoteOverride || article.key_quote_en || article.key_quote;
  const isPending = !READ_ONLY && !approved;

  if (hidden) return null;

  return (
    <article
      style={{
        borderBottom: "1px solid var(--border-color)",
        borderLeft: isPending ? "3px solid #f59e0b" : "none",
        padding: "18px 0",
        paddingLeft: isPending ? "14px" : "0",
        cursor: "pointer",
      }}
      onClick={handleExpand}
    >
      {/* Pending approval banner */}
      {isPending && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginBottom: "10px",
          }}
          onClick={(e) => e.stopPropagation()}
        >
          <span
            style={{
              fontSize: "10px",
              fontFamily: "var(--font-mono)",
              color: "#f59e0b",
              textTransform: "uppercase",
              letterSpacing: "1.5px",
              fontWeight: 600,
            }}
          >
            ⚠ Pending Approval
          </span>
          <div style={{ display: "flex", gap: "6px" }}>
            <button
              onClick={handleApprove}
              style={{
                padding: "3px 10px",
                background: "#16a34a",
                color: "#fff",
                border: "none",
                borderRadius: "3px",
                fontSize: "11px",
                fontFamily: "var(--font-mono)",
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              ✓ Approve
            </button>
            <button
              onClick={handleHide}
              style={{
                padding: "3px 10px",
                background: "transparent",
                color: "var(--text-muted)",
                border: "1px solid var(--border-color)",
                borderRadius: "3px",
                fontSize: "11px",
                fontFamily: "var(--font-mono)",
                cursor: "pointer",
              }}
            >
              ✕ Dismiss
            </button>
          </div>
        </div>
      )}
      {/* Metadata row */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "10px",
          marginBottom: "8px",
          flexWrap: "wrap",
        }}
      >
        <SourceBadge
          sourceName={article.source_name}
          bias={article.bias}
        />
        <TopicPill topic={article.topic_primary} onClick={onTopicClick} />
        <SentimentBadge
          sentiment={article.sentiment}
          score={article.sentiment_score}
        />
        <span
          style={{
            color: "var(--text-muted)",
            fontSize: "12px",
            fontFamily: "var(--font-mono)",
          }}
        >
          {article.published_at?.slice(0, 10)}
        </span>
        {article.cluster_size > 1 && (
          <span
            style={{
              background: "var(--bg-secondary)",
              color: "var(--accent-teal)",
              border: "1px solid var(--accent-teal)",
              padding: "1px 8px",
              borderRadius: "2px",
              fontSize: "10px",
              fontFamily: "var(--font-mono)",
              cursor: "pointer",
            }}
          >
            {article.cluster_size} sources
          </span>
        )}
        {isSignal && (
          <span
            style={{
              background: "var(--accent-red)",
              color: "#fff",
              padding: "1px 8px",
              borderRadius: "2px",
              fontSize: "10px",
              fontWeight: 600,
              fontFamily: "var(--font-mono)",
            }}
          >
            SIGNAL
          </span>
        )}

{/* Action buttons — admin only */}
        {!READ_ONLY && (
          <div style={{ display: "flex", gap: "6px", marginLeft: "auto" }}>
            <button
              onClick={handleToggleSignal}
              title={isSignal ? "Remove signal flag" : "Mark as escalation signal"}
              style={{
                background: isSignal ? "var(--accent-red)" : "transparent",
                border: "1px solid var(--accent-red)",
                color: isSignal ? "#fff" : "var(--accent-red)",
                borderRadius: "2px",
                padding: "1px 7px",
                fontSize: "10px",
                fontFamily: "var(--font-mono)",
                cursor: "pointer",
                lineHeight: 1.6,
              }}
            >
              {isSignal ? "✕ Signal" : "! Signal"}
            </button>
            <button
              onClick={handleHide}
              title="Hide this article"
              style={{
                background: "transparent",
                border: "1px solid var(--border-color)",
                color: "var(--text-muted)",
                borderRadius: "2px",
                padding: "1px 7px",
                fontSize: "10px",
                fontFamily: "var(--font-mono)",
                cursor: "pointer",
                lineHeight: 1.6,
              }}
            >
              {"✕"}
            </button>
          </div>
        )}

      </div>

      {/* Headline */}
      <h3
        style={{
          fontFamily: "var(--font-headline)",
          fontSize: "18px",
          fontWeight: 400,
          lineHeight: 1.4,
          marginBottom: "4px",
          color: (!READ_ONLY && titleOverride) ? "#f59e0b" : "var(--text-primary)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <FieldEditor
          label="headline"
          value={displayTitle}
          onSave={(v) => handleSaveTranslation("title_en_override", v)}
        />
      </h3>

      {/* Original language title */}
      {article.title_en && article.title_original !== article.title_en && (
        <p
          style={{
            fontSize: "14px",
            color: "var(--text-muted)",
            marginBottom: "8px",
            fontFamily: "var(--font-body)",
          }}
        >
          {article.title_original}
        </p>
      )}

      {/* Summary */}
      <p
        style={{
          fontSize: "14px",
          fontFamily: "var(--font-body)",
          color: (!READ_ONLY && summaryOverride) ? "#f59e0b" : "var(--text-secondary)",
          lineHeight: 1.65,
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <FieldEditor
          label="summary"
          value={displaySummary}
          onSave={(v) => handleSaveTranslation("summary_en_override", v)}
        />
      </p>

      {/* Expanded detail */}
      {expanded && (
        <div
          style={{
            marginTop: "18px",
            paddingTop: "18px",
            borderTop: "1px dashed var(--border-color)",
          }}
          onClick={(e) => e.stopPropagation()}
        >
          {/* Entities */}
          {article.entities && article.entities.length > 0 && (
            <div style={{ marginBottom: "16px" }}>
              <h4
                style={{
                  fontSize: "11px",
                  fontFamily: "var(--font-mono)",
                  color: "var(--text-muted)",
                  textTransform: "uppercase",
                  letterSpacing: "1.5px",
                  marginBottom: "8px",
                }}
              >
                Extracted Entities
              </h4>
              <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
                {article.entities.map((e, i) => (
                  <EntityTag
                    key={e.id ?? i}
                    articleId={article.id}
                    entity={e}
                    onEntityClick={onEntityClick}
                  />
                ))}
              </div>
            </div>
          )}

          {/* Key quote */}
          {(article.key_quote || quoteOverride) && (
            <div style={{ marginBottom: "16px" }}>
              <h4
                style={{
                  fontSize: "11px",
                  fontFamily: "var(--font-mono)",
                  color: "var(--text-muted)",
                  textTransform: "uppercase",
                  letterSpacing: "1.5px",
                  marginBottom: "8px",
                }}
              >
                Key Quote
              </h4>
              <blockquote
                style={{
                  borderLeft: "3px solid var(--accent-teal)",
                  paddingLeft: "14px",
                  fontFamily: "var(--font-body)",
                  fontSize: "14px",
                  color: "var(--text-secondary)",
                  fontStyle: "italic",
                  lineHeight: 1.6,
                }}
              >
                {article.key_quote}
                <p
                  style={{
                    color: (!READ_ONLY && quoteOverride) ? "#f59e0b" : "var(--text-muted)",
                    marginTop: "4px",
                    fontStyle: "normal",
                    fontSize: "13px",
                  }}
                >
                  {"\u2014 "}
                  <FieldEditor
                    label="key quote translation"
                    value={displayQuote}
                    onSave={(v) => handleSaveTranslation("key_quote_override", v)}
                  />
                </p>
              </blockquote>
            </div>
          )}

          {/* Source link */}
          <a href={article.url} target="_blank" rel="noopener noreferrer" style={{ fontSize: "12px", fontFamily: "var(--font-mono)", color: "var(--accent-teal)", textDecoration: "none" }}>
            {"View original source \u2192"}
          </a>

          {/* Coverage comparison */}
          {article.cluster_size > 1 && (
            <div style={{ marginTop: "20px" }}>
              <h4 style={{
                fontSize: "11px",
                fontFamily: "var(--font-mono)",
                color: "var(--text-muted)",
                textTransform: "uppercase",
                letterSpacing: "1.5px",
                marginBottom: "10px",
              }}>
                Also covered by {article.cluster_size - 1} other {article.cluster_size - 1 === 1 ? "source" : "sources"}
              </h4>
              {clusterLoading ? (
                <p style={{ fontSize: "12px", color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
                  Loading coverage...
                </p>
              ) : clusterArticles?.map((c, i) => (
                <div key={i} style={{
                  background: "var(--bg-secondary)",
                  borderRadius: "3px",
                  padding: "10px 12px",
                  marginBottom: "6px",
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "flex-start",
                  gap: "12px",
                }}>
                  <div style={{ flex: 1 }}>
                    <div style={{
                      fontSize: "10px",
                      fontFamily: "var(--font-mono)",
                      color: c.place === "PRC" ? "var(--accent-red)" : "var(--accent-blue)",
                      textTransform: "uppercase",
                      letterSpacing: "1px",
                      marginBottom: "4px",
                    }}>
                      {c.source_name}
                    </div>
                    <div style={{
                      fontSize: "13px",
                      fontFamily: "var(--font-body)",
                      color: "var(--text-secondary)",
                      lineHeight: 1.4,
                    }}>
                      {c.title_en || c.title_original}
                    </div>
                  </div>
                  <div style={{ textAlign: "right", flexShrink: 0 }}>
                    <div style={{
                      fontSize: "11px",
                      fontFamily: "var(--font-mono)",
                      color: c.sentiment_score > 0.3
                        ? "#f59e0b"
                        : c.sentiment_score < -0.3
                        ? "#7c3aed"
                        : "#6b7280",
                      fontWeight: 600,
                    }}>
                      {c.sentiment_score > 0 ? "+" : ""}{c.sentiment_score?.toFixed(2)}
                    </div>
                    <a href={c.url} target="_blank" rel="noopener noreferrer" style={{
                      fontSize: "10px",
                      fontFamily: "var(--font-mono)",
                      color: "var(--accent-teal)",
                      textDecoration: "none",
                    }}>
                      {"Source \u2197"}
                    </a>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Analyst commentary — admin only */}
          {!READ_ONLY && (
            <div style={{ marginTop: "20px" }}>
              <h4
                style={{
                  fontSize: "11px",
                  fontFamily: "var(--font-mono)",
                  color: "var(--text-muted)",
                  textTransform: "uppercase",
                  letterSpacing: "1.5px",
                  marginBottom: "12px",
                }}
              >
                Analyst Commentary
              </h4>

              {/* Override controls */}
              <div
                style={{
                  display: "flex",
                  gap: "16px",
                  marginBottom: "12px",
                  flexWrap: "wrap",
                }}
              >
                <div>
                  <label style={labelStyle}>Override Sentiment</label>
                  <select
                    value={sentimentOverride}
                    onChange={(e) => setSentimentOverride(e.target.value)}
                    style={selectStyle}
                  >
                    <option value="">— no override —</option>
                    {SENTIMENT_OPTIONS.map((s) => (
                      <option key={s} value={s}>{s}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label style={labelStyle}>Override Score (-1.0 to +1.0)</label>
                  <input
                    type="number"
                    min="-1"
                    max="1"
                    step="0.1"
                    value={scoreOverride}
                    onChange={(e) => setScoreOverride(e.target.value)}
                    placeholder="e.g. +0.6"
                    style={{
                      ...selectStyle,
                      width: "120px",
                    }}
                  />
                </div>
                <div>
                  <label style={labelStyle}>Override Topic</label>
                  <select
                    value={topicOverride}
                    onChange={(e) => setTopicOverride(e.target.value)}
                    style={selectStyle}
                  >
                    <option value="">— no override —</option>
                    {TOPIC_OPTIONS.map((t) => (
                      <option key={t} value={t}>{t}</option>
                    ))}
                  </select>
                </div>
              </div>

              <textarea
                value={noteText}
                onChange={(e) => setNoteText(e.target.value)}
                placeholder="Add editorial analysis or context..."
                style={{
                  width: "100%",
                  padding: "12px",
                  background: "var(--bg-secondary)",
                  color: "var(--text-primary)",
                  border: "1px solid var(--border-color)",
                  borderRadius: "3px",
                  fontSize: "14px",
                  fontFamily: "var(--font-body)",
                  minHeight: "70px",
                  resize: "vertical",
                  lineHeight: 1.5,
                  boxSizing: "border-box",
                }}
              />
              <button
                onClick={handleSaveNote}
                style={{
                  marginTop: "8px",
                  padding: "7px 20px",
                  background: noteSaved ? "var(--accent-green)" : "var(--accent-teal)",
                  color: "#fff",
                  border: "none",
                  borderRadius: "3px",
                  fontSize: "13px",
                  fontFamily: "var(--font-body)",
                  fontWeight: 600,
                  cursor: "pointer",
                  transition: "background 0.2s",
                }}
              >
                {noteSaved ? "✓ Saved" : "Save Note"}
              </button>
            </div>
          )}
        </div>
      )}
    </article>
  );
}