import { useState } from "react";
import SourceBadge from "./SourceBadge";
import TopicPill from "./TopicPill";
import SentimentBadge from "./SentimentBadge";
import { createNote, hideArticle, toggleSignal, approveArticle, updateArticleTranslation, updateEntityName } from "../api";
import { fetchArticleCluster } from "../api";
import { READ_ONLY } from "../readOnly";
import AltModelPanel from "./AltModelPanel";
import { modelLabel, modelTintRgba } from "../altModels";

const SENTIMENT_OPTIONS = ["hostile", "cooperative", "neutral", "mixed"];
const TOPIC_OPTIONS = [
  "MIL_EXERCISE", "MIL_MOVEMENT", "MIL_HARDWARE", "MIL_POLICY",
  "DIP_STATEMENT", "DIP_VISIT", "DIP_SANCTIONS", "PARTY_VISIT", "ARMS_SALES",
  "ECON_TRADE", "ECON_INVEST", "ENERGY", "SCI_TECH",
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
            border: "1px solid var(--flag)",
            borderRadius: 0,
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
              background: "var(--flag)",
              color: "#fff",
              border: "none",
              borderRadius: 0,
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
              borderRadius: 0,
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
      <span style={{ display: "inline-flex", alignItems: "center", gap: "4px", background: "var(--tag-bg)", padding: "3px 8px", borderRadius: 0 }}>
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") handleSave(); if (e.key === "Escape") { setDraft(displayName); setEditing(false); } }}
          style={{
            width: "140px", padding: "1px 4px", fontSize: "12px",
            fontFamily: "var(--font-body)", background: "var(--bg-primary)",
            color: "var(--text-primary)", border: "1px solid var(--flag)",
            borderRadius: 0, outline: "none",
          }}
          autoFocus
        />
        <button
          onClick={handleSave}
          disabled={saving}
          style={{ background: "var(--flag)", color: "#fff", border: "none", borderRadius: 0, padding: "1px 6px", fontSize: "11px", cursor: "pointer" }}
        >
          {saving ? "…" : "✓"}
        </button>
        <button
          onClick={() => { setDraft(displayName); setEditing(false); }}
          style={{ background: "transparent", color: "var(--text-muted)", border: "1px solid var(--border-color)", borderRadius: 0, padding: "1px 6px", fontSize: "11px", cursor: "pointer" }}
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
        padding: "3px 10px", borderRadius: 0, fontSize: "12px",
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

export default function ArticleCard({ article, altLens, altDual, onTopicClick, onEntityClick, onSignalOff, onApprove }) {
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
    borderRadius: 0,
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

  // Alt-model lens: when active, the server attached alt_* fields to every
  // row (INNER JOIN on the swept subset). 'ok' rows swap the analysis fields
  // for the alt model's and show production Gemini as a ghost chip; refused /
  // error rows keep production values plus a finding chip. Headline and
  // quote translations always stay production — the sweep doesn't retranslate.
  const lensActive = !READ_ONLY && altLens && article.alt_outcome != null;
  const lensOk = lensActive && article.alt_outcome === "ok";
  const topicDiverges = lensOk && article.alt_topic_primary !== article.topic_primary;
  // Dual display: production stays primary (and interactive); the alt model
  // renders alongside it instead of replacing it. Swap = the original lens.
  const dualMode = lensOk && altDual;
  const swapMode = lensOk && !altDual;

  if (hidden) return null;

  return (
    <article
      style={{
        // Under an active lens, wash the card in the model's tint (stronger
        // when the model's output has replaced production) — you should never
        // mistake a lensed feed for the production one.
        background: lensActive
          ? modelTintRgba(altLens.model, dualMode ? 0.04 : 0.05)
          : undefined,
        borderBottom: "1px solid var(--soft)",
        borderLeft: article.urgency === "flash"
          ? "3px solid var(--hostile)"
          : article.urgency === "priority"
          ? "3px solid var(--dot)"
          : isPending
          ? "3px solid var(--flag)"
          : "3px solid var(--card-rule)",  // transparent; .expandable:hover → hairline
        padding: "16px 0 16px 12px",
        cursor: "pointer",
      }}
      className="expandable"
      role="button"
      tabIndex={0}
      aria-expanded={expanded}
      onClick={handleExpand}
      onKeyDown={(e) => {
        if (e.target !== e.currentTarget) return;  // inner controls keep their own keys
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); handleExpand(); }
      }}
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
              fontSize: "9px",
              fontFamily: "var(--font-mono)",
              color: "var(--flag)",
              textTransform: "uppercase",
              letterSpacing: "0.14em",
              fontWeight: 600,
            }}
          >
            ⚑ Pending Approval
          </span>
          <div style={{ display: "flex", gap: "8px" }}>
            <button
              onClick={handleApprove}
              style={{
                padding: "4px 14px",
                background: "var(--ink)",
                color: "var(--bg)",
                border: "1px solid var(--ink)",
                fontSize: "9px",
                letterSpacing: "0.14em",
                textTransform: "uppercase",
                fontFamily: "var(--font-mono)",
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              Approve
            </button>
            <button
              onClick={handleHide}
              style={{
                padding: "4px 14px",
                background: "transparent",
                color: "var(--muted)",
                border: "1px solid var(--hair)",
                fontSize: "9px",
                letterSpacing: "0.14em",
                textTransform: "uppercase",
                fontFamily: "var(--font-mono)",
                cursor: "pointer",
              }}
            >
              Dismiss
            </button>
          </div>
        </div>
      )}
      {/* Metadata line — source · alignment · topic · date · score */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "10px",
          marginBottom: "6px",
          flexWrap: "wrap",
        }}
      >
        <SourceBadge
          sourceName={article.source_name}
          bias={article.bias}
        />
        <span
          style={{
            color: "var(--faint)",
            fontSize: "9px",
            letterSpacing: "0.08em",
            fontFamily: "var(--font-mono)",
          }}
        >
          {article.published_at?.slice(0, 10)}
        </span>
        <TopicPill
          topic={swapMode ? article.alt_topic_primary : article.topic_primary}
          // Topic filtering runs on the production classification, so an alt
          // pill click would filter by the wrong value — disable it under swap.
          // (Dual shows the production pill, so clicking stays valid.)
          onClick={swapMode ? undefined : onTopicClick}
        />
        <SentimentBadge
          sentiment={swapMode ? article.alt_sentiment : article.sentiment}
          score={swapMode ? article.alt_sentiment_score : article.sentiment_score}
        />
        {swapMode && topicDiverges && (
          // Model-only view stays clean of Gemini chrome except this one
          // signal: the production topic differed. Full comparison lives
          // in the Both view.
          <span
            title={`Production Gemini classified this ${article.topic_primary}`}
            style={{
              fontSize: "10px",
              fontFamily: "var(--font-mono)",
              padding: "1px 8px",
              borderRadius: 0,
              color: "var(--flag)",
              border: "1px solid var(--flag)",
            }}
          >
            ≠ Gemini
          </span>
        )}
        {dualMode && (
          <span
            title={`${modelLabel(altLens.model)} classification for comparison`}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "6px",
              padding: "2px 6px",
              borderRadius: 0,
              border: `1px ${topicDiverges ? "solid var(--flag)" : "dashed var(--border-color)"}`,
              background: topicDiverges ? "color-mix(in srgb, var(--flag) 5%, transparent)" : "transparent",
            }}
          >
            <span style={{
              fontSize: "9px",
              fontFamily: "var(--font-mono)",
              color: topicDiverges ? "var(--flag)" : "var(--text-muted)",
              textTransform: "uppercase",
              letterSpacing: "1px",
            }}>
              {modelLabel(altLens.model)}
            </span>
            <TopicPill topic={article.alt_topic_primary} />
            <SentimentBadge
              sentiment={article.alt_sentiment}
              score={article.alt_sentiment_score}
            />
          </span>
        )}
        {lensActive && article.alt_outcome !== "ok" && (
          <span style={{
            fontSize: "10px",
            fontFamily: "var(--font-mono)",
            fontWeight: 600,
            padding: "1px 8px",
            borderRadius: 0,
            textTransform: "uppercase",
            letterSpacing: "1px",
            color: article.alt_outcome === "refused" ? "var(--nat)" : "var(--text-muted)",
            border: `1px solid ${article.alt_outcome === "refused" ? "var(--nat)" : "var(--border-color)"}`,
            background: article.alt_outcome === "refused" ? "color-mix(in srgb, var(--nat) 6%, transparent)" : "transparent",
          }}>
            {article.alt_outcome === "refused"
              ? (article.alt_finish_reason === "content_filter" ? "Filtered by provider" : "Refused")
              : article.alt_outcome === "parse_error" ? "Unparseable output" : "API error"}
          </span>
        )}
        {!READ_ONLY && (swapMode ? article.alt_sentiment_reasoning : article.sentiment_reasoning) && (
          <span style={{ color: "var(--text-muted)", fontSize: "11px", fontStyle: "italic" }}>
            {swapMode ? article.alt_sentiment_reasoning : article.sentiment_reasoning}
          </span>
        )}
        {article.cluster_size > 1 && (
          <span
            style={{
              color: "var(--pale)",
              fontSize: "9px",
              letterSpacing: "0.08em",
              fontFamily: "var(--font-mono)",
              textTransform: "uppercase",
              cursor: "pointer",
            }}
          >
            {article.cluster_size} sources
          </span>
        )}
        {isSignal && (
          <span
            style={{
              color: "var(--hostile)",
              border: "1px solid var(--hostile)",
              padding: "0 7px",
              fontSize: "9px",
              letterSpacing: "0.12em",
              fontWeight: 600,
              fontFamily: "var(--font-mono)",
            }}
          >
            SIGNAL
          </span>
        )}
        {/* Expand affordance — sits at the right edge (admin buttons follow it) */}
        <span className="expand-cue" aria-hidden="true">
          {expanded ? "less ▴" : "detail ▾"}
        </span>

