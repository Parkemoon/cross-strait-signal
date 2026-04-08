import { useState, useEffect } from "react";
import {
  fetchKeyFigures,
  fetchKeyFigureCandidates,
  approveKeyFigureStatement,
  dismissKeyFigureStatement,
} from "../api";
import SourceBadge from "./SourceBadge";
import { READ_ONLY } from "../readOnly";

const PARTY_ACCENT = { PRC: "#dc2626", DPP: "#16a34a", KMT: "#1d4ed8" };

function figureAccent(figure) {
  return PARTY_ACCENT[figure.party] || PARTY_ACCENT[figure.side] || "#6b7280";
}

function formatDate(ts) {
  if (!ts) return null;
  return new Date(ts).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

function relativeTime(ts) {
  if (!ts) return null;
  const h = Math.floor((Date.now() - new Date(ts).getTime()) / 3600000);
  if (h < 1) return "< 1h ago";
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function Portrait({ portrait, nameEn, figure, attribution }) {
  const [error, setError] = useState(false);
  const initials = nameEn.split(" ").slice(0, 2).map((w) => w[0]).join("");
  const accent = figureAccent(figure);

  if (error || !portrait) {
    return (
      <div style={{
        width: 48, height: 48, borderRadius: "50%", background: accent,
        display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
      }}>
        <span style={{ color: "#fff", fontSize: "15px", fontWeight: 600, fontFamily: "var(--font-mono)" }}>
          {initials}
        </span>
      </div>
    );
  }

  return (
    <img
      src={`/figures/${portrait}`}
      alt={nameEn}
      title={attribution || undefined}
      onError={() => setError(true)}
      style={{
        width: 48, height: 48, borderRadius: "50%",
        objectFit: "cover", objectPosition: "center top", flexShrink: 0,
        border: `2px solid ${accent}`,
      }}
    />
  );
}

function CandidateModal({ figure, candidates, onApprove, onDismiss, onClose }) {
  const accent = figureAccent(figure);
  const [processing, setProcessing] = useState(null);

  const handle = async (fn, id) => {
    setProcessing(id);
    await fn(id);
    setProcessing(null);
  };

  return (
    <div
      onClick={(e) => e.target === e.currentTarget && onClose()}
      style={{
        position: "fixed", inset: 0,
        background: "rgba(0,0,0,0.55)",
        display: "flex", alignItems: "center", justifyContent: "center",
        zIndex: 1000,
      }}
    >
      <div style={{
        background: "var(--bg-card)",
        border: "1px solid var(--border-color)",
        borderTop: `4px solid ${accent}`,
        borderRadius: "4px",
        width: 500, maxWidth: "92vw", maxHeight: "80vh",
        display: "flex", flexDirection: "column",
      }}>
        {/* Modal header */}
        <div style={{
          display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "14px 16px", borderBottom: "1px solid var(--border-color)",
        }}>
          <div>
            <span style={{
              fontFamily: "var(--font-mono)", fontSize: "11px", fontWeight: 700,
              letterSpacing: "0.07em", textTransform: "uppercase", color: "var(--text-primary)",
            }}>
              {figure.name_en}
            </span>
            <span style={{ fontSize: "10px", color: "var(--text-muted)", marginLeft: "8px" }}>
              {candidates.length} pending candidate{candidates.length !== 1 ? "s" : ""}
            </span>
          </div>
          <button
            onClick={onClose}
            style={{
              background: "none", border: "none", cursor: "pointer",
              color: "var(--text-muted)", fontSize: "16px", lineHeight: 1, padding: "2px 4px",
            }}
          >
            ✕
          </button>
        </div>

        {/* Candidate list */}
        <div style={{ overflowY: "auto", padding: "8px 0" }}>
          {candidates.length === 0 ? (
            <div style={{ padding: "24px 16px", color: "var(--text-muted)", fontSize: "13px", fontStyle: "italic" }}>
              No pending candidates.
            </div>
          ) : candidates.map((c) => (
            <div key={c.id} style={{
              padding: "12px 16px",
              borderBottom: "1px solid var(--border-color)",
            }}>
              {/* Meta row */}
              <div style={{ display: "flex", alignItems: "center", gap: "6px", marginBottom: "6px", flexWrap: "wrap" }}>
                <SourceBadge sourceName={c.source_name} bias={c.source_bias} />
                <span style={{
                  fontSize: "9px", fontFamily: "var(--font-mono)", fontWeight: 700,
                  textTransform: "uppercase", letterSpacing: "0.05em",
                  background: c.statement_kind === "quote" ? "#1d4ed820" : "#15803d20",
                  color: c.statement_kind === "quote" ? "#1d4ed8" : "#15803d",
                  padding: "1px 5px", borderRadius: "2px",
                }}>
                  {c.statement_kind}
                </span>
                <span style={{ fontSize: "10px", fontFamily: "var(--font-mono)", color: "var(--text-muted)" }}>
                  {formatDate(c.published_at)} · {relativeTime(c.published_at)}
                </span>
                <a
                  href={c.article_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{ fontSize: "10px", color: "var(--text-muted)", marginLeft: "auto" }}
                >
                  view article →
                </a>
              </div>

              {/* Statement text */}
              <div style={{
                fontSize: "13px", lineHeight: 1.5, color: "var(--text-primary)",
                fontStyle: c.statement_kind === "quote" ? "italic" : "normal",
                marginBottom: "10px",
              }}>
                {c.statement_kind === "quote"
                  ? `\u201c${c.statement_text}\u201d`
                  : c.statement_text}
              </div>

              {/* Action buttons */}
              <div style={{ display: "flex", gap: "6px" }}>
                <button
                  onClick={() => handle(onApprove, c.id)}
                  disabled={processing === c.id}
                  style={{
                    fontSize: "11px", padding: "4px 12px",
                    background: "#15803d", color: "#fff",
                    border: "none", borderRadius: "2px", cursor: "pointer",
                    opacity: processing === c.id ? 0.6 : 1,
                  }}
                >
                  Approve
                </button>
                <button
                  onClick={() => handle(onDismiss, c.id)}
                  disabled={processing === c.id}
                  style={{
                    fontSize: "11px", padding: "4px 12px",
                    background: "transparent", color: "var(--text-muted)",
                    border: "1px solid var(--border-color)", borderRadius: "2px", cursor: "pointer",
                    opacity: processing === c.id ? 0.6 : 1,
                  }}
                >
                  Dismiss
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function FigureCard({ figure, pendingCount, onOpenCuration, onClearStatement }) {
  const { name_en, name_zh, role, portrait, latest } = figure;
  const accent = figureAccent(figure);

  return (
    <div style={{
      minWidth: "230px", maxWidth: "230px",
      background: "var(--bg-card)",
      border: "1px solid var(--border-color)",
      borderLeft: `4px solid ${accent}`,
      borderRadius: "3px",
      padding: "12px",
      flexShrink: 0,
      display: "flex", flexDirection: "column",
    }}>
      {/* Header: portrait + name/role + curate icon */}
      <div style={{ display: "flex", gap: "10px", alignItems: "flex-start", marginBottom: "8px" }}>
        <Portrait portrait={portrait} nameEn={name_en} figure={figure} attribution={figure.attribution} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{
            fontSize: "11px", fontFamily: "var(--font-mono)", fontWeight: 700,
            letterSpacing: "0.07em", textTransform: "uppercase",
            color: "var(--text-primary)", lineHeight: 1.3,
          }}>
            {name_en}
          </div>
          <div style={{ fontSize: "10px", color: "var(--text-muted)", marginTop: "2px", lineHeight: 1.3 }}>
            {name_zh} · {role}
          </div>
        </div>
        {/* Curate button — admin only */}
        {!READ_ONLY && (
          <button
            onClick={onOpenCuration}
            title={pendingCount > 0 ? `${pendingCount} pending candidate${pendingCount > 1 ? "s" : ""}` : "Curate statement"}
            style={{
              background: "none", border: "none", cursor: "pointer",
              padding: "2px", flexShrink: 0, lineHeight: 1,
              position: "relative",
            }}
          >
            <span style={{ fontSize: "13px", color: pendingCount > 0 ? "#d97706" : "var(--text-muted)" }}>✎</span>
            {pendingCount > 0 && (
              <span style={{
                position: "absolute", top: "-4px", right: "-4px",
                background: "#d97706", color: "#fff",
                fontSize: "8px", fontWeight: 700, fontFamily: "var(--font-mono)",
                width: "14px", height: "14px", borderRadius: "50%",
                display: "flex", alignItems: "center", justifyContent: "center",
              }}>
                {pendingCount > 9 ? "9+" : pendingCount}
              </span>
            )}
          </button>
        )}
      </div>

      {/* Quote / summary / empty state */}
      {latest ? (
        <a
          href={latest.article_url}
          target="_blank"
          rel="noopener noreferrer"
          style={{ textDecoration: "none", color: "inherit", flex: 1 }}
        >
          <div style={{
            fontSize: "12px", lineHeight: 1.5, color: "var(--text-primary)",
            fontStyle: latest.display_kind === "quote" ? "italic" : "normal",
            marginBottom: "10px",
          }}>
            {latest.display_kind === "quote"
              ? `\u201c${latest.display_text}\u201d`
              : latest.display_text}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "6px", flexWrap: "wrap" }}>
            <SourceBadge sourceName={latest.source_name} bias={latest.source_bias} />
            <span style={{ fontSize: "10px", fontFamily: "var(--font-mono)", color: "var(--text-muted)" }}>
              {formatDate(latest.published_at)}
            </span>
            <span style={{ fontSize: "10px", fontFamily: "var(--font-mono)", color: "var(--text-muted)" }}>
              · {relativeTime(latest.published_at)}
            </span>
            {!READ_ONLY && (
              <button
                onClick={(e) => { e.preventDefault(); onClearStatement(latest.statement_id); }}
                title="Clear this statement"
                style={{
                  marginLeft: "auto", background: "none", border: "none", cursor: "pointer",
                  color: "var(--text-muted)", fontSize: "11px", padding: "0 2px", lineHeight: 1,
                }}
              >
                ✕
              </button>
            )}
          </div>
        </a>
      ) : (
        <div style={{ flex: 1 }}>
          <div style={{
            fontSize: "12px", color: "var(--text-muted)", fontStyle: "italic", marginBottom: "10px",
          }}>
            No curated statement yet
          </div>
          <div style={{ fontSize: "10px", fontFamily: "var(--font-mono)", color: "var(--text-muted)" }}>
            —
          </div>
        </div>
      )}
    </div>
  );
}

export default function KeyFigures() {
  const [figures, setFigures] = useState([]);
  const [candidates, setCandidates] = useState({});
  const [openCurationFor, setOpenCurationFor] = useState(null);

  const loadFigures = () => {
    fetchKeyFigures()
      .then((d) => setFigures(d.figures || []))
      .catch(() => {});
  };

  useEffect(() => {
    loadFigures();
    fetchKeyFigureCandidates()
      .then((d) => setCandidates(d.candidates || {}))
      .catch(() => {});
  }, []);

  const handleApprove = async (statementId) => {
    await approveKeyFigureStatement(statementId);
    setCandidates((prev) => {
      const updated = { ...prev };
      for (const fid of Object.keys(updated)) {
        updated[fid] = updated[fid].filter((s) => s.id !== statementId);
      }
      return updated;
    });
    loadFigures();
  };

  const handleDismiss = async (statementId) => {
    await dismissKeyFigureStatement(statementId);
    setCandidates((prev) => {
      const updated = { ...prev };
      for (const fid of Object.keys(updated)) {
        updated[fid] = updated[fid].filter((s) => s.id !== statementId);
      }
      return updated;
    });
  };

  const handleClear = async (statementId) => {
    await dismissKeyFigureStatement(statementId);
    loadFigures();
  };

  if (!figures.length) return null;

  const curationFigure = openCurationFor ? figures.find((f) => f.id === openCurationFor) : null;

  return (
    <div style={{ marginBottom: "32px" }}>
      <h3 style={{
        fontFamily: "var(--font-headline)", fontSize: "13px", fontWeight: 600,
        letterSpacing: "0.08em", textTransform: "uppercase",
        color: "var(--text-muted)", margin: "0 0 8px 0",
      }}>
        Key Figures
      </h3>

      <div style={{ display: "flex", gap: "10px", overflowX: "auto", paddingBottom: "4px" }}>
        {figures.map((figure) => (
          <FigureCard
            key={figure.id}
            figure={figure}
            pendingCount={(candidates[figure.id] || []).length}
            onOpenCuration={() => setOpenCurationFor(figure.id)}
            onClearStatement={handleClear}
          />
        ))}
      </div>

      {!READ_ONLY && openCurationFor && curationFigure && (
        <CandidateModal
          figure={curationFigure}
          candidates={candidates[openCurationFor] || []}
          onApprove={handleApprove}
          onDismiss={handleDismiss}
          onClose={() => setOpenCurationFor(null)}
        />
      )}
    </div>
  );
}
