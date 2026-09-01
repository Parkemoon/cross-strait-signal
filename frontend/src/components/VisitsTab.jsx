import { useEffect, useMemo, useState } from "react";
import {
  Bar, BarChart, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend,
} from "recharts";
import { Copy } from "../copy";
import {
  fetchVisits, fetchVisitsSummary, fetchVisitsMonthly, fetchVisitCandidatesCount,
  dismissVisit, updateVisit, fetchKeyFigures,
} from "../api";
import VisitsMap from "./VisitsMap";
import VisitsReviewQueue, {
  DIRECTION_LABEL, DIR_COLOUR, AFFILIATION_LABEL, LEVEL_LABEL, TW_AFFILIATIONS, PRC_AFFILIATIONS,
  affiliationColour, VisitFieldsGrid, visitDraftFrom, isVisitDraftDirty, buildVisitPatch,
} from "./VisitsReviewQueue";
import { READ_ONLY } from "../readOnly";

const TICK = { fontFamily: "var(--font-mono)", fontSize: 10, fill: "var(--text-muted)" };
const TOOLTIP_STYLE = { background: "var(--bg-primary)", border: "1px solid var(--border-color)", fontFamily: "var(--font-mono)", fontSize: "11px" };
const RANGES = [{ label: "90d", days: 90 }, { label: "1Y", days: 365 }, { label: "All", days: 3650 }];
const STATUS_TONE = { planned: "var(--blue)", rumoured: "var(--muted)", cancelled: "var(--muted)", blocked: "var(--red)" };

