import { useState } from "react";
import SourceBadge from "./SourceBadge";
import TopicPill from "./TopicPill";
import SentimentBadge from "./SentimentBadge";
import { createNote } from "../api";

export default function ArticleCard({ article }) {
  const [expanded, setExpanded] = useState(false);
  const [noteText, setNoteText] = useState("");
  const [noteSaved, setNoteSaved] = useState(false);

  const handleSaveNote = async () => {
    if (!noteText.trim()) return;
    await createNote({ article_id: article.id, note_text: noteText });
    setNoteSaved(true);
    setTimeout(() => setNoteSaved(false), 2000);
  };

  return (
    <div
      style={{
        background: "var(--bg-card)",
        borderLeft: article.is_escalation_signal
          ? "3px solid var(--accent-red)"
          : "3px solid transparent",
        padding: "16px 20px",
        marginBottom: "10px",
        borderRadius: "4px",
        cursor: "pointer",
        transition: "border-color 0.2s",
      }}
      onClick={() => setExpanded(!expanded)}
    >
      {/* Header row */}
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
          country={article.source_country}
        />
        <SentimentBadge
          sentiment={article.sentiment}
          score={article.sentiment_score}
        />
        <span
          style={{
            color: "var(--text-muted)",
            fontSize: "12px",
            fontFamily: "'JetBrains Mono', 'Courier New', monospace",
          }}
        >
          {article.published_at?.slice(0, 10)}
        </span>
        {article.is_escalation_signal === 1 && (
          <span
            style={{
              background: "var(--accent-red)",
              color: "#fff",
              padding: "1px 6px",
              borderRadius: "3px",
              fontSize: "10px",
              fontWeight: 700,
            }}
          >
            ⚠ SIGNAL
          </span>
        )}
      </div>

      {/* Title */}
      <h3
        style={{
          fontSize: "15px",
          fontWeight: 600,
          marginBottom: "4px",
          color: "var(--text-primary)",
        }}
      >
        {article.title_en || article.title_original}
      </h3>

      {/* Original title if different */}
      {article.title_en && article.title_original !== article.title_en && (
        <p
          style={{
            fontSize: "13px",
            color: "var(--text-muted)",
            marginBottom: "8px",
          }}
        >
          {article.title_original}
        </p>
      )}

      {/* Summary */}
      <p
        style={{
          fontSize: "13px",
          color: "var(--text-secondary)",
          lineHeight: 1.6,
          marginBottom: "10px",
        }}
      >
        {article.summary_en}
      </p>

      {/* Topic pills */}
      <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
        <TopicPill topic={article.topic_primary} />
        {article.topic_secondary && (
          <TopicPill topic={article.topic_secondary} />
        )}
      </div>

      {/* Expanded section */}
      {expanded && (
        <div
          style={{
            marginTop: "16px",
            paddingTop: "16px",
            borderTop: "1px solid var(--border-color)",
          }}
          onClick={(e) => e.stopPropagation()}
        >
          {/* Entities */}
          {article.entities && article.entities.length > 0 && (
            <div style={{ marginBottom: "12px" }}>
              <span
                style={{
                  fontSize: "11px",
                  color: "var(--text-muted)",
                  textTransform: "uppercase",
                  letterSpacing: "1px",
                }}
              >
                Entities:
              </span>
              <div
                style={{
                  display: "flex",
                  gap: "6px",
                  flexWrap: "wrap",
                  marginTop: "4px",
                }}
              >
                {article.entities.map((e, i) => (
                  <span
                    key={i}
                    style={{
                      background: "var(--tag-bg)",
                      color: "var(--tag-text)",
                      padding: "2px 8px",
                      borderRadius: "3px",
                      fontSize: "12px",
                    }}
                  >
                    {e.entity_name_en || e.entity_name} ({e.entity_type})
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Key quote */}
          {article.key_quote && (
            <div style={{ marginBottom: "12px" }}>
              <span
                style={{
                  fontSize: "11px",
                  color: "var(--text-muted)",
                  textTransform: "uppercase",
                  letterSpacing: "1px",
                }}
              >
                Key Quote:
              </span>
              <p
                style={{
                  fontSize: "13px",
                  color: "var(--text-secondary)",
                  fontStyle: "italic",
                  marginTop: "4px",
                  lineHeight: 1.5,
                }}
              >
                "{article.key_quote}"
                {article.key_quote_en && (
                  <span style={{ color: "var(--text-muted)" }}>
                    {" "}
                    — "{article.key_quote_en}"
                  </span>
                )}
              </p>
            </div>
          )}

          {/* Source link */}
          <a
            href={article.url}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              fontSize: "12px",
              color: "var(--accent-blue)",
              textDecoration: "none",
            }}
          >
            View original →
          </a>

          {/* Analyst note */}
          <div style={{ marginTop: "16px" }}>
            <span
              style={{
                fontSize: "11px",
                color: "var(--text-muted)",
                textTransform: "uppercase",
                letterSpacing: "1px",
              }}
            >
              Analyst Commentary:
            </span>
            <textarea
              value={noteText}
              onChange={(e) => setNoteText(e.target.value)}
              placeholder="Add your analysis..."
              style={{
                width: "100%",
                marginTop: "6px",
                padding: "10px",
                background: "var(--bg-secondary)",
                color: "var(--text-primary)",
                border: "1px solid var(--border-color)",
                borderRadius: "4px",
                fontSize: "13px",
                minHeight: "60px",
                resize: "vertical",
                fontFamily: "inherit",
              }}
            />
            <button
              onClick={handleSaveNote}
              style={{
                marginTop: "6px",
                padding: "6px 16px",
                background: noteSaved ? "var(--accent-green)" : "var(--accent-blue)",
                color: "#fff",
                border: "none",
                borderRadius: "4px",
                fontSize: "12px",
                cursor: "pointer",
                fontWeight: 600,
              }}
            >
              {noteSaved ? "✓ Saved" : "Save Note"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}