import {
  Bar, ComposedChart, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from "recharts";

// Shared bits for the Coast Guard tracker components (CoastGuardSection /
// CoastGuardMap / CoastGuardRosterModal) — the same pattern as
// pollFormShared.jsx. Force palette reuses the locked side conventions
// (PRC red, ROC green, JP teal, US blue — see ExerciseMap PERFORMER_COLOUR).
// NOTE: red↔green fails the CVD validator when adjacent (ΔE 5.0 deutan), so
// CCG and CGA must never share a stacked or grouped mark.
export const FORCE_COLOUR = { CCG: "var(--red)", CGA: "var(--green)", JCG: "var(--cyan)", USCG: "var(--blue)" };
export const FORCE_LABEL  = { CCG: "China Coast Guard", CGA: "Taiwan Coast Guard", JCG: "Japan Coast Guard", USCG: "US Coast Guard" };
export const FORCES = ["CCG", "CGA", "JCG", "USCG"];

export function Pill({ active, onClick, children, colour }) {
  return (
    <button onClick={onClick} style={{
      fontFamily: "var(--font-mono)", fontSize: "10px", letterSpacing: "0.05em", cursor: "pointer",
      padding: "3px 9px", background: active ? (colour || "var(--text-primary)") : "transparent",
      color: active ? "var(--bg-primary)" : "var(--text-secondary)",
      border: `1px solid ${active ? (colour || "var(--text-primary)") : "var(--border-color)"}`,
    }}>{children}</button>
  );
}

// ---------------------------------------------------------------- chart primitives
// Shared by CoastGuardSection and MaritimeCivilSection (Phase 2g): the two
// sections sit on one page and must read as one instrument — same strips,
// same caveat box, same zone pills, same formatters.
export const GROUPS = [
  { id: "kinmen",     label: "Kinmen", },
  { id: "matsu",      label: "Matsu", },
  { id: "median",     label: "Median line", },
  { id: "contiguous", label: "24 nm zone", },
  { id: "pratas",     label: "Pratas", },
  { id: "east",       label: "East box", },
  { id: "taiwan_bank", label: "Taiwan Bank", },   // Phase 2g shoal box — the dredger theatre
  { id: "",           label: "All zones", },
];
export const RANGES = [{ label: "3Y", months: 36 }, { label: "5Y", months: 60 }, { label: "All", months: 200 }];
export const MONTH_ABBR = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

export const fmtMonth = (ym) => { if (!ym) return ""; const [y, m] = ym.split("-"); return `${MONTH_ABBR[Number(m) - 1]} ${y.slice(2)}`; };
export const fmtDay = (iso) => { if (!iso) return ""; const [, m, d] = iso.split("-"); return `${MONTH_ABBR[Number(m) - 1]} ${Number(d)}`; };
export const fmtInt = (n) => (n === null || n === undefined ? "—" : Number(n).toLocaleString());
export const addMonths = (ym, n) => { const [y, m] = ym.split("-").map(Number); const d = new Date(Date.UTC(y, m - 1 + n, 1)); return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`; };

export const TICK = { fontFamily: "var(--font-mono)", fontSize: 10, fill: "var(--text-muted)" };

export const TOOLTIP_STYLE = { background: "var(--bg-primary)", border: "1px solid var(--border-color)", fontFamily: "var(--font-mono)", fontSize: "11px" };

// Every CGA number on this section comes from a specific report PDF (the
// rows carry source_url); cite it with a link, never a bare "表8-1".
export function SrcLink({ href, children, muted }) {
  if (!href) return <span>{children}</span>;
  return (
    <a href={href} target="_blank" rel="noreferrer"
       style={{ color: muted ? "var(--text-muted)" : "var(--text-secondary)", textDecoration: "underline dotted", textUnderlineOffset: 2 }}>
      {children}
    </a>
  );
}
// The CGA report PDF a table came from: the monthly report wins, the yearbook
// (or the manual 護永專案 rows) is the fallback. Both Maritime sections cite 表8-1 with it.
export const latestSource = (sources, table) =>
  (sources || []).find((r) => r.source === "monthly" && r.source_ref.endsWith(table)) ||
  (sources || []).find((r) => r.source_ref.endsWith(table));

export function SubHeader({ children, right }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", margin: "22px 0 8px" }}>
      <span style={{ fontFamily: "var(--font-mono)", fontSize: "10.5px", fontWeight: 600, letterSpacing: "0.1em",
                     textTransform: "uppercase", color: "var(--text-primary)" }}>{children}</span>
      {right && <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--text-muted)" }}>{right}</span>}
    </div>
  );
}


// Delta vs the previous window. Deliberately NEUTRAL (no hostile purple /
// cooperative amber): more CCG presence and more CGA enforcement are both
// "more activity", and this tracker must not score one side's activity as
// bad and the other's as good.
export function deltaText(cur, prev) {
  if (!prev) return cur ? "no prior-window data" : null;
  const pct = ((cur - prev) / prev) * 100;
  return `${pct >= 0 ? "▲" : "▼"} ${Math.abs(pct).toFixed(0)}% vs prior window (${fmtInt(prev)})`;
}

// Scoped caveats from summary.caveats — the chart can't render without them.
export function Caveats({ caveats, scopes, compact }) {
  const rows = (caveats || []).filter((c) => scopes.includes(c.scope));
  if (!rows.length) return null;
  return (
    <div style={{ margin: compact ? "6px 0 0" : "10px 0 0", padding: "8px 10px", border: "1px dashed var(--border-color)",
                  background: "var(--bg-card)", fontFamily: "var(--font-body)", fontSize: "11.5px", color: "var(--text-secondary)", lineHeight: 1.5 }}>
      {rows.map((c) => (
        <div key={c.key} style={{ marginBottom: 3 }}>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: "9.5px", color: "var(--flag)", marginRight: 6 }}>⚑ CAVEAT</span>
          {c.en}
        </div>
      ))}
    </div>
  );
}

// One force, one strip, one axis. `unit` names the measure for the tooltip.
export function MonthlyStrip({ data, dataKey, colour, title, titleLink, unit, syncId, height = 130, xKey = "month", fmt = fmtMonth }) {
  return (
    <div style={{ marginBottom: 6 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, fontFamily: "var(--font-mono)", fontSize: "10.5px", color: "var(--text-primary)", marginBottom: 2 }}>
        <span style={{ display: "inline-block", width: 10, height: 10, background: colour }} />
        {title}
        {titleLink}
      </div>
      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} syncId={syncId} margin={{ top: 6, right: 12, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="2 4" stroke="var(--border-color)" vertical={false} />
            <XAxis dataKey={xKey} tick={TICK} stroke="var(--border-color)" tickFormatter={fmt} interval="preserveStartEnd" minTickGap={48} />
            <YAxis tick={TICK} stroke="var(--border-color)" width={38} allowDecimals={false} />
            <Tooltip contentStyle={TOOLTIP_STYLE} labelFormatter={fmt}
                     formatter={(v) => [fmtInt(v), unit]} />
            <Bar dataKey={dataKey} fill={colour} maxBarSize={9} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