function SectionHeader({ children, right }) {
  return (
    <div style={{ display: "flex", alignItems: "baseline", gap: "10px", marginBottom: "16px", marginTop: "28px" }}>
      <span style={{
        fontFamily: "var(--font-mono)",
        fontSize: "9.5px",
        fontWeight: 600,
        letterSpacing: "0.24em",
        textTransform: "uppercase",
        color: "var(--ink)",
        whiteSpace: "nowrap",
      }}>
        {children}
      </span>
      <span style={{ flex: 1, borderBottom: "1px solid var(--hair)" }} />
      {right && (
        <span style={{
          fontFamily: "var(--font-mono)",
          fontSize: "9px",
          color: "var(--pale)",
          letterSpacing: "0.08em",
          textAlign: "right",
        }}>
          {right}
        </span>
      )}
    </div>
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

function Pill({ active, onClick, children, colour }) {
  return (
    <button onClick={onClick}
            style={{ padding: "3px 10px", fontFamily: "var(--font-mono)", fontSize: "10px", letterSpacing: "0.06em",
                     border: `1px solid ${active ? (colour || "var(--text-primary)") : "var(--border-color)"}`,
                     background: active ? (colour ? `color-mix(in srgb, ${colour} 13%, transparent)` : "var(--bg-card)") : "transparent",
                     color: active ? "var(--text-primary)" : "var(--text-muted)", cursor: "pointer" }}>
      {children}
    </button>
  );
}

function Chip({ aff }) {
  if (!aff) return null;
  const c = affiliationColour(aff);
  return (
    <span style={{ fontFamily: "var(--font-mono)", fontSize: "9px", letterSpacing: "0.06em", textTransform: "uppercase",
                   color: c, border: `1px solid ${c}`, padding: "1px 5px", whiteSpace: "nowrap" }}>
      {AFFILIATION_LABEL[aff] || aff}
    </span>
  );
}

function delta(cur, prev) {
  if (!prev) return cur ? "new this window" : "—";
  const d = cur - prev;
  return `${d >= 0 ? "+" : ""}${d} vs prior window`;
}

function fmtMonth(m) { return m ? `${m.slice(5, 7)}/${m.slice(2, 4)}` : ""; }

// TW state bodies get the hollow marker (state, not party) — same rule as
// the feed's alignment legend. Everything else with an affiliation is filled.
const HOLLOW_AFFILIATIONS = new Set(["TW_GOV", "SEF", "TW_LEGISLATURE", "TW_LOCAL"]);

function VisitAvatar({ v, portraitFor }) {
  const colour = affiliationColour(v.visitor_affiliation) || "var(--muted)";
  const fig = portraitFor?.(v.visitor_figure_id) || portraitFor?.(v.counterpart_figure_id);
  if (fig?.portrait) {
    return (
      <img src={`/figures/${fig.portrait}`} alt={fig.name_en}
           style={{ width: "44px", height: "44px", borderRadius: "50%", objectFit: "cover",
                    objectPosition: "center top", flexShrink: 0 }} />
    );
  }
  const en = v.visitor_name_en || "";
  const initials = en
    ? en.split(" ").slice(0, 2).map((w) => w[0]).join("")
    : (v.visitor_name_zh || "·").slice(0, 1);
  return (
    <div style={{ width: "44px", height: "44px", borderRadius: "50%", flexShrink: 0,
                  background: "color-mix(in srgb, " + colour + " 16%, transparent)",
                  border: `1px solid ${colour}`,
                  display: "flex", alignItems: "center", justifyContent: "center" }}>
      <span style={{ color: colour, fontSize: "13px", fontWeight: 600, fontFamily: "var(--font-mono)" }}>
        {initials}
      </span>
    </div>
  );
}

// Labelled detail row — the review queue's clarity, public-facing.
function VisitField({ label, children }) {
  if (!children) return null;
  return (
    <div style={{ display: "flex", gap: "10px", alignItems: "baseline", marginTop: "3px" }}>
      <span style={{ fontFamily: "var(--font-mono)", fontSize: "8px", letterSpacing: "0.12em",
                     color: "var(--faint)", textTransform: "uppercase", width: "74px", flexShrink: 0 }}>
        {label}
      </span>
      <span style={{ fontFamily: "var(--font-body)", fontSize: "12px", color: "var(--body)",
                     lineHeight: 1.5, minWidth: 0 }}>
        {children}
      </span>
    </div>
  );
}

function VisitCard({ v, admin, onEdit, onDismiss, portraitFor }) {
  const who = v.visitor_name_en || v.visitor_name_zh || v.delegation_desc_en || "Unnamed delegation";
  const whoZh = v.visitor_name_en && v.visitor_name_zh ? v.visitor_name_zh : null;
  const met = v.counterpart_name_en || v.counterpart_name_zh;
  const metZh = v.counterpart_name_en && v.counterpart_name_zh ? v.counterpart_name_zh : null;
  const dates = v.start_date
    ? (v.end_date && v.end_date !== v.start_date ? `${v.start_date} → ${v.end_date}` : v.start_date)
    : `~${v.effective_date}`;
  const statusColour = STATUS_TONE[v.visit_status] || "var(--faint)";
  const aff = v.visitor_affiliation;
  const affColour = affiliationColour(aff) || "var(--muted)";
  const marker = HOLLOW_AFFILIATIONS.has(aff) ? "□" : "■";

  return (
    <div style={{ display: "grid", gridTemplateColumns: "88px 44px 1fr", gap: "14px",
                  padding: "16px 0", borderBottom: "1px solid var(--soft)", alignItems: "start" }}>
      {/* Date + status + level */}
      <div>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: "10px", fontWeight: 600,
                      letterSpacing: "0.06em", color: "var(--ink)" }}>{dates}</div>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: "8.5px", letterSpacing: "0.1em",
                      color: statusColour, marginTop: "3px", textTransform: "uppercase" }}>
          {v.visit_status}
        </div>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: "8.5px", letterSpacing: "0.08em",
                      color: "var(--pale)", marginTop: "3px", textTransform: "uppercase" }}>
          {LEVEL_LABEL[v.visit_level] || v.visit_level}
        </div>
      </div>

      <VisitAvatar v={v} portraitFor={portraitFor} />

      {/* Who, what, where — every field labelled */}
      <div style={{ borderLeft: `2px solid ${affColour}`, paddingLeft: "14px", minWidth: 0 }}>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: "8.5px", letterSpacing: "0.1em",
                      color: affColour, fontWeight: 700, marginBottom: "4px", textTransform: "uppercase" }}>
          {marker} {AFFILIATION_LABEL[aff] || aff || "Unattributed"} · {DIRECTION_LABEL[v.direction]}
        </div>
        <div style={{ fontFamily: "var(--font-headline)", fontSize: "17px", fontWeight: 500,
                      lineHeight: 1.35, color: "var(--ink)", marginBottom: "2px" }}>
          {who}{whoZh ? <span style={{ color: "var(--pale)", fontSize: "13px" }}> {whoZh}</span> : null}
          {met ? <span style={{ fontWeight: 400 }}> met {met}</span> : null}
          {met && metZh ? <span style={{ color: "var(--pale)", fontSize: "13px" }}> {metZh}</span> : null}
        </div>
        <VisitField label="Visitor">
          {v.visitor_title || null}
        </VisitField>
        <VisitField label="Met with">
          {met ? [v.counterpart_title,
                  v.counterpart_affiliation && (AFFILIATION_LABEL[v.counterpart_affiliation] || v.counterpart_affiliation)]
                  .filter(Boolean).join(" · ") || null : null}
        </VisitField>
        <VisitField label="Event">
          {v.event_name_en ? <>{v.event_name_en}{v.event_name_zh ? <span style={{ color: "var(--pale)" }}> {v.event_name_zh}</span> : null}</> : null}
        </VisitField>
        <VisitField label="Place">{v.location_label || null}</VisitField>
        <VisitField label="Delegation">{v.delegation_desc_en || null}</VisitField>
        <VisitField label="Purpose">{v.purpose_en || null}</VisitField>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center",
                      gap: "8px", flexWrap: "wrap", marginTop: "7px" }}>
          <a href={v.article?.url} target="_blank" rel="noreferrer"
             style={{ fontFamily: "var(--font-mono)", fontSize: "8.5px", letterSpacing: "0.08em",
                      color: "var(--pale)", textDecoration: "none", borderBottom: "1px solid var(--dot)",
                      textTransform: "uppercase" }}>
            Reported by {v.article?.source_name} · {v.article?.published_at?.slice(0, 10)}
          </a>
          {admin && (
            <span style={{ display: "flex", gap: "6px" }}>
              <button onClick={() => onEdit(v)} style={{ fontFamily: "var(--font-mono)", fontSize: "9.5px", padding: "2px 7px", cursor: "pointer",
                      background: "transparent", border: "1px solid var(--border-color)", color: "var(--text-secondary)" }}>✎ edit</button>
              <button onClick={() => onDismiss(v)} style={{ fontFamily: "var(--font-mono)", fontSize: "9.5px", padding: "2px 7px", cursor: "pointer",
                      background: "transparent", border: "1px solid var(--border-color)", color: "var(--text-muted)" }}>dismiss</button>
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

function EditModal({ visit, onClose, onSaved }) {
  const [draft, setDraft] = useState(() => visitDraftFrom(visit));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const dirty = isVisitDraftDirty(draft, visit);
  const save = async () => {
    setBusy(true); setError(null);
    try {
      const patch = buildVisitPatch(draft, visit);
      if (Object.keys(patch).length) await updateVisit(visit.id, patch);
      onSaved();
    } catch (e) { setError(e.message || String(e)); setBusy(false); }
  };
  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.55)", zIndex: 1000,
                                    display: "flex", alignItems: "flex-start", justifyContent: "center", padding: "40px 16px", overflowY: "auto" }}>
      <div onClick={(e) => e.stopPropagation()} style={{ background: "var(--bg-card)", border: "1px solid var(--border-color)", width: "min(900px, 100%)", padding: "14px 16px" }}>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: "11px", fontWeight: 600, letterSpacing: "0.14em", textTransform: "uppercase", marginBottom: "10px" }}>
          Edit visit #{visit.id}
        </div>
        <VisitFieldsGrid draft={draft} setDraft={setDraft} />
        {error && <div style={{ color: "var(--accent-red)", fontFamily: "var(--font-mono)", fontSize: "10px" }}>{error}</div>}
        <div style={{ display: "flex", gap: "6px", marginTop: "8px" }}>
          <button disabled={busy || !dirty} onClick={save} style={{ padding: "5px 12px", fontFamily: "var(--font-mono)", fontSize: "10px",
                  textTransform: "uppercase", background: "var(--green)", color: "#fff", border: "none", cursor: "pointer", opacity: dirty ? 1 : 0.5 }}>Save</button>
          <button onClick={onClose} style={{ padding: "5px 12px", fontFamily: "var(--font-mono)", fontSize: "10px", textTransform: "uppercase",
                  background: "transparent", color: "var(--text-secondary)", border: "1px solid var(--border-color)", cursor: "pointer" }}>Cancel</button>
        </div>
      </div>
    </div>
  );
}

