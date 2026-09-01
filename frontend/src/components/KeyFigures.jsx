import { useState, useEffect, useRef } from "react";
import {
  fetchKeyFigures,
  fetchKeyFigureCandidates,
  approveKeyFigureStatement,
  dismissKeyFigureStatement,
} from "../api";
import SourceBadge from "./SourceBadge";
import { READ_ONLY } from "../readOnly";
import { PARTY_COLOURS } from "../partyColours";

function figureAccent(figure) {
  return PARTY_COLOURS[figure.party] || PARTY_COLOURS[figure.side] || "var(--muted)";
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
        width: 44, height: 44, borderRadius: "50%", background: accent,
        display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
        margin: "0 auto",
      }}>
        <span style={{ color: "var(--bg)", fontSize: "14px", fontWeight: 600, fontFamily: "var(--font-mono)" }}>
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
        width: 44, height: 44, borderRadius: "50%",
        objectFit: "cover", objectPosition: "center top", flexShrink: 0,
        margin: "0 auto", display: "block",
      }}
    />
  );
}

function CandidateModal({ figure, candidates, onApprove, onDismiss, onClose }) {
  const accent = figureAccent(figure);
  const [processing, setProcessing] = useState(null);

  const handle = async (fn, id) => {
    setProcessing(id);
    try {
      await fn(id);
    } catch (err) {
      // Clear the processing flag (and surface the error) so the candidate's
      // Approve/Dismiss buttons don't stay disabled forever on a failed call.
      console.error("Key-figure action failed:", err);
      alert(`Action failed: ${err.message || err}`);
    } finally {
      setProcessing(null);
    }
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
        borderTop: `3px solid ${accent}`,
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
                  background: "var(--soft)",
                  color: "var(--muted)",
                  padding: "1px 5px", borderRadius: 0,
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
                    background: "var(--ink)", color: "var(--bg)",
                    border: "1px solid var(--ink)", cursor: "pointer",
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
                    border: "1px solid var(--border-color)", borderRadius: 0, cursor: "pointer",
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
      minWidth: "215px", maxWidth: "215px",
      padding: "4px 12px 8px",
      flexShrink: 0,
      display: "flex", flexDirection: "column",
      textAlign: "center",
      position: "relative",
    }}>
      {/* Curate button — admin only, corner overlay */}
      {!READ_ONLY && (
        <button
          onClick={onOpenCuration}
          title={pendingCount > 0 ? `${pendingCount} pending candidate${pendingCount > 1 ? "s" : ""}` : "Curate statement"}
          style={{
            background: "none", border: "none", cursor: "pointer",
            padding: "2px", lineHeight: 1,
            position: "absolute", top: 0, right: "4px", zIndex: 1,
          }}
        >
          <span style={{ fontSize: "13px", color: pendingCount > 0 ? "var(--flag)" : "var(--pale)" }}>✎</span>
          {pendingCount > 0 && (
            <span style={{
              color: "var(--flag)",
              fontSize: "9px", fontWeight: 700, fontFamily: "var(--font-mono)",
              marginLeft: "2px", verticalAlign: "top",
            }}>
              {pendingCount > 9 ? "9+" : pendingCount}
            </span>
          )}
        </button>
      )}

      <div style={{ marginBottom: "7px" }}>
        <Portrait portrait={portrait} nameEn={name_en} figure={figure} attribution={figure.attribution} />
      </div>

      {/* Quote / empty state */}
      {latest ? (
        <a
          href={latest.article_url}
          target="_blank"
          rel="noopener noreferrer"
          style={{ textDecoration: "none", color: "inherit", flex: 1, display: "flex", flexDirection: "column" }}
        >
          <div style={{
            fontFamily: "var(--font-headline)",
            fontSize: "13px", lineHeight: 1.5, color: "var(--body)",
            fontStyle: "italic",
            marginBottom: "6px",
            flex: 1,
            display: "-webkit-box",
            WebkitLineClamp: 8,
            WebkitBoxOrient: "vertical",
            overflow: "hidden",
          }}>
            {latest.display_kind === "quote"
              ? `\u201c${latest.display_text}\u201d`
              : latest.display_text}
          </div>
          <div style={{
            fontFamily: "var(--font-mono)", fontSize: "8.5px",
            color: "var(--pale)", letterSpacing: "0.08em", lineHeight: 1.7,
          }}>
            <span style={{ color: accent, fontWeight: 700 }}>{name_en.toUpperCase()} {name_zh}</span>
            <br />
            <span style={{ color: accent }}>{role?.toUpperCase()}</span>
            {" · "}
            <SourceBadge sourceName={latest.source_name} bias={latest.source_bias} />
            {" "}
            {formatDate(latest.published_at)?.toUpperCase()}
            {!READ_ONLY && (
              <button
                onClick={(e) => { e.preventDefault(); onClearStatement(latest.statement_id); }}
                title="Clear this statement"
                style={{
                  background: "none", border: "none", cursor: "pointer",
                  color: "var(--pale)", fontSize: "10px", padding: "0 3px", lineHeight: 1,
                }}
              >
                ✕
              </button>
            )}
          </div>
        </a>
      ) : (
        <div style={{ flex: 1, display: "flex", flexDirection: "column" }}>
          <div style={{
            fontFamily: "var(--font-headline)",
            fontSize: "13px", color: "var(--pale)", fontStyle: "italic", marginBottom: "6px", flex: 1,
          }}>
            No curated statement yet
          </div>
          <div style={{
            fontFamily: "var(--font-mono)", fontSize: "8.5px",
            color: "var(--pale)", letterSpacing: "0.08em", lineHeight: 1.7,
          }}>
            <span style={{ color: accent, fontWeight: 700 }}>{name_en.toUpperCase()} {name_zh}</span>
            <br />
            <span style={{ color: accent }}>{role?.toUpperCase()}</span>
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
  const [canScrollLeft, setCanScrollLeft] = useState(false);
  const [canScrollRight, setCanScrollRight] = useState(false);
  const scrollRef = useRef(null);

  const updateScrollState = () => {
    const el = scrollRef.current;
    if (!el) return;
    setCanScrollLeft(el.scrollLeft > 0);
    setCanScrollRight(el.scrollLeft < el.scrollWidth - el.clientWidth - 1);
  };

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    updateScrollState();
    el.addEventListener("scroll", updateScrollState);
    return () => el.removeEventListener("scroll", updateScrollState);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [figures]);

  const scrollBy = (dir) => {
    if (scrollRef.current) scrollRef.current.scrollBy({ left: dir * 240, behavior: "smooth" });
  };

  const loadFigures = () => {
    fetchKeyFigures()
      .then((d) => setFigures(d.figures || []))
      .catch(() => {});
  };

  useEffect(() => {
    loadFigures();
    // Candidates queue is admin-only — skip the call entirely in the
    // public read-only build (the API would 401 it anyway).
    if (!READ_ONLY) {
      fetchKeyFigureCandidates()
        .then((d) => setCandidates(d.candidates || {}))
        .catch(() => {});
    }
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

  const arrowStyle = {
    position: "absolute", top: "50%", transform: "translateY(-50%)",
    zIndex: 2,
    background: "var(--bg)",
    border: "1px solid var(--hair)",
    borderRadius: "50%",
    width: "28px", height: "28px",
    display: "flex", alignItems: "center", justifyContent: "center",
    cursor: "pointer",
    boxShadow: "0 2px 6px rgba(0,0,0,0.12)",
    color: "var(--text-secondary)",
    fontSize: "18px",
    lineHeight: 1,
    padding: 0,
  };

  return (
    <div style={{ marginBottom: "32px" }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: "10px", marginBottom: "14px" }}>
        <span style={{
          fontFamily: "var(--font-mono)", fontSize: "9.5px", fontWeight: 600,
          letterSpacing: "0.24em", textTransform: "uppercase", color: "var(--ink)",
        }}>
          Voices
        </span>
        <span style={{ flex: 1, borderBottom: "1px solid var(--hair)" }} />
      </div>

      <div className="key-figures-scroll-wrapper" style={{ position: "relative" }}>
        {/* Left scroll arrow */}
        <button
          className={`scroll-arrow${canScrollLeft ? "" : " hidden"}`}
          onClick={() => scrollBy(-1)}
          style={{ ...arrowStyle, left: 0 }}
        >
          ‹
        </button>

        {/* Cards strip */}
        <div
          ref={scrollRef}
          className="hide-scrollbar"
          style={{ display: "flex", gap: "10px", overflowX: "auto", paddingBottom: "4px" }}
        >
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

        {/* Right scroll arrow */}
        <button
          className={`scroll-arrow${canScrollRight ? "" : " hidden"}`}
          onClick={() => scrollBy(1)}
          style={{ ...arrowStyle, right: 0 }}
        >
          ›
        </button>

        {/* Edge fade gradients — always visible when scrollable */}
        {canScrollLeft && (
          <div style={{
            position: "absolute", left: 0, top: 0, bottom: 4,
            width: "40px", pointerEvents: "none", zIndex: 1,
            background: "linear-gradient(to right, var(--bg-primary), transparent)",
          }} />
        )}
        {canScrollRight && (
          <div style={{
            position: "absolute", right: 0, top: 0, bottom: 4,
            width: "40px", pointerEvents: "none", zIndex: 1,
            background: "linear-gradient(to left, var(--bg-primary), transparent)",
          }} />
        )}
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
