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
    <article
      style={{
        borderBottom: "1px solid var(--border-color)",
        padding: "18px 0",
        cursor: "pointer",
      }}
      onClick={() => setExpanded(!expanded)}
    >
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
          country={article.source_country}
        />
        <TopicPill topic={article.topic_primary} />
        <SentimentBadge
          sentiment={article.sentiment}
          score={article.sentiment_score}
        />
        <span
          style={{
            color: "var(--text-muted)",
            fontSize: "12px",
            fontFamily: "var(--font-mono)",
            marginLeft: "auto",
          }}
        >
          {article.published_at?.slice(0, 10)}
        </span>
        {article.is_escalation_signal === 1 && (
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
      </div>

      {/* Headline — serif */}
      <h3
        style={{
          fontFamily: "var(--font-headline)",
          fontSize: "18px",
          fontWeight: 400,
          lineHeight: 1.4,
          marginBottom: "4px",
          color: "var(--text-primary)",
        }}
      >
        {article.title_en || article.title_original}
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
          color: "var(--text-secondary)",
          lineHeight: 1.65,
        }}
      >
        {article.summary_en}
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
              <div
                style={{
                  display: "flex",
                  gap: "6px",
                  flexWrap: "wrap",
                }}
              >
                {article.entities.map((e, i) => (
                  <span
                    key={i}
                    style={{
                      background: "var(--tag-bg)",
                      color: "var(--tag-text)",
                      padding: "3px 10px",
                      borderRadius: "2px",
                      fontSize: "12px",
                      fontFamily: "var(--font-body)",
                    }}
                  >
                    {e.entity_name_en || e.entity_name}
                    <span style={{ opacity: 0.5, marginLeft: "4px" }}>
                      {e.entity_type}
                    </span>
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Key quote */}
          {article.key_quote && (
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
                {article.key_quote_en && (
                  <p
                    style={{
                      color: "var(--text-muted)",
                      marginTop: "4px",
                      fontStyle: "normal",
                      fontSize: "13px",
                    }}
                  >
                    — {article.key_quote_en}
                  </p>
                )}
              </blockquote>
            </div>
          )}

          {/* Source link */}
          <a
            href={article.url}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              fontSize: "12px",
              fontFamily: "var(--font-mono)",
              color: "var(--accent-teal)",
              textDecoration: "none",
            }}
          >
            View original source →
          </a>

          {/* Analyst commentary */}
          <div style={{ marginTop: "20px" }}>
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
              Analyst Commentary
            </h4>
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
        </div>
      )}
    </article>
  );
}