export default function VisitsTab() {
  const [summary, setSummary] = useState(null);
  const [monthly, setMonthly] = useState(null);
  const [visits, setVisits] = useState(null);
  const [error, setError] = useState(false);
  const [range, setRange] = useState(365);
  const [direction, setDirection] = useState("");
  const [affiliation, setAffiliation] = useState("");
  const [reviewOpen, setReviewOpen] = useState(false);
  const [pendingCount, setPendingCount] = useState(0);
  const [editing, setEditing] = useState(null);
  const [nonce, setNonce] = useState(0);
  // Key-figure portraits for the visit avatars — one fetch, id-keyed map.
  // Most visitors are long-tail officials with no portrait; they get the
  // initials medallion in their affiliation colour instead.
  const [figureMap, setFigureMap] = useState({});
  useEffect(() => {
    fetchKeyFigures().then((d) => {
      const m = {};
      for (const f of d.figures || []) m[f.id] = { portrait: f.portrait, name_en: f.name_en };
      setFigureMap(m);
    }).catch(() => {});
  }, []);
  const portraitFor = (figId) => (figId != null ? figureMap[figId] : undefined);

  const loadPendingCount = () => {
    if (READ_ONLY) return;
    fetchVisitCandidatesCount().then((r) => setPendingCount(r.pending || 0)).catch(() => setPendingCount(0));
  };

  useEffect(() => {
    Promise.all([fetchVisitsSummary({ days: 90 }), fetchVisitsMonthly({ months: 24 })])
      .then(([s, m]) => { setSummary(s); setMonthly(m.rows || []); })
      .catch(() => setError(true));
    loadPendingCount();
  }, [nonce]);

  useEffect(() => {
    const params = { days: range, limit: 1000 };
    if (direction) params.direction = direction;
    if (affiliation) params.affiliation = affiliation;
    fetchVisits(params).then((d) => setVisits(d.visits || [])).catch(() => setVisits([]));
  }, [range, direction, affiliation, nonce]);

  // Pivot monthly rows onto one axis: one bar per direction + a blocked bar.
  const chart = useMemo(() => {
    if (!monthly) return [];
    const by = {};
    for (const r of monthly) {
      by[r.month] = by[r.month] || { month: r.month, TW_TO_PRC: 0, PRC_TO_TW: 0, THIRD_VENUE: 0, blocked: 0 };
      by[r.month][r.direction] += r.n;
      by[r.month].blocked += r.n_blocked;
    }
    return Object.values(by).sort((a, b) => (a.month < b.month ? -1 : 1));
  }, [monthly]);

  // Group the list by month for the timeline.
  const grouped = useMemo(() => {
    if (!visits) return [];
    const out = [];
    let cur = null;
    for (const v of visits) {
      const m = (v.effective_date || "").slice(0, 7);
      if (!cur || cur.month !== m) { cur = { month: m, items: [] }; out.push(cur); }
      cur.items.push(v);
    }
    return out;
  }, [visits]);

  // Affiliations present in the loaded list — drive the filter pills so the
  // row doesn't show 19 empty options.
  const affsPresent = useMemo(() => {
    const s = new Set((visits || []).map((v) => v.visitor_affiliation));
    return [...TW_AFFILIATIONS, ...PRC_AFFILIATIONS].filter((a) => s.has(a) || a === affiliation);
  }, [visits, affiliation]);

  const onDismiss = async (v) => {
    if (!window.confirm(`Dismiss visit #${v.id} (${v.visitor_name_en || v.visitor_name_zh})? It leaves the public list.`)) return;
    try { await dismissVisit(v.id); setNonce((n) => n + 1); } catch (e) { window.alert(e.message || String(e)); }
  };

  if (error) return <p style={{ color: "var(--accent-red)", fontFamily: "var(--font-mono)", fontSize: "13px", padding: "28px 32px" }}>Couldn't load the visits tracker.</p>;
  if (!summary) return <p style={{ color: "var(--text-muted)", fontFamily: "var(--font-mono)", fontSize: "13px", padding: "28px 32px" }}>Loading cross-strait visits…</p>;

  const cur = summary.current, prev = summary.previous;
  const d = (k) => cur.by_direction[k] || 0, pd = (k) => prev.by_direction[k] || 0;
  const blockedNow = (cur.by_status.blocked || 0) + (cur.by_status.cancelled || 0);
  const blockedPrev = (prev.by_status.blocked || 0) + (prev.by_status.cancelled || 0);
  const cov = summary.coverage;

  return (
    <main style={{ padding: "28px 32px", minWidth: 0 }}>
      <SectionHeader right={cov?.n ? `${cov.n} visits · ${cov.first} → ${cov.last}` : "no approved visits yet"}>
        Cross-Strait Visits
      </SectionHeader>

      <Copy k="visits.intro"
            style={{ fontFamily: "var(--font-body)", fontSize: "13px", color: "var(--text-secondary)", lineHeight: 1.55, margin: "0 0 18px", maxWidth: "820px" }}
            fallback={"Publicly reported visits, meetings and exchanges between official- or party-level actors from Taiwan and from the mainland, Hong Kong or Macao — in both directions. Cross-strait only: Taiwan's dealings with third countries live on the Diplomacy map. Every entry is drawn from a news article and reviewed by an analyst before it appears; visits that were announced, rumoured, cancelled or refused entry are kept and labelled, because a blocked delegation is a signal in its own right."} />

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))", gap: "12px" }}>
        <KPICard label="Taiwan → mainland" value={d("TW_TO_PRC")} accent={DIR_COLOUR.TW_TO_PRC} sublabel={`${delta(d("TW_TO_PRC"), pd("TW_TO_PRC"))} · 90d`} />
        <KPICard label="Mainland → Taiwan" value={d("PRC_TO_TW")} accent={DIR_COLOUR.PRC_TO_TW} sublabel={`${delta(d("PRC_TO_TW"), pd("PRC_TO_TW"))} · 90d`} />
        <KPICard label="Third venue" value={d("THIRD_VENUE")} accent={DIR_COLOUR.THIRD_VENUE} sublabel="both sides meet elsewhere" />
        <KPICard label="Blocked / cancelled" value={blockedNow} accent={STATUS_TONE.blocked} sublabel={`${delta(blockedNow, blockedPrev)} · 90d`} />
      </div>

      <SectionHeader right="approved visits per month, by direction">Monthly Volume</SectionHeader>
      <div style={{ height: "200px", border: "1px solid var(--border-color)", background: "var(--bg-card)", padding: "8px 8px 0" }}>
        {chart.length === 0 ? (
          <p style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--text-muted)", padding: "12px" }}>No approved visits yet.</p>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chart} margin={{ top: 4, right: 12, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="2 4" stroke="var(--border-color)" vertical={false} />
              <XAxis dataKey="month" tick={TICK} stroke="var(--border-color)" tickFormatter={fmtMonth} interval="preserveStartEnd" minTickGap={36} />
              <YAxis tick={TICK} stroke="var(--border-color)" width={30} allowDecimals={false} />
              <Tooltip contentStyle={TOOLTIP_STYLE} labelFormatter={fmtMonth} />
              <Legend wrapperStyle={{ fontFamily: "var(--font-mono)", fontSize: "10px" }} />
              <Bar dataKey="TW_TO_PRC" name="TW → PRC" stackId="v" fill={DIR_COLOUR.TW_TO_PRC} maxBarSize={18} />
              <Bar dataKey="PRC_TO_TW" name="PRC → TW" stackId="v" fill={DIR_COLOUR.PRC_TO_TW} maxBarSize={18} />
              <Bar dataKey="THIRD_VENUE" name="third venue" stackId="v" fill={DIR_COLOUR.THIRD_VENUE} maxBarSize={18} />
              <Bar dataKey="blocked" name="blocked / cancelled" stackId="v" fill={DIR_COLOUR.blocked} maxBarSize={18} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>

      {summary.frequent_visitors?.length > 0 && (
        <>
          <SectionHeader right="last 12 months">Frequent Travellers</SectionHeader>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: "8px" }}>
            {summary.frequent_visitors.map((f) => (
              <div key={`${f.key}-${f.affiliation}`} style={{ padding: "8px 10px", border: "1px solid var(--border-color)", background: "var(--bg-card)",
                                                                display: "flex", justifyContent: "space-between", alignItems: "center", gap: "8px" }}>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontFamily: "var(--font-body)", fontSize: "12.5px", color: "var(--text-primary)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                    {f.name_en || f.name_zh}
                  </div>
                  <div style={{ marginTop: "3px" }}><Chip aff={f.affiliation} /></div>
                </div>
                <div style={{ fontFamily: "var(--font-display)", fontSize: "20px", color: "var(--text-primary)" }}>{f.n}</div>
              </div>
            ))}
          </div>
        </>
      )}

      <SectionHeader right={visits ? `${visits.length} shown` : ""}>Map & Timeline</SectionHeader>
      <div style={{ display: "flex", gap: "6px", flexWrap: "wrap", alignItems: "center", marginBottom: "12px" }}>
        {RANGES.map((r) => <Pill key={r.days} active={range === r.days} onClick={() => setRange(r.days)}>{r.label}</Pill>)}
        <span style={{ width: "10px" }} />
        <Pill active={!direction} onClick={() => setDirection("")}>all</Pill>
        {Object.entries(DIRECTION_LABEL).map(([k, l]) => (
          <Pill key={k} active={direction === k} colour={DIR_COLOUR[k]} onClick={() => setDirection(direction === k ? "" : k)}>{l}</Pill>
        ))}
        <span style={{ width: "10px" }} />
        {affsPresent.map((a) => (
          <Pill key={a} active={affiliation === a} colour={affiliationColour(a)} onClick={() => setAffiliation(affiliation === a ? "" : a)}>
            {AFFILIATION_LABEL[a] || a}
          </Pill>
        ))}
        <span style={{ flex: 1 }} />
        {!READ_ONLY && (
          <button onClick={() => setReviewOpen(true)} title={`${pendingCount} visits pending review`}
                  style={{ padding: "4px 11px", fontFamily: "var(--font-mono)", fontSize: "10px", letterSpacing: "0.06em",
                           border: `1px solid ${pendingCount > 0 ? "var(--flag)" : "var(--border-color)"}`,
                           background: pendingCount > 0 ? "color-mix(in srgb, var(--flag) 12%, transparent)" : "transparent",
                           color: pendingCount > 0 ? "var(--flag)" : "var(--text-muted)", cursor: "pointer" }}>
            ✎ Review{pendingCount > 0 ? ` (${pendingCount})` : ""}
          </button>
        )}
      </div>

      <VisitsMap visits={visits || []} />

      {visits && visits.length === 0 && (
        <p style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--text-muted)" }}>No approved visits in this window.</p>
      )}
      {grouped.map((g) => (
        <div key={g.month} style={{ marginBottom: "18px" }}>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: "10px", letterSpacing: "0.1em", color: "var(--text-muted)", margin: "0 0 8px" }}>
            {g.month} · {g.items.length}
          </div>
          <div style={{ display: "grid", gap: "8px" }}>
            {g.items.map((v) => <VisitCard key={v.id} v={v} admin={!READ_ONLY} onEdit={setEditing} onDismiss={onDismiss} portraitFor={portraitFor} />)}
          </div>
        </div>
      ))}

      {reviewOpen && (
        <VisitsReviewQueue onClose={() => { setReviewOpen(false); setNonce((n) => n + 1); }} onResolveAll={loadPendingCount} />
      )}
      {editing && <EditModal visit={editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); setNonce((n) => n + 1); }} />}
    </main>
  );
}