{/* Action buttons — admin only */}
        {!READ_ONLY && (
          <div style={{ display: "flex", gap: "6px", marginLeft: "8px" }}>
            <button
              onClick={handleToggleSignal}
              title={isSignal ? "Remove signal flag" : "Mark as escalation signal"}
              style={{
                background: isSignal ? "var(--hostile)" : "transparent",
                border: "1px solid var(--hostile)",
                color: isSignal ? "var(--bg)" : "var(--hostile)",
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
                borderRadius: 0,
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

      {/* Headline — Newsreader 20px */}
      <h3
        style={{
          fontFamily: "var(--font-headline)",
          fontSize: "20px",
          fontWeight: 500,
          lineHeight: 1.3,
          marginBottom: "3px",
          color: (!READ_ONLY && titleOverride) ? "var(--flag)" : "var(--ink)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <FieldEditor
          label="headline"
          value={displayTitle}
          onSave={(v) => handleSaveTranslation("title_en_override", v)}
        />
      </h3>

      {/* Original-language title — the source's own words, own line */}
      {article.title_en && article.title_original !== article.title_en && (
        <p
          style={{
            fontSize: "12.5px",
            color: "var(--pale)",
            marginBottom: "4px",
            fontFamily: "var(--font-body)",
          }}
        >
          {article.title_original}
        </p>
      )}

      {/* Summary (dek) */}
      <p
        style={{
          fontSize: "13.5px",
          fontFamily: "var(--font-body)",
          color: (!READ_ONLY && summaryOverride) ? "var(--flag)" : "var(--body)",
          lineHeight: 1.65,
          textWrap: "pretty",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {swapMode && article.alt_summary_en ? (
          // The alt model's own summary — read-only; the FieldEditor writes
          // production summary overrides and must not be fed model output.
          article.alt_summary_en
        ) : (
          <FieldEditor
            label="summary"
            value={displaySummary}
            onSave={(v) => handleSaveTranslation("summary_en_override", v)}
          />
        )}
      </p>

      {/* Dual mode: alt model's summary + reasoning below production's.
          Read-only for the same reason as swap — never feed model output
          into the production override editor. */}
      {dualMode && article.alt_summary_en && (
        <div
          style={{
            marginTop: "8px",
            padding: "8px 10px",
            borderLeft: `2px solid ${topicDiverges ? "var(--flag)" : "var(--border-color)"}`,
            background: "var(--bg-secondary)",
          }}
          onClick={(e) => e.stopPropagation()}
        >
          <span style={{
            fontSize: "9px",
            fontFamily: "var(--font-mono)",
            color: "var(--text-muted)",
            textTransform: "uppercase",
            letterSpacing: "1px",
            display: "block",
            marginBottom: "4px",
          }}>
            {modelLabel(altLens.model)} summary
          </span>
          <p style={{
            fontSize: "13px",
            fontFamily: "var(--font-body)",
            color: "var(--text-secondary)",
            lineHeight: 1.6,
            margin: 0,
          }}>
            {article.alt_summary_en}
          </p>
          {article.alt_sentiment_reasoning && (
            <p style={{
              fontSize: "11px",
              color: "var(--text-muted)",
              fontStyle: "italic",
              margin: "6px 0 0",
            }}>
              {article.alt_sentiment_reasoning}
            </p>
          )}
        </div>
      )}

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
                  borderLeft: "2px solid var(--dot)",
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
                    color: (!READ_ONLY && quoteOverride) ? "var(--flag)" : "var(--text-muted)",
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
          <a href={article.url} target="_blank" rel="noopener noreferrer" style={{ fontSize: "12px", fontFamily: "var(--font-mono)", color: "var(--muted)", textDecoration: "none", borderBottom: "1px solid var(--dot)" }}>
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
                  borderRadius: 0,
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
                      color: c.place === "PRC" ? "var(--red)" : "var(--green)",
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
                        ? "var(--coop)"
                        : c.sentiment_score < -0.3
                        ? "var(--hostile)"
                        : "var(--neut)",
                      fontWeight: 600,
                    }}>
                      {c.sentiment_score > 0 ? "+" : ""}{c.sentiment_score?.toFixed(2)}
                    </div>
                    <a href={c.url} target="_blank" rel="noopener noreferrer" style={{
                      fontSize: "10px",
                      fontFamily: "var(--font-mono)",
                      color: "var(--muted)",
                      textDecoration: "none",
                      borderBottom: "1px solid var(--dot)",
                    }}>
                      {"Source \u2197"}
                    </a>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Alt-model comparison — admin only, renders nothing unless swept */}
          {!READ_ONLY && <AltModelPanel article={article} />}

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
                  borderRadius: 0,
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
                  background: noteSaved ? "var(--gsoft)" : "var(--ink)",
                  color: "#fff",
                  border: "none",
                  borderRadius: 0,
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