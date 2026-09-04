// Shared chrome for the admin surfaces (Morning Brief redesign, phase 2B):
// the modal frame every analyst modal / review queue sits in, the four
// button verbs, and the form field + label styles. One place, so a modal
// restyle is a token change here rather than thirteen inline copies.
//
//   <ModalFrame title meta onClose busy width accent footer>…</ModalFrame>
//     overlay + paper panel (1px hair border, 2px ink top rule — `accent`
//     recolours the rule: --flag for review queues, --hostile for military,
//     a figure's alignment colour for curation). Header = Newsreader 20px
//     title + Archivo meta + ✕. Body scrolls; `footer` sits under a hairline.
//
//   <Btn variant="primary|outline|ghost|danger" …>   Archivo 9px/0.14em caps,
//     7px 16px — the design's review-card action row. primary = solid ink on
//     paper (ONE per action row), outline = hair border (hover → ink),
//     ghost = borderless pale (hover → ink), danger = outline in --red.
//
//   FIELD / LABEL / MICRO   inline style objects for inputs, their captions
//     and micro-caps metadata; `.field` in index.css carries the focus ring.
import React from "react";

export const MICRO = {
  fontFamily: "var(--font-mono)",
  fontSize: "8.5px",
  letterSpacing: "0.12em",
  textTransform: "uppercase",
  color: "var(--faint)",
};

export const LABEL = {
  ...MICRO,
  display: "block",
  marginBottom: "4px",
};

export const FIELD = {
  fontFamily: "var(--font-body)",
  fontSize: "13px",
  lineHeight: 1.4,
  padding: "6px 8px",
  border: "1px solid var(--hair)",
  borderRadius: 0,
  background: "var(--bg)",
  color: "var(--ink)",
  width: "100%",
  boxSizing: "border-box",
};

// Compact variant for dense edit grids (poll options, roster rows).
export const FIELD_COMPACT = { ...FIELD, fontSize: "12px", padding: "4px 6px" };

export const META_LINE = {
  fontFamily: "var(--font-mono)",
  fontSize: "9px",
  letterSpacing: "0.08em",
  color: "var(--faint)",
  lineHeight: 1.6,
};

export function Btn({ variant = "outline", children, style, className, ...rest }) {
  const cls = `btn btn-${variant}${className ? ` ${className}` : ""}`;
  return (
    <button type="button" className={cls} style={style} {...rest}>
      {children}
    </button>
  );
}

/** Backdrop + panel. `dismissOnBackdrop` false for long forms where a stray click would lose work. */
export function ModalFrame({
  title, meta, onClose, busy = false, width = 720, accent = "var(--ink)",
  children, footer, dismissOnBackdrop = true, bodyStyle, tall = false,
}) {
  return (
    <div
      onClick={(e) => dismissOnBackdrop && e.target === e.currentTarget && !busy && onClose && onClose()}
      style={{
        position: "fixed", inset: 0, zIndex: 1000,
        background: "color-mix(in srgb, var(--ink) 55%, transparent)",
        display: "flex", alignItems: tall ? "flex-start" : "center", justifyContent: "center",
        padding: tall ? "40px 16px" : "16px", overflowY: tall ? "auto" : "hidden",
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={typeof title === "string" ? title : undefined}
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "var(--bg)",
          border: "1px solid var(--hair)",
          borderTop: `2px solid ${accent}`,
          borderRadius: 0,
          width, maxWidth: "100%",
          maxHeight: tall ? "none" : "88vh",
          display: "flex", flexDirection: "column",
          boxShadow: "0 10px 24px rgba(28,26,22,0.13)",
        }}
      >
        <div style={{
          display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: "16px",
          padding: "14px 18px 12px", borderBottom: "1px solid var(--hair)",
        }}>
          <div style={{ minWidth: 0, display: "flex", alignItems: "baseline", gap: "12px", flexWrap: "wrap" }}>
            <span style={{
              fontFamily: "var(--font-headline)", fontSize: "20px", fontWeight: 500,
              lineHeight: 1.2, color: "var(--ink)",
            }}>
              {title}
            </span>
            {meta && <span style={META_LINE}>{meta}</span>}
          </div>
          {onClose && (
            <Btn variant="ghost" onClick={onClose} disabled={busy} aria-label="Close"
                 style={{ padding: "2px 4px", fontSize: "14px", letterSpacing: 0 }}>
              ✕
            </Btn>
          )}
        </div>

        <div style={{
          overflowY: tall ? "visible" : "auto", padding: "14px 18px",
          opacity: busy ? 0.55 : 1, transition: "opacity 0.12s", ...bodyStyle,
        }}>
          {children}
        </div>

        {footer && (
          <div style={{
            display: "flex", gap: "8px", alignItems: "center", flexWrap: "wrap",
            padding: "12px 18px", borderTop: "1px solid var(--hair)",
          }}>
            {footer}
          </div>
        )}
      </div>
    </div>
  );
}

/** Inline error line for modal bodies / footers. */
export function ErrorLine({ children, style }) {
  if (!children) return null;
  return (
    <div style={{ fontFamily: "var(--font-mono)", fontSize: "10px", letterSpacing: "0.04em",
                  color: "var(--red)", marginTop: "8px", ...style }}>
      {children}
    </div>
  );
}

/** Quiet status line for loading / empty states inside admin surfaces. */
export function Quiet({ children, style }) {
  return (
    <div style={{ fontFamily: "var(--font-body)", fontSize: "12.5px", color: "var(--faint)",
                  padding: "24px 0", fontStyle: "italic", ...style }}>
      {children}
    </div>
  );
}
