// Shared chrome for the section pages ("reading documents", Morning Brief
// redesign phase 2). Two things every section page opens with:
//
//   <DocumentHeader eyebrow="Security · Military" title=… standfirst=… meta=… />
//     eyebrow (Archivo micro-caps) / Newsreader 34px title / standfirst
//     (Public Sans, muted — usually the page's Copy block for its intro key) with a
//     right-hand meta block (Archivo, faint) and an optional admin action slot.
//     Closed by a hairline rule.
//
//   <StatGrid columns={4}><StatBlock label value note accent /> …</StatGrid>
//     the 4-up stat band: `gap: 1px` on a `--hair` background inside a 1px
//     `--hair` border — the hairline grid comes from the gap, never from
//     per-cell borders. Figures are Newsreader 28px; captions Archivo 8.5px.
//
// Section rules within a page stay `SectionHeader` (MilitaryTab.jsx).
import React from "react";

const EYEBROW = {
  fontFamily: "var(--font-mono)",
  fontSize: "9px",
  letterSpacing: "0.24em",
  textTransform: "uppercase",
  color: "var(--faint)",
  marginBottom: "7px",
};
const TITLE = {
  fontFamily: "var(--font-headline)",
  fontSize: "34px",
  fontWeight: 500,
  lineHeight: 1.1,
  color: "var(--ink)",
  margin: 0,
  textWrap: "balance",
};
export const STANDFIRST = {
  fontFamily: "var(--font-body)",
  fontSize: "13.5px",
  lineHeight: 1.65,
  color: "var(--muted)",
  margin: "10px 0 0",
  maxWidth: "680px",
  textWrap: "pretty",
};
const META = {
  fontFamily: "var(--font-mono)",
  fontSize: "9px",
  letterSpacing: "0.08em",
  color: "var(--faint)",
  textAlign: "right",
  lineHeight: 1.6,
  whiteSpace: "nowrap",
  flexShrink: 0,
  paddingTop: "6px",
};

/**
 * Page header for a section view.
 *  eyebrow     "Security · Military" — nav group · view (chrome, English).
 *  title       Newsreader 34px. Pass a string or a <Copy> node.
 *  standfirst  the page intro — a <Copy> node (styled by the caller with
 *              STANDFIRST) or plain JSX; rendered under the title.
 *  meta        one line or an array of lines for the right block (data
 *              vintage, counts). Strings only — chrome.
 *  actions     admin buttons (already gated by the caller) — sit above meta.
 */
export function DocumentHeader({ eyebrow, title, standfirst, meta, actions }) {
  const metaLines = meta == null ? [] : Array.isArray(meta) ? meta.filter(Boolean) : [meta];
  return (
    <header style={{
      display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "12px 24px", flexWrap: "wrap",
      borderBottom: "1px solid var(--hair)", paddingBottom: "18px", marginBottom: "22px",
    }}>
      <div style={{ minWidth: 0 }}>
        {eyebrow && <div style={EYEBROW}>{eyebrow}</div>}
        <h1 style={TITLE}>{title}</h1>
        {standfirst}
      </div>
      {(actions || metaLines.length > 0) && (
        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: "10px", flexShrink: 0 }}>
          {actions}
          {metaLines.length > 0 && (
            <div style={META}>
              {metaLines.map((m, i) => <div key={i}>{m}</div>)}
            </div>
          )}
        </div>
      )}
    </header>
  );
}

/** Hairline stat band. `columns` = cell count per row on desktop (collapses to 2 under 640px via .stat-grid). */
export function StatGrid({ columns = 4, children, style }) {
  return (
    <div className="stat-grid" style={{ "--cols": columns, ...style }}>
      {children}
    </div>
  );
}

/**
 * One stat cell.
 *  label    Archivo caption (uppercase) — with an optional `chip` at its right.
 *  value    the figure, Newsreader 28px, `--ink` or `accent`.
 *  delta    Archivo 10px line under the figure (e.g. "▲ 12% vs prior window"),
 *           coloured by `deltaColour` (defaults muted — neutral unless the
 *           caller has a reason, e.g. sentiment band; coast-guard deltas stay neutral).
 *  note     Public Sans 11px muted line (context, period, source).
 */
export function StatBlock({ label, value, delta, deltaColour, note, accent, chip, title }) {
  return (
    <div title={title} style={{ background: "var(--bg)", padding: "14px 16px", minWidth: 0 }}>
      <div style={{
        fontFamily: "var(--font-mono)", fontSize: "8.5px", letterSpacing: "0.14em", textTransform: "uppercase",
        color: "var(--faint)", marginBottom: "8px", display: "flex", justifyContent: "space-between",
        alignItems: "center", gap: "8px",
      }}>
        <span style={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{label}</span>
        {chip}
      </div>
      <div style={{
        fontFamily: "var(--font-headline)", fontSize: "28px", fontWeight: 500, lineHeight: 1.05,
        color: accent || "var(--ink)", fontVariantNumeric: "tabular-nums",
      }}>
        {value}
      </div>
      {delta && (
        <div style={{
          fontFamily: "var(--font-mono)", fontSize: "10px", letterSpacing: "0.04em",
          color: deltaColour || "var(--muted)", marginTop: "6px",
        }}>
          {delta}
        </div>
      )}
      {note && (
        <div style={{ fontFamily: "var(--font-body)", fontSize: "11px", color: "var(--muted)", marginTop: delta ? "2px" : "6px", lineHeight: 1.45 }}>
          {note}
        </div>
      )}
    </div>
  );
}
