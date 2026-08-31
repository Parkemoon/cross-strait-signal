import { useEffect, useState } from "react";
import {
  fetchVisitCandidates,
  approveVisit,
  dismissVisit,
  mergeVisit,
  updateVisit,
} from "../api";
import { PARTY_COLOURS } from "../partyColours";

// Enums mirror scraper/processors/visits_extract.py + api/routes/visits.py.
export const DIRECTIONS = ["TW_TO_PRC", "PRC_TO_TW", "THIRD_VENUE"];
export const DIRECTION_LABEL = { TW_TO_PRC: "TW → PRC", PRC_TO_TW: "PRC → TW", THIRD_VENUE: "third venue" };
// Direction colours (shared by the tab chart, timeline cards and map).
// Not party colours (direction is not a party) and not the sentiment
// purple/amber pair — two neutral tones that stay apart in both themes.
export const DIR_COLOUR = { TW_TO_PRC: "#0e7490", PRC_TO_TW: "#b45309", THIRD_VENUE: "#64748b", blocked: "#9ca3af" };
export const STATUSES = ["reported", "planned", "rumoured", "cancelled", "blocked"];
export const LEVELS = [
  "head_of_state_govt", "party_leader", "party_senior", "minister", "legislator",
  "local_executive", "local_official", "youth_delegation", "delegation", "other",
];
export const LEVEL_LABEL = {
  head_of_state_govt: "Head of state / govt", party_leader: "Party leader", party_senior: "Party senior",
  minister: "Minister", legislator: "Legislator", local_executive: "Local executive",
  local_official: "Local official", youth_delegation: "Youth delegation", delegation: "Delegation", other: "Other",
};
export const TW_AFFILIATIONS = ["DPP", "KMT", "TPP", "NPP", "PFP", "NP", "TW_OTHER_PARTY", "TW_GOV", "SEF", "TW_LEGISLATURE", "TW_LOCAL", "TW_IND"];
export const PRC_AFFILIATIONS = ["CCP", "TAO", "ARATS", "PRC_GOV", "PRC_LOCAL", "HKMO_GOV", "PRC_OTHER"];
export const AFFILIATION_LABEL = {
  DPP: "DPP", KMT: "KMT", TPP: "TPP", NPP: "NPP", PFP: "PFP", NP: "New Party",
  TW_OTHER_PARTY: "Other TW party", TW_GOV: "TW government", SEF: "SEF",
  TW_LEGISLATURE: "Legislative Yuan", TW_LOCAL: "TW local govt", TW_IND: "Independent (TW)",
  CCP: "CCP", TAO: "TAO", ARATS: "ARATS", PRC_GOV: "PRC government", PRC_LOCAL: "PRC local govt",
  HKMO_GOV: "HK / Macao govt", PRC_OTHER: "Other PRC",
};

// Chip colour: a party gets its canonical colour; TW non-party = slate; PRC
// side = PRC red (the bias-palette red, deliberately — it's the PRC side).
export function affiliationColour(aff) {
  if (PARTY_COLOURS[aff]) return PARTY_COLOURS[aff];
  if (PRC_AFFILIATIONS.includes(aff)) return PARTY_COLOURS.PRC;
  return "#475569";
}

function fieldStyle() {
  return {
    fontFamily: "var(--font-mono)", fontSize: "11px", padding: "4px 6px",
    border: "1px solid var(--border-color)", background: "var(--bg-primary)",
    color: "var(--text-primary)", width: "100%", boxSizing: "border-box",
  };
}
function labelStyle() {
  return {
    fontFamily: "var(--font-mono)", fontSize: "9.5px", letterSpacing: "0.06em",
    textTransform: "uppercase", color: "var(--text-muted)", marginBottom: "2px", display: "block",
  };
}

const EDITABLE = [
  "direction", "visit_status", "visitor_name_en", "visitor_name_zh", "visitor_title",
  "visitor_affiliation", "visit_level", "delegation_desc_en", "counterpart_name_en",
  "counterpart_name_zh", "counterpart_title", "counterpart_affiliation", "event_name_en",
  "event_name_zh", "location_label", "start_date", "end_date", "purpose_en",
];

export function visitDraftFrom(row) {
  const d = {};
  for (const k of EDITABLE) d[k] = row[k] || "";
  return d;
}
export function isVisitDraftDirty(draft, row) {
  return EDITABLE.some((k) => (draft[k] || "") !== (row[k] || ""));
}
export function buildVisitPatch(draft, row) {
  const p = {};
  for (const k of EDITABLE) if ((draft[k] || "") !== (row[k] || "")) p[k] = draft[k];
  return p;
}

function Field({ label, children, span }) {
  return (
    <div style={span ? { gridColumn: `span ${span}` } : undefined}>
      <label style={labelStyle()}>{label}</label>
      {children}
    </div>
  );
}

export function VisitFieldsGrid({ draft, setDraft }) {
  const set = (k) => (e) => setDraft({ ...draft, [k]: e.target.value });
  const sel = (k, opts, labels) => (
    <select style={fieldStyle()} value={draft[k]} onChange={set(k)}>
      {k === "counterpart_affiliation" && <option value="">—</option>}
      {opts.map((o) => <option key={o} value={o}>{labels ? labels[o] || o : o}</option>)}
    </select>
  );
  const inp = (k) => <input style={fieldStyle()} value={draft[k]} onChange={set(k)} />;
  const allAff = [...TW_AFFILIATIONS, ...PRC_AFFILIATIONS];
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(0, 1fr))", gap: "6px 10px", marginBottom: "6px" }}>
      <Field label="Direction">{sel("direction", DIRECTIONS, DIRECTION_LABEL)}</Field>
      <Field label="Status">{sel("visit_status", STATUSES)}</Field>
      <Field label="Level">{sel("visit_level", LEVELS, LEVEL_LABEL)}</Field>
      <Field label="Location">{inp("location_label")}</Field>

      <Field label="Visitor (EN)">{inp("visitor_name_en")}</Field>
      <Field label="Visitor (ZH)">{inp("visitor_name_zh")}</Field>
      <Field label="Visitor title">{inp("visitor_title")}</Field>
      <Field label="Visitor affiliation">{sel("visitor_affiliation", allAff, AFFILIATION_LABEL)}</Field>

      <Field label="Counterpart (EN)">{inp("counterpart_name_en")}</Field>
      <Field label="Counterpart (ZH)">{inp("counterpart_name_zh")}</Field>
      <Field label="Counterpart title">{inp("counterpart_title")}</Field>
      <Field label="Counterpart affiliation">{sel("counterpart_affiliation", allAff, AFFILIATION_LABEL)}</Field>

      <Field label="Event (EN)">{inp("event_name_en")}</Field>
      <Field label="Event (ZH)">{inp("event_name_zh")}</Field>
      <Field label="Start"><input type="date" style={fieldStyle()} value={draft.start_date} onChange={set("start_date")} /></Field>
      <Field label="End"><input type="date" style={fieldStyle()} value={draft.end_date} onChange={set("end_date")} /></Field>

      <Field label="Delegation" span={4}>{inp("delegation_desc_en")}</Field>
      <Field label="Purpose (English)" span={4}>
        <textarea style={{ ...fieldStyle(), minHeight: "40px", fontFamily: "var(--font-body)" }}
                  value={draft.purpose_en} onChange={set("purpose_en")} />
      </Field>
    </div>
  );
}

