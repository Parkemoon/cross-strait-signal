import { useEffect, useMemo, useState } from "react";
import {
  fetchDiplomacyCandidates,
  approveDiplomacyStatement,
  dismissDiplomacyStatement,
  updateDiplomacyStatement,
} from "../api";
import { BAND_COLOUR, BAND_LABEL, TIER_LABEL } from "./DiplomacyMap";

// Ordered tier list for the edit dropdown — keys mirror TIER_LABEL.
const AUTHORITY_TIERS = [
  "government", "head_of_state", "ruling_party", "legislator",
  "subnational", "former_official", "other",
];
const SOURCE_SIDES = ["TW", "PRC", "INTL"];

// Mirror of _stance_label (ai_pipeline.py / diplomacy.py) for the live band
// preview as the analyst drags the stance — keep thresholds in sync.
function stanceBand(v) {
  const n = Number(v);
  if (Number.isNaN(n)) return "neutral";
  if (n >= 0.6) return "pro_taipei";
  if (n >= 0.2) return "leaning_taipei";
  if (n > -0.2) return "neutral";
  if (n > -0.6) return "leaning_beijing";
  return "pro_beijing";
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

// Editable draft shape — mirrors StatementPatch in api/routes/diplomacy.py.
// Empty string = the form's "absent" sentinel; the PATCH path normalises back.
// Exported (with isDiplomacyDraftDirty / buildDiplomacyPatch / DiplomacyFieldsGrid)
// so DiplomacyEditModal can reuse the exact same edit UI on approved rows —
// the same lockstep ExerciseReviewQueue keeps with ExerciseEditModal.
export function diplomacyDraftFrom(row) {
  return {
    country_iso:    row.country_iso || "",
    country_name:   row.country_name || "",
    speaker:        row.speaker || "",
    authority_tier: row.authority_tier || "other",
    stance:         row.stance ?? "",
    statement_en:   row.statement_en || "",
    stated_date:    row.stated_date || "",
    source_side:    row.source_side || "INTL",
  };
}

function fieldChanged(k, v, row) {
  if (k === "stance") {
    const orig = row.stance ?? "";
    return String(v) !== String(orig);
  }
  return (v || "") !== (row[k] || "");
}

export function isDiplomacyDraftDirty(draft, row) {
  return Object.entries(draft).some(([k, v]) => fieldChanged(k, v, row));
}

// Minimal PATCH body — only changed fields, so the server's per-field
// validators (tier/side enums, ISO date, stance clamp) only run on edits.
export function buildDiplomacyPatch(draft, row) {
  const p = {};
  for (const [k, v] of Object.entries(draft)) {
    if (!fieldChanged(k, v, row)) continue;
    if (k === "stance") p[k] = v === "" ? null : Number(v);
    else p[k] = v;
  }
  return p;
}

export function DiplomacyFieldsGrid({ draft, setDraft }) {
  const band = stanceBand(draft.stance);
  const set = (k) => (e) => setDraft({ ...draft, [k]: e.target.value });
  return (
    <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr", gap: "6px 10px", marginBottom: "6px" }}>
      <div>
        <label style={labelStyle()}>Country</label>
        <input style={fieldStyle()} value={draft.country_name} onChange={set("country_name")} />
      </div>
      <div>
        <label style={labelStyle()}>ISO (2-letter)</label>
        <input style={fieldStyle()} value={draft.country_iso} maxLength={2}
               onChange={(e) => setDraft({ ...draft, country_iso: e.target.value.toUpperCase() })} />
      </div>
      <div>
        <label style={labelStyle()}>Source side</label>
        <select style={fieldStyle()} value={draft.source_side} onChange={set("source_side")}>
          {SOURCE_SIDES.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>

      <div>
        <label style={labelStyle()}>Speaker</label>
        <input style={fieldStyle()} value={draft.speaker} onChange={set("speaker")} />
      </div>
      <div>
        <label style={labelStyle()}>Authority tier</label>
        <select style={fieldStyle()} value={draft.authority_tier} onChange={set("authority_tier")}>
          {AUTHORITY_TIERS.map((t) => <option key={t} value={t}>{TIER_LABEL[t]}</option>)}
        </select>
      </div>
      <div>
        <label style={labelStyle()}>Stance (−1…+1)</label>
        <div style={{ display: "flex", gap: "6px", alignItems: "center" }}>
          <input style={{ ...fieldStyle(), width: "70px" }} type="number" min="-1" max="1" step="0.1"
                 value={draft.stance} onChange={set("stance")} />
          <span style={{
            fontFamily: "var(--font-mono)", fontSize: "8.5px", letterSpacing: "0.05em",
            textTransform: "uppercase", color: "#fff", background: BAND_COLOUR[band],
            padding: "1px 5px", whiteSpace: "nowrap",
          }}>
            {BAND_LABEL[band]}
          </span>
        </div>
      </div>

      <div>
        <label style={labelStyle()}>Stated date</label>
        <input type="date" style={fieldStyle()} value={draft.stated_date} onChange={set("stated_date")} />
      </div>
      <div style={{ gridColumn: "2 / span 2" }}>
        <label style={labelStyle()}>Statement (English)</label>
        <textarea style={{ ...fieldStyle(), minHeight: "40px", fontFamily: "var(--font-body)" }}
                  value={draft.statement_en} onChange={set("statement_en")} />
      </div>
    </div>
  );
}

function CandidateCard({ candidate, onResolve }) {
  const [draft, setDraft] = useState(() => diplomacyDraftFrom(candidate));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const dirty = isDiplomacyDraftDirty(draft, candidate);

  const act = async (action) => {
    setBusy(true); setError(null);
    try {
      // Save edits before approving (never before dismissing — a dismissed
      // row's edits are moot).
      if (action === "approve" && dirty) {
        const patch = buildDiplomacyPatch(draft, candidate);
        if (Object.keys(patch).length > 0) await updateDiplomacyStatement(candidate.id, patch);
      }
      if (action === "approve") await approveDiplomacyStatement(candidate.id);
      else await dismissDiplomacyStatement(candidate.id);
      onResolve(candidate.id);
    } catch (e) {
      setError(e.message || String(e));
      setBusy(false);
    }
  };

  return (
    <div style={{ padding: "12px 14px", borderBottom: "1px solid var(--border-color)", opacity: busy ? 0.55 : 1 }}>
      <div style={{
        display: "flex", justifyContent: "space-between", alignItems: "baseline",
        fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--text-muted)", marginBottom: "8px",
      }}>
        <a href={candidate.article?.url} target="_blank" rel="noreferrer"
           style={{ color: "var(--text-secondary)", textDecoration: "underline" }}>
          {candidate.article?.source_name} · {candidate.article?.source_bias}
        </a>
        <span>
          {candidate.article?.published_at?.slice(0, 10)} · conf {Number(candidate.confidence || 0).toFixed(2)}
        </span>
      </div>

      {/* Original Chinese, for translation review */}
      {candidate.statement_zh && (
        <p style={{ fontFamily: "var(--font-body)", fontSize: "12px", color: "var(--text-secondary)",
                    lineHeight: 1.5, margin: "0 0 8px", fontStyle: "italic" }}>
          {candidate.statement_zh}
        </p>
      )}

      <DiplomacyFieldsGrid draft={draft} setDraft={setDraft} />

      {error && (
        <div style={{ color: "var(--accent-red)", fontFamily: "var(--font-mono)", fontSize: "10px", marginBottom: "4px" }}>
          {error}
        </div>
      )}

      <div style={{ display: "flex", gap: "6px", alignItems: "center", marginTop: "8px" }}>
        <button disabled={busy} onClick={() => act("approve")}
                style={{ padding: "5px 12px", fontFamily: "var(--font-mono)", fontSize: "10px",
                         letterSpacing: "0.08em", textTransform: "uppercase",
                         background: "#16a34a", color: "#fff", border: "none", cursor: "pointer" }}>
          {dirty ? "Save & approve" : "Approve"}
        </button>
        <button disabled={busy} onClick={() => act("dismiss")}
                style={{ padding: "5px 12px", fontFamily: "var(--font-mono)", fontSize: "10px",
                         letterSpacing: "0.08em", textTransform: "uppercase", background: "transparent",
                         color: "var(--text-secondary)", border: "1px solid var(--border-color)", cursor: "pointer" }}>
          Dismiss
        </button>
      </div>
    </div>
  );
}

// Collapsible per-country group — only expanded groups render their cards, so
// the DOM stays light across the (large) pending backlog.
function CountryGroup({ group, expanded, onToggle, onResolve }) {
  return (
    <div>
      <div onClick={onToggle}
           style={{
           display: "flex", alignItems: "center", justifyContent: "space-between",
           padding: "10px 16px", cursor: "pointer", background: "var(--bg-primary)",
           borderBottom: "1px solid var(--border-color)",
         }}>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: "11px", letterSpacing: "0.06em",
                       color: "var(--text-primary)" }}>
          <span style={{ color: "var(--text-muted)", marginRight: "8px" }}>{expanded ? "▾" : "▸"}</span>
          {group.country_name}
          <span style={{ color: "var(--text-muted)", marginLeft: "6px" }}>{group.country_iso}</span>
        </span>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--text-muted)" }}>
          {group.statements.length} pending
        </span>
      </div>
      {expanded && group.statements.map((c) => (
        <CandidateCard key={c.id} candidate={c} onResolve={onResolve} />
      ))}
    </div>
  );
}

