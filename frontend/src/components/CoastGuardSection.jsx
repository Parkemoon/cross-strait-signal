import { useEffect, useMemo, useState } from "react";
import {
  Bar, Line, ComposedChart, BarChart, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from "recharts";
import {
  fetchCoastGuardSummary, fetchCoastGuardDaily, fetchCoastGuardMonthly,
  fetchCoastGuardEncounters, fetchCoastGuardEnforcement,
} from "../api";
import { READ_ONLY } from "../readOnly";
import CoastGuardMap from "./CoastGuardMap";
import CoastGuardRosterModal from "./CoastGuardRosterModal";

// Coast Guard section of the Military tab (Phase 2e). Two halves, always shown
// together (Ed's standing rule for this tracker): AIS-visible coast-guard
// PRESENCE in Taiwan-drawn zones (GFW, four flags) and the CGA's own
// ENFORCEMENT statistics (PRC vessels expelled / detained) — "what the AIS
// shows" next to "what Taipei reports". The series is a FLOOR, not an
// activity index: every chart renders the scoped caveat from
// `summary.caveats`, and CCG / CGA never share a stacked or grouped mark
// (the locked red/green side palette fails the CVD check when adjacent), so
// each force gets its own strip with the label carrying identity.
const FORCE_COLOUR = { CCG: "#dc2626", CGA: "#16a34a", JCG: "#14B8A6", USCG: "#1d4ed8" };
const FORCE_LABEL  = { CCG: "China Coast Guard", CGA: "Taiwan Coast Guard", JCG: "Japan Coast Guard", USCG: "US Coast Guard" };
const CHART_FORCES = ["CCG", "CGA", "JCG"];          // USCG hidden — 2 hull-days since 2020 (caveat uscg_absent)
const GROUPS = [
  { id: "kinmen",     label: "Kinmen",       zh: "金門" },
  { id: "matsu",      label: "Matsu",        zh: "馬祖" },
  { id: "median",     label: "Median line",  zh: "海峽中線" },
  { id: "contiguous", label: "24 nm zone",   zh: "鄰接區" },
  { id: "pratas",     label: "Pratas",       zh: "東沙" },
  { id: "east",       label: "East box",     zh: "東部海域" },
  { id: "",           label: "All zones",    zh: "全部" },
];
const RANGES = [{ label: "3Y", months: 36 }, { label: "5Y", months: 60 }, { label: "All", months: 200 }];
const MONTH_ABBR = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

const fmtMonth = (ym) => { if (!ym) return ""; const [y, m] = ym.split("-"); return `${MONTH_ABBR[Number(m) - 1]} ${y.slice(2)}`; };
const fmtDay = (iso) => { if (!iso) return ""; const [, m, d] = iso.split("-"); return `${MONTH_ABBR[Number(m) - 1]} ${Number(d)}`; };
const fmtInt = (n) => (n === null || n === undefined ? "—" : Number(n).toLocaleString());
const addMonths = (ym, n) => { const [y, m] = ym.split("-").map(Number); const d = new Date(Date.UTC(y, m - 1 + n, 1)); return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`; };

const TICK = { fontFamily: "var(--font-mono)", fontSize: 10, fill: "var(--text-muted)" };
const TOOLTIP_STYLE = { background: "var(--bg-primary)", border: "1px solid var(--border-color)", fontFamily: "var(--font-mono)", fontSize: "11px" };

// ---------------------------------------------------------------- shared bits
function SubHeader({ children, right }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", margin: "22px 0 8px" }}>
      <span style={{ fontFamily: "var(--font-mono)", fontSize: "10.5px", fontWeight: 600, letterSpacing: "0.1em",
                     textTransform: "uppercase", color: "var(--text-primary)" }}>{children}</span>
      {right && <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--text-muted)" }}>{right}</span>}
    </div>
  );
}

function Pill({ active, onClick, children, colour }) {
  return (
    <button onClick={onClick} style={{
      fontFamily: "var(--font-mono)", fontSize: "10px", letterSpacing: "0.05em", cursor: "pointer",
      padding: "3px 9px", background: active ? (colour || "var(--text-primary)") : "transparent",
      color: active ? "var(--bg-primary)" : "var(--text-secondary)",
      border: `1px solid ${active ? (colour || "var(--text-primary)") : "var(--border-color)"}`,
    }}>{children}</button>
  );
}

function KPICard({ value, label, sublabel, accent }) {
  return (
    <div style={{ padding: "14px 16px", border: "1px solid var(--border-color)", borderLeft: `3px solid ${accent || "var(--border-color)"}`,
                  background: "var(--bg-card)", minWidth: 0 }}>
      <div style={{ fontFamily: "var(--font-mono)", fontSize: "10px", letterSpacing: "0.08em", textTransform: "uppercase",
                    color: "var(--text-muted)", marginBottom: "6px" }}>{label}</div>
      <div style={{ fontFamily: "var(--font-display)", fontSize: "26px", fontWeight: 500, color: "var(--text-primary)", lineHeight: 1.1 }}>{value}</div>
      {sublabel && <div style={{ fontFamily: "var(--font-body)", fontSize: "11px", color: "var(--text-secondary)", marginTop: "4px" }}>{sublabel}</div>}
    </div>
  );
}

// Delta vs the previous window. Deliberately NEUTRAL (no hostile purple /
// cooperative amber): more CCG presence and more CGA enforcement are both
// "more activity", and this tracker must not score one side's activity as
// bad and the other's as good.
function deltaText(cur, prev) {
  if (!prev) return cur ? "no prior-window data" : null;
  const pct = ((cur - prev) / prev) * 100;
  return `${pct >= 0 ? "▲" : "▼"} ${Math.abs(pct).toFixed(0)}% vs prior window (${fmtInt(prev)})`;
}

// Scoped caveats from summary.caveats — the chart can't render without them.
function Caveats({ caveats, scopes, compact }) {
  const rows = (caveats || []).filter((c) => scopes.includes(c.scope));
  if (!rows.length) return null;
  return (
    <div style={{ margin: compact ? "6px 0 0" : "10px 0 0", padding: "8px 10px", border: "1px dashed var(--border-color)",
                  background: "var(--bg-card)", fontFamily: "var(--font-body)", fontSize: "11.5px", color: "var(--text-secondary)", lineHeight: 1.5 }}>
      {rows.map((c) => (
        <div key={c.key} style={{ marginBottom: 3 }}>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: "9.5px", color: "#b8860b", marginRight: 6 }}>⚑ CAVEAT</span>
          {c.en}
          <span style={{ display: "block", color: "var(--text-muted)", fontSize: "10.5px" }}>{c.zh}</span>
        </div>
      ))}
    </div>
  );
}

// One force, one strip, one axis. `unit` names the measure for the tooltip.
function MonthlyStrip({ data, dataKey, colour, title, unit, lineKey, lineLabel, syncId, height = 130 }) {
  return (
    <div style={{ marginBottom: 6 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, fontFamily: "var(--font-mono)", fontSize: "10.5px", color: "var(--text-primary)", marginBottom: 2 }}>
        <span style={{ display: "inline-block", width: 10, height: 10, background: colour }} />
        {title}
        {lineKey && <span style={{ color: "var(--text-muted)" }}>— line: {lineLabel}</span>}
      </div>
      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} syncId={syncId} margin={{ top: 6, right: 12, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="2 4" stroke="var(--border-color)" vertical={false} />
            <XAxis dataKey="month" tick={TICK} stroke="var(--border-color)" tickFormatter={fmtMonth} interval="preserveStartEnd" minTickGap={48} />
            <YAxis tick={TICK} stroke="var(--border-color)" width={38} allowDecimals={false} />
            <Tooltip contentStyle={TOOLTIP_STYLE} labelFormatter={fmtMonth}
                     formatter={(v, key) => [fmtInt(v), key === lineKey ? lineLabel : unit]} />
            <Bar dataKey={dataKey} fill={colour} maxBarSize={9} />
            {lineKey && <Line type="monotone" dataKey={lineKey} stroke="var(--text-primary)" strokeWidth={1.5} dot={false} />}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function DailyStrip({ rows, force }) {
  return (
    <div style={{ marginBottom: 4 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, fontFamily: "var(--font-mono)", fontSize: "10.5px", color: "var(--text-primary)", marginBottom: 2 }}>
        <span style={{ display: "inline-block", width: 10, height: 10, background: FORCE_COLOUR[force] }} />
        {FORCE_LABEL[force]} · hulls present per day, all zones
      </div>
      <div style={{ height: 96 }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} syncId="cg-daily" margin={{ top: 4, right: 12, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="2 4" stroke="var(--border-color)" vertical={false} />
            <XAxis dataKey="date" tick={TICK} stroke="var(--border-color)" tickFormatter={fmtDay} interval="preserveStartEnd" minTickGap={42} />
            <YAxis tick={TICK} stroke="var(--border-color)" width={38} allowDecimals={false} />
            <Tooltip contentStyle={TOOLTIP_STYLE} labelFormatter={fmtDay} formatter={(v) => [fmtInt(v), "hulls"]} />
            <Bar dataKey={force} fill={FORCE_COLOUR[force]} maxBarSize={7} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

// Zone × force table for the summary window. One sequential ramp per column
// (grey → ink) so the number, not a hue, carries identity across forces.
function ZoneTable({ zones }) {
  const max = {};
  for (const f of CHART_FORCES) max[f] = Math.max(1, ...zones.map((z) => z.forces?.[f]?.hull_days || 0));
  const cell = (z, f) => {
    const s = z.forces?.[f];
    const v = s?.hull_days || 0;
    const t = v / max[f];
    return (
      <td key={f} style={{ padding: "5px 8px", textAlign: "right", fontFamily: "var(--font-mono)", fontSize: "11px",
                           background: v ? `rgba(124,124,124,${0.06 + t * 0.32})` : "transparent", color: "var(--text-primary)", whiteSpace: "nowrap" }}>
        {v ? <>{v}<span style={{ color: "var(--text-muted)", fontSize: "9.5px" }}> / {s.hulls}</span></> : <span style={{ color: "var(--text-muted)" }}>·</span>}
      </td>
    );
  };
  return (
    <div style={{ overflowX: "auto", border: "1px solid var(--border-color)", background: "var(--bg-card)" }}>
      <table style={{ borderCollapse: "collapse", width: "100%" }}>
        <thead>
          <tr style={{ fontFamily: "var(--font-mono)", fontSize: "9.5px", letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--text-muted)" }}>
            <th style={{ textAlign: "left", padding: "6px 8px", fontWeight: 600 }}>Zone</th>
            {CHART_FORCES.map((f) => (
              <th key={f} style={{ textAlign: "right", padding: "6px 8px", fontWeight: 600 }}>
                <span style={{ display: "inline-block", width: 8, height: 8, background: FORCE_COLOUR[f], marginRight: 5 }} />{f}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {zones.map((z) => (
            <tr key={z.zone_id} style={{ borderTop: "1px solid var(--border-color)" }}>
              <td style={{ padding: "5px 8px", fontFamily: "var(--font-body)", fontSize: "11.5px", color: "var(--text-primary)", whiteSpace: "nowrap" }}>
                {z.label_en}
                {z.group === "kinmen" && <span title="AIS-visible floor — see Kinmen caveat" style={{ color: "#b8860b", marginLeft: 5, fontSize: "9.5px" }}>⚑</span>}
                <span style={{ display: "block", fontFamily: "var(--font-mono)", fontSize: "9.5px", color: "var(--text-muted)" }}>{z.label_zh}</span>
              </td>
              {CHART_FORCES.map((f) => cell(z, f))}
            </tr>
          ))}
        </tbody>
      </table>
      <div style={{ padding: "5px 8px", fontFamily: "var(--font-mono)", fontSize: "9.5px", color: "var(--text-muted)" }}>hull-days / distinct hulls in window</div>
    </div>
  );
}

function Encounters({ rows }) {
  if (!rows.length) {
    return <div style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--text-muted)", padding: "8px 0" }}>No same-zone co-presence in window.</div>;
  }
  return (
    <div style={{ border: "1px solid var(--border-color)", background: "var(--bg-card)" }}>
      {rows.slice(0, 10).map((r, i) => (
        <div key={`${r.date}-${r.zone_id}`} style={{ padding: "7px 10px", borderTop: i ? "1px solid var(--border-color)" : "none",
                                                     fontFamily: "var(--font-mono)", fontSize: "10.5px", color: "var(--text-secondary)", lineHeight: 1.5 }}>
          <span style={{ color: "var(--text-primary)", fontWeight: 600 }}>{r.date}</span> · {r.zone_id.replace(/_/g, " ")}
          <div>
            <span style={{ color: FORCE_COLOUR.CCG }}>CCG ×{r.ccg}</span>
            {r.cga > 0 && <span style={{ color: FORCE_COLOUR.CGA, marginLeft: 8 }}>CGA ×{r.cga}</span>}
            {r.jcg > 0 && <span style={{ color: FORCE_COLOUR.JCG, marginLeft: 8 }}>JCG ×{r.jcg}</span>}
            <span style={{ color: "var(--text-muted)", marginLeft: 8 }}>{r.ccg_names.slice(0, 4).join(", ")}{r.ccg_names.length > 4 ? "…" : ""}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------- main
export default function CoastGuardSection() {
  const [summary, setSummary] = useState(null);
  const [daily, setDaily] = useState(null);
  const [encounters, setEncounters] = useState([]);
  const [enforcement, setEnforcement] = useState(null);
  const [monthly, setMonthly] = useState(null);
  const [group, setGroup] = useState("kinmen");
  const [range, setRange] = useState(60);
  const [rosterOpen, setRosterOpen] = useState(false);
  const [error, setError] = useState(false);

  const loadSummary = () => fetchCoastGuardSummary(30).then(setSummary);
  useEffect(() => {
    Promise.all([
      loadSummary(),
      fetchCoastGuardDaily({ days: 90 }).then((d) => setDaily(d.rows || [])),
      fetchCoastGuardEncounters({ days: 30 }).then((d) => setEncounters(d.rows || [])),
      fetchCoastGuardEnforcement({ months: 240 }).then(setEnforcement),
    ]).catch(() => setError(true));
  }, []);

  useEffect(() => {
    const params = { months: range };
    if (group) params.group = group;
    fetchCoastGuardMonthly(params).then((d) => setMonthly(d.rows || [])).catch(() => setMonthly([]));
  }, [group, range]);

  // Pivot the three monthly inputs onto one month axis (zero-filled) so the
  // strips share x and the synced tooltip lines up.
  const paired = useMemo(() => {
    if (!monthly || !enforcement || !summary?.latest_date) return [];
    const latest = summary.latest_date.slice(0, 7);
    const start = addMonths(latest, -(range - 1));
    const floor = "2020-01";                       // backfill start
    const from = start < floor ? floor : start;
    const byMonth = {};
    for (let m = from; m <= latest; m = addMonths(m, 1)) byMonth[m] = { month: m, CCG: 0, CGA: 0, JCG: 0, expelled: null, detained: null };
    for (const r of monthly) if (byMonth[r.month]) byMonth[r.month][r.force] = r.hull_days;
    for (const r of enforcement.monthly || []) if (byMonth[r.period]) { byMonth[r.period].expelled = r.expelled; byMonth[r.period].detained = r.detained; }
    return Object.values(byMonth);
  }, [monthly, enforcement, summary, range]);

  const dailyPivot = useMemo(() => {
    if (!daily) return [];
    const m = {};
    for (const r of daily) { m[r.date] = m[r.date] || { date: r.date, CCG: 0, CGA: 0, JCG: 0 }; m[r.date][r.force] = r.hulls; }
    return Object.values(m).sort((a, b) => (a.date < b.date ? -1 : 1));
  }, [daily]);

  if (error) {
    return <p style={{ color: "var(--accent-red)", fontFamily: "var(--font-mono)", fontSize: "13px", padding: "20px 0" }}>Couldn't load coast guard data.</p>;
  }
  if (!summary) {
    return <p style={{ color: "var(--text-muted)", fontFamily: "var(--font-mono)", fontSize: "13px", padding: "20px 0" }}>Loading coast guard presence…</p>;
  }

  const force = (f) => summary.forces.find((x) => x.force === f) || {};
  const ccg = force("CCG"), cga = force("CGA");
  const enf = summary.enforcement;
  const groupMeta = GROUPS.find((g) => g.id === group);
  const showPre2023 = paired.length && paired[0].month < "2023-01";
  const caveatScopes = ["all", group === "kinmen" ? "kinmen" : null, showPre2023 ? "CCG" : null].filter(Boolean);
  const zones = summary.zones || [];

  return (
    <>
      <p style={{ fontFamily: "var(--font-body)", fontSize: "13px", color: "var(--text-secondary)", lineHeight: 1.55, margin: "0 0 14px" }}>
        Two series that describe the same water from opposite shores. <strong>Presence</strong> is where coast-guard hulls
        of four flags were seen on AIS inside Taiwan-drawn zones (Kinmen and Matsu prohibited/restricted waters, the
        median-line band, the 24 nm contiguous zone, Pratas, an east-coast box), from Global Fishing Watch's daily 1-km
        presence data. <strong>Enforcement</strong> is what Taiwan's Coast Guard Administration says it did — PRC fishing
        vessels expelled or detained for crossing the same lines. Neither is an incident count: presence is an
        AIS-visible floor, enforcement is a self-report. Read together they show pressure and response; read apart,
        each misleads.
      </p>
      <Caveats caveats={summary.caveats} scopes={["all"]} />

      {/* KPI strip — two per side, deliberately symmetric */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))", gap: "12px", marginTop: 14 }}>
        <KPICard label="China CG · 30 days" accent={FORCE_COLOUR.CCG} value={fmtInt(ccg.hull_days)}
                 sublabel={`hull-days · ${fmtInt(ccg.hulls)} hulls · ${deltaText(ccg.hull_days, ccg.prev_hull_days) || ""}`} />
        <KPICard label="Taiwan CG · 30 days" accent={FORCE_COLOUR.CGA} value={fmtInt(cga.hull_days)}
                 sublabel={`hull-days · ${fmtInt(cga.hulls)} hulls · ${deltaText(cga.hull_days, cga.prev_hull_days) || ""}`} />
        <KPICard label="PRC vessels expelled" accent={FORCE_COLOUR.CGA} value={enf ? fmtInt(enf.expelled) : "—"}
                 sublabel={enf ? `by the CGA, ${enf.months} reported months to ${fmtMonth(enf.latest_month)}` : "no CGA data"} />
        <KPICard label="PRC vessels detained" accent={FORCE_COLOUR.CGA} value={enf ? fmtInt(enf.detained) : "—"}
                 sublabel={enf ? "same window · CGA 表8-1" : "no CGA data"} />
      </div>

      {/* Paired monthly strips */}
      <SubHeader right={`AIS-visible to ${summary.latest_date}`}>Presence vs enforcement · monthly</SubHeader>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center", marginBottom: 10 }}>
        {GROUPS.map((g) => <Pill key={g.id} active={group === g.id} onClick={() => setGroup(g.id)}>{g.label}</Pill>)}
        <span style={{ width: 10 }} />
        {RANGES.map((r) => <Pill key={r.months} active={range === r.months} onClick={() => setRange(r.months)}>{r.label}</Pill>)}
      </div>
      {paired.length ? (
        <>
          <MonthlyStrip data={paired} dataKey="CCG" colour={FORCE_COLOUR.CCG} syncId="cg-paired" unit="hull-days"
                        title={`China Coast Guard hull-days · ${groupMeta.label}${groupMeta.zh ? ` ${groupMeta.zh}` : ""}`} />
          <MonthlyStrip data={paired} dataKey="CGA" colour={FORCE_COLOUR.CGA} syncId="cg-paired" unit="hull-days"
                        title={`Taiwan Coast Guard hull-days · ${groupMeta.label}${groupMeta.zh ? ` ${groupMeta.zh}` : ""}`} />
          <MonthlyStrip data={paired} dataKey="expelled" colour={FORCE_COLOUR.CGA} syncId="cg-paired" unit="expelled"
                        title="PRC fishing vessels expelled by the CGA · national, all waters (表8-1)" />
          <MonthlyStrip data={paired} dataKey="detained" colour={FORCE_COLOUR.CGA} syncId="cg-paired" unit="detained" height={90}
                        title="PRC fishing vessels detained by the CGA · national (表8-1)" />
        </>
      ) : (
        <div style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--text-muted)", padding: "12px 0" }}>Loading…</div>
      )}
      <Caveats caveats={summary.caveats} scopes={caveatScopes.filter((s) => s !== "all")} compact />

      {/* Dual-frame reading — both, always */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 12, marginTop: 12 }}>
        <div style={{ padding: "10px 12px", border: "1px solid var(--border-color)", borderLeft: `3px solid ${FORCE_COLOUR.CGA}`, background: "var(--bg-card)" }}>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: "9.5px", letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--text-muted)", marginBottom: 4 }}>Read from Taipei · 台北視角</div>
          <div style={{ fontFamily: "var(--font-body)", fontSize: "12px", color: "var(--text-secondary)", lineHeight: 1.5 }}>
            The zones are Taiwan's declared prohibited and restricted waters (MND 公告, 2004/2018). Any CCG hull inside them is an
            incursion into waters Taiwan administers; the CGA's expulsion count is routine law enforcement against trespass fishing.
          </div>
        </div>
        <div style={{ padding: "10px 12px", border: "1px solid var(--border-color)", borderLeft: `3px solid ${FORCE_COLOUR.CCG}`, background: "var(--bg-card)" }}>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: "9.5px", letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--text-muted)", marginBottom: 4 }}>Read from Beijing · 北京視角</div>
          <div style={{ fontFamily: "var(--font-body)", fontSize: "12px", color: "var(--text-secondary)", lineHeight: 1.5 }}>
            Beijing recognises no prohibited or restricted waters off Kinmen and Matsu (TAO, Feb 2024) and casts CCG patrols as
            law enforcement in Chinese waters; Taiwan's expulsions of mainland fishermen are the provocation, the patrols the response.
          </div>
        </div>
      </div>

      {/* Daily small multiples */}
      <SubHeader right="Last 90 days · all zones">Daily presence by flag</SubHeader>
      {CHART_FORCES.map((f) => <DailyStrip key={f} rows={dailyPivot} force={f} />)}
      <Caveats caveats={summary.caveats} scopes={["JCG", "CGA", "USCG"]} compact />

      {/* Map + zone table */}
      <SubHeader right={`${summary.window_start} → ${summary.latest_date}`}>Zones · 30-day window</SubHeader>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: 16, alignItems: "start" }}>
        <CoastGuardMap zoneStats={zones} />
        <ZoneTable zones={zones} />
      </div>

      {/* Co-presence + roster */}
      <SubHeader right={!READ_ONLY ? (
        <button onClick={() => setRosterOpen(true)} style={{ fontFamily: "var(--font-mono)", fontSize: "10px", cursor: "pointer", padding: "2px 8px",
                                                              background: "transparent", color: summary.anomalies ? "#b8860b" : "var(--text-secondary)",
                                                              border: `1px solid ${summary.anomalies ? "#b8860b" : "var(--border-color)"}` }}>
          ✎ Roster · {fmtInt(summary.anomalies)} anomalies
        </button>
      ) : "Last 30 days"}>Same-zone co-presence</SubHeader>
      <p style={{ fontFamily: "var(--font-body)", fontSize: "11.5px", color: "var(--text-secondary)", margin: "0 0 8px", lineHeight: 1.5 }}>
        A CCG hull and a Taiwanese or Japanese coast-guard hull inside the same zone on the same day. Daily 1-km data cannot
        show an intercept, so this is co-presence, not interaction.
      </p>
      <Encounters rows={encounters} />

      <p style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--text-muted)", marginTop: "16px", lineHeight: 1.5 }}>
        <strong style={{ color: "var(--text-secondary)" }}>Sources:</strong> Global Fishing Watch 4Wings presence
        (AIS, per hull per day per 1-km cell; coverage from {summary.coverage_start}, ~5-day lag) · coast-guard rosters resolved from
        GFW's identity index with MID / flag / name-change anomaly flags ({fmtInt(summary.roster?.CCG)} CCG, {fmtInt(summary.roster?.CGA)} CGA,
        {" "}{fmtInt(summary.roster?.JCG)} JCG identities) · Kinmen zone from the county gazette's official control points, Matsu from the
        MND 公告 bands · CGA 績效統計月報 / 海巡統計年報 表8-1 (national monthly), 表8-3 (county) and the 護永專案 summary.
        Map basemap: CartoDB Positron (&copy; OpenStreetMap contributors, &copy; CARTO).
      </p>

      {rosterOpen && <CoastGuardRosterModal onClose={() => setRosterOpen(false)} onChanged={loadSummary} />}
    </>
  );
}