function CandidateCard({ candidate, targets, onResolve }) {
  const [draft, setDraft] = useState(() => visitDraftFrom(candidate));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [mergeTarget, setMergeTarget] = useState("");
  const dirty = isVisitDraftDirty(draft, candidate);

  const act = async (action) => {
    setBusy(true); setError(null);
    try {
      if (action === "approve") {
        if (dirty) {
          const patch = buildVisitPatch(draft, candidate);
          if (Object.keys(patch).length) await updateVisit(candidate.id, patch);
        }
        await approveVisit(candidate.id);
      } else if (action === "merge") {
        if (!mergeTarget) throw new Error("pick a merge target");
        await mergeVisit(candidate.id, Number(mergeTarget));
      } else {
        await dismissVisit(candidate.id);
      }
      onResolve(candidate.id);
    } catch (e) {
      setError(e.message || String(e));
      setBusy(false);
    }
  };

  // Merge targets: same direction, within ±21 days of this candidate — the
  // typical "five articles on one trip" spread.
  const eff = candidate.effective_date || "";
  const near = (targets || []).filter((t) => t.direction === candidate.direction
    && Math.abs((new Date(t.effective_date) - new Date(eff)) / 86400000) <= 21);

  const btn = (label, action, style) => (
    <button disabled={busy} onClick={() => act(action)}
            style={{ padding: "5px 12px", fontFamily: "var(--font-mono)", fontSize: "10px",
                     letterSpacing: "0.08em", textTransform: "uppercase", cursor: "pointer", ...style }}>
      {label}
    </button>
  );

  return (
    <div style={{ padding: "12px 14px", borderBottom: "1px solid var(--border-color)", opacity: busy ? 0.55 : 1 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline",
                    fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--text-muted)", marginBottom: "6px", gap: "8px" }}>
        <a href={candidate.article?.url} target="_blank" rel="noreferrer"
           style={{ color: "var(--text-secondary)", textDecoration: "underline" }}>
          {candidate.article?.source_name} · {candidate.article?.source_bias}
        </a>
        <span>{candidate.article?.published_at?.slice(0, 10)} · conf {Number(candidate.confidence || 0).toFixed(2)}</span>
      </div>
      <div style={{ fontFamily: "var(--font-body)", fontSize: "12px", color: "var(--text-primary)", marginBottom: "6px" }}>
        {candidate.article?.title_en || candidate.article?.title_original}
      </div>
      {candidate.quote_zh && (
        <p style={{ fontFamily: "var(--font-body)", fontSize: "12px", color: "var(--text-secondary)",
                    lineHeight: 1.5, margin: "0 0 8px", fontStyle: "italic" }}>
          {candidate.quote_zh}
        </p>
      )}

      <VisitFieldsGrid draft={draft} setDraft={setDraft} />

      {error && (
        <div style={{ color: "var(--accent-red)", fontFamily: "var(--font-mono)", fontSize: "10px", marginBottom: "4px" }}>{error}</div>
      )}

      <div style={{ display: "flex", gap: "6px", alignItems: "center", marginTop: "8px", flexWrap: "wrap" }}>
        {btn(dirty ? "Save & approve" : "Approve", "approve", { background: "#16a34a", color: "#fff", border: "none" })}
        {btn("Dismiss", "dismiss", { background: "transparent", color: "var(--text-secondary)", border: "1px solid var(--border-color)" })}
        {near.length > 0 && (
          <>
            <select style={{ ...fieldStyle(), width: "auto", maxWidth: "360px" }} value={mergeTarget}
                    onChange={(e) => setMergeTarget(e.target.value)}>
              <option value="">merge into approved visit…</option>
              {near.map((t) => (
                <option key={t.id} value={t.id}>
                  #{t.id} {t.effective_date} {t.visitor_name_en || t.visitor_name_zh} ({t.visitor_affiliation}) {t.event_name_en || t.location_label || ""}
                </option>
              ))}
            </select>
            {mergeTarget && btn("Merge", "merge", { background: "#b8860b", color: "#fff", border: "none" })}
          </>
        )}
      </div>
    </div>
  );
}

export default function VisitsReviewQueue({ onClose, onResolveAll }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchVisitCandidates().then(setData).catch((e) => setError(e.message || String(e)));
  }, []);

  const resolve = (id) => {
    setData((d) => d ? { ...d, candidates: d.candidates.filter((c) => c.id !== id), total: d.total - 1 } : d);
    onResolveAll?.();
  };

  return (
    <div onClick={onClose}
         style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.55)", zIndex: 1000,
                  display: "flex", alignItems: "flex-start", justifyContent: "center", padding: "40px 16px", overflowY: "auto" }}>
      <div onClick={(e) => e.stopPropagation()}
           style={{ background: "var(--bg-card)", border: "1px solid var(--border-color)", width: "min(1040px, 100%)",
                    maxHeight: "calc(100vh - 80px)", overflowY: "auto" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center",
                      padding: "12px 16px", borderBottom: "2px solid var(--border-color)", position: "sticky", top: 0,
                      background: "var(--bg-card)", zIndex: 1 }}>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: "11px", fontWeight: 600, letterSpacing: "0.14em",
                         textTransform: "uppercase", color: "var(--text-primary)" }}>
            Visit candidates{data ? ` · ${data.total} pending` : ""}
          </span>
          <button onClick={onClose}
                  style={{ background: "transparent", border: "1px solid var(--border-color)", color: "var(--text-secondary)",
                           fontFamily: "var(--font-mono)", fontSize: "10px", padding: "3px 9px", cursor: "pointer" }}>
            Close
          </button>
        </div>
        {error && <p style={{ padding: "16px", color: "var(--accent-red)", fontFamily: "var(--font-mono)", fontSize: "11px" }}>{error}</p>}
        {!data && !error && <p style={{ padding: "16px", fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--text-muted)" }}>Loading…</p>}
        {data && data.candidates.length === 0 && (
          <p style={{ padding: "16px", fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--text-muted)" }}>Queue is empty.</p>
        )}
        {data && data.candidates.map((c) => (
          <CandidateCard key={c.id} candidate={c} targets={data.merge_targets} onResolve={resolve} />
        ))}
      </div>
    </div>
  );
}