export default function DiplomacyReviewQueue({ onClose, onResolveAll }) {
  const [data, setData] = useState(null);   // {groups, total} | {_error} | null
  const [expanded, setExpanded] = useState(() => new Set());

  useEffect(() => {
    fetchDiplomacyCandidates()
      .then((r) => setData(r))
      .catch((e) => setData({ _error: e.message }));
  }, []);

  // Biggest backlogs first — clears duplicate piles fastest.
  const groups = useMemo(() => {
    if (!data?.groups) return [];
    return [...data.groups].sort((a, b) => b.statements.length - a.statements.length);
  }, [data]);

  const total = data?.groups ? data.groups.reduce((s, g) => s + g.statements.length, 0) : null;

  const onResolve = (id) => {
    setData((prev) => {
      if (!prev?.groups) return prev;
      const nextGroups = prev.groups
        .map((g) => ({ ...g, statements: g.statements.filter((s) => s.id !== id) }))
        .filter((g) => g.statements.length > 0);
      const left = nextGroups.reduce((s, g) => s + g.statements.length, 0);
      if (left === 0 && onResolveAll) onResolveAll();
      return { ...prev, groups: nextGroups };
    });
  };

  const toggle = (iso) => setExpanded((prev) => {
    const next = new Set(prev);
    if (next.has(iso)) next.delete(iso); else next.add(iso);
    return next;
  });

  return (
    <div onClick={(e) => e.target === e.currentTarget && onClose()}
         style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.55)",
                  display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000 }}>
      <div style={{ background: "var(--bg-card)", border: "1px solid var(--border-color)",
                    borderTop: "4px solid #d4a94a", borderRadius: "4px",
                    width: 820, maxWidth: "94vw", maxHeight: "88vh",
                    display: "flex", flexDirection: "column" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between",
                      padding: "14px 16px", borderBottom: "1px solid var(--border-color)" }}>
          <div>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: "11px", fontWeight: 700,
                           letterSpacing: "0.07em", textTransform: "uppercase", color: "var(--text-primary)" }}>
              Diplomatic stance candidates
            </span>
            <span style={{ fontSize: "10px", color: "var(--text-muted)", marginLeft: "10px" }}>
              {total === null ? "…" : `${total} pending · ${groups.length} countries`}
            </span>
          </div>
          <button onClick={onClose}
                  style={{ background: "none", border: "none", cursor: "pointer",
                           color: "var(--text-muted)", fontSize: "16px", padding: "2px 4px" }}>
            ✕
          </button>
        </div>

        <div style={{ overflowY: "auto" }}>
          {!data ? (
            <div style={{ padding: "24px 16px", color: "var(--text-muted)", fontFamily: "var(--font-mono)", fontSize: "12px" }}>
              Loading…
            </div>
          ) : data._error ? (
            <div style={{ padding: "24px 16px", color: "var(--accent-red)", fontFamily: "var(--font-mono)", fontSize: "12px" }}>
              {data._error}
            </div>
          ) : groups.length === 0 ? (
            <div style={{ padding: "24px 16px", color: "var(--text-muted)", fontFamily: "var(--font-mono)",
                          fontSize: "12px", fontStyle: "italic" }}>
              No pending candidates.
            </div>
          ) : (
            groups.map((g) => (
              <CountryGroup key={g.country_iso} group={g}
                            expanded={expanded.has(g.country_iso)}
                            onToggle={() => toggle(g.country_iso)}
                            onResolve={onResolve} />
            ))
          )}
        </div>
      </div>
    </div>
  );
}
