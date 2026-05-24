import { useEffect, useState } from "react";
import {
  fetchMilitaryExerciseCandidates,
  fetchMilitaryExercises,
  approveMilitaryExercise,
  dismissMilitaryExercise,
  mergeMilitaryExercise,
  updateMilitaryExercise,
} from "../api";
import { PERFORMER_COLOUR, PERFORMER_LABEL } from "./ExerciseMap";

const EXERCISE_KINDS = [
  "live_fire", "readiness_drill", "joint_patrol",
  "named_exercise", "cyber", "amphibious", "other",
];

function fieldStyle() {
  return {
    fontFamily: "var(--font-mono)",
    fontSize: "11px",
    padding: "4px 6px",
    border: "1px solid var(--border-color)",
    background: "var(--bg-primary)",
    color: "var(--text-primary)",
    width: "100%",
    boxSizing: "border-box",
  };
}

function labelStyle() {
  return {
    fontFamily: "var(--font-mono)",
    fontSize: "9.5px",
    letterSpacing: "0.06em",
    textTransform: "uppercase",
    color: "var(--text-muted)",
    marginBottom: "2px",
    display: "block",
  };
}

function CandidateCard({ candidate, approvedTargets, onResolve }) {
  const [draft, setDraft] = useState({
    name_en:        candidate.name_en || "",
    name_zh:        candidate.name_zh || "",
    performer:      candidate.performer,
    exercise_kind:  candidate.exercise_kind || "other",
    start_date:     candidate.start_date || "",
    end_date:       candidate.end_date || "",
    location_label: candidate.location_label || "",
    latitude:       candidate.latitude  ?? "",
    longitude:      candidate.longitude ?? "",
    description_en: candidate.description_en || "",
  });
  const [busy, setBusy] = useState(false);
  const [mergeTarget, setMergeTarget] = useState("");
  const [error, setError] = useState(null);

  // Track whether the draft diverges from the candidate's current DB state —
  // only PATCH the row if the analyst edited something.
  const isDirty = Object.entries(draft).some(([k, v]) => {
    const orig = candidate[k];
    if (k === "latitude" || k === "longitude") {
      const origNum = orig === null || orig === undefined ? "" : String(orig);
      return String(v) !== origNum;
    }
    return (v || "") !== (orig || "");
  });

  const patchFromDraft = () => {
    const p = { ...draft };
    if (p.latitude === "")  p.latitude = null;  else p.latitude  = Number(p.latitude);
    if (p.longitude === "") p.longitude = null; else p.longitude = Number(p.longitude);
    return p;
  };

  const resolve = async (fn, extra) => {
    setBusy(true);
    setError(null);
    try {
      if (isDirty && fn !== dismissMilitaryExercise) {
        await updateMilitaryExercise(candidate.id, patchFromDraft());
      }
      await fn(candidate.id, extra);
      onResolve(candidate.id);
    } catch (e) {
      setError(e.message || String(e));
      setBusy(false);
    }
  };

  const performerColour = PERFORMER_COLOUR[draft.performer] || "#666";

  return (
    <div style={{
      padding: "12px 14px",
      borderBottom: "1px solid var(--border-color)",
      opacity: busy ? 0.55 : 1,
    }}>
      {/* Top: source + AI confidence */}
      <div style={{
        display: "flex", justifyContent: "space-between", alignItems: "baseline",
        fontFamily: "var(--font-mono)", fontSize: "10px",
        color: "var(--text-muted)", marginBottom: "8px",
      }}>
        <a href={candidate.article?.url} target="_blank" rel="noreferrer"
           style={{ color: "var(--text-secondary)", textDecoration: "underline" }}>
          {candidate.article?.source_name}
        </a>
        <span>
          {candidate.article?.published_at?.slice(0, 10)} ·
          conf {Number(candidate.confidence || 0).toFixed(2)}
        </span>
      </div>

      {/* Grid of editable fields */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "2fr 1fr 1fr",
        gap: "6px 10px",
        marginBottom: "6px",
      }}>
        <div>
          <label style={labelStyle()}>Name (English)</label>
          <input style={fieldStyle()} value={draft.name_en}
                 placeholder="Joint Sword 2024B"
                 onChange={(e) => setDraft({ ...draft, name_en: e.target.value })} />
        </div>
        <div>
          <label style={labelStyle()}>Performer</label>
          <select style={{ ...fieldStyle(), color: performerColour, fontWeight: 700 }}
                  value={draft.performer}
                  onChange={(e) => setDraft({ ...draft, performer: e.target.value })}>
            {Object.keys(PERFORMER_LABEL).map((p) =>
              <option key={p} value={p}>{PERFORMER_LABEL[p]}</option>
            )}
          </select>
        </div>
        <div>
          <label style={labelStyle()}>Kind</label>
          <select style={fieldStyle()} value={draft.exercise_kind}
                  onChange={(e) => setDraft({ ...draft, exercise_kind: e.target.value })}>
            {EXERCISE_KINDS.map((k) => <option key={k} value={k}>{k.replace("_", " ")}</option>)}
          </select>
        </div>

        <div>
          <label style={labelStyle()}>Name (original)</label>
          <input style={fieldStyle()} value={draft.name_zh}
                 onChange={(e) => setDraft({ ...draft, name_zh: e.target.value })} />
        </div>
        <div>
          <label style={labelStyle()}>Start</label>
          <input type="date" style={fieldStyle()} value={draft.start_date}
                 onChange={(e) => setDraft({ ...draft, start_date: e.target.value })} />
        </div>
        <div>
          <label style={labelStyle()}>End</label>
          <input type="date" style={fieldStyle()} value={draft.end_date}
                 onChange={(e) => setDraft({ ...draft, end_date: e.target.value })} />
        </div>

        <div style={{ gridColumn: "1 / span 3" }}>
          <label style={labelStyle()}>Location label</label>
          <input style={fieldStyle()} value={draft.location_label}
                 placeholder="e.g. Bashi Channel ~50nm SW of Eluanbi"
                 onChange={(e) => setDraft({ ...draft, location_label: e.target.value })} />
        </div>

        <div>
          <label style={labelStyle()}>Latitude (8–35°N)</label>
          <input style={fieldStyle()} type="number" step="0.001"
                 value={draft.latitude}
                 onChange={(e) => setDraft({ ...draft, latitude: e.target.value })} />
        </div>
        <div>
          <label style={labelStyle()}>Longitude (105–135°E)</label>
          <input style={fieldStyle()} type="number" step="0.001"
                 value={draft.longitude}
                 onChange={(e) => setDraft({ ...draft, longitude: e.target.value })} />
        </div>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: "9px", color: "var(--text-muted)", alignSelf: "end" }}>
          Empty = no marker on the map.
        </div>

        <div style={{ gridColumn: "1 / span 3" }}>
          <label style={labelStyle()}>Description (English)</label>
          <textarea style={{ ...fieldStyle(), minHeight: "44px", fontFamily: "var(--font-body)" }}
                    value={draft.description_en}
                    onChange={(e) => setDraft({ ...draft, description_en: e.target.value })} />
        </div>
      </div>

      {error && (
        <div style={{ color: "var(--accent-red)", fontFamily: "var(--font-mono)",
                      fontSize: "10px", marginBottom: "4px" }}>
          {error}
        </div>
      )}

      {/* Action row */}
      <div style={{
        display: "flex", gap: "6px", alignItems: "center", flexWrap: "wrap",
        marginTop: "8px",
      }}>
        <button disabled={busy}
                onClick={() => resolve(approveMilitaryExercise)}
                style={{
                  padding: "5px 12px", fontFamily: "var(--font-mono)",
                  fontSize: "10px", letterSpacing: "0.08em", textTransform: "uppercase",
                  background: "#16a34a", color: "#fff", border: "none", cursor: "pointer",
                }}>
          {isDirty ? "Save & approve" : "Approve"}
        </button>
        <button disabled={busy}
                onClick={() => resolve(dismissMilitaryExercise)}
                style={{
                  padding: "5px 12px", fontFamily: "var(--font-mono)",
                  fontSize: "10px", letterSpacing: "0.08em", textTransform: "uppercase",
                  background: "transparent", color: "var(--text-secondary)",
                  border: "1px solid var(--border-color)", cursor: "pointer",
                }}>
          Dismiss
        </button>

        <select value={mergeTarget}
                onChange={(e) => setMergeTarget(e.target.value)}
                style={{ ...fieldStyle(), width: "180px", marginLeft: "auto" }}>
          <option value="">Merge into…</option>
          {approvedTargets.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name_en || `[unnamed ${t.performer} ${t.exercise_kind}]`}
              {t.start_date ? ` (${t.start_date})` : ""}
            </option>
          ))}
        </select>
        <button disabled={busy || !mergeTarget}
                onClick={() => resolve(
                  (id) => mergeMilitaryExercise(id, Number(mergeTarget)),
                )}
                style={{
                  padding: "5px 10px", fontFamily: "var(--font-mono)",
                  fontSize: "10px", letterSpacing: "0.08em", textTransform: "uppercase",
                  background: "transparent", color: mergeTarget ? "var(--text-primary)" : "var(--text-muted)",
                  border: "1px solid var(--border-color)",
                  cursor: mergeTarget ? "pointer" : "not-allowed",
                }}>
          Merge
        </button>
      </div>
    </div>
  );
}

export default function ExerciseReviewQueue({ onClose, onResolveAll }) {
  const [candidates, setCandidates] = useState(null);
  const [approvedTargets, setApprovedTargets] = useState([]);

  const loadCandidates = () => {
    fetchMilitaryExerciseCandidates()
      .then((r) => setCandidates(r.candidates || {}))
      .catch((e) => setCandidates({ _error: e.message }));
  };

  useEffect(() => {
    loadCandidates();
    // Approved exercises in last 180 days = potential merge targets.
    fetchMilitaryExercises({ days: 180 })
      .then((r) => setApprovedTargets(r.rows || []))
      .catch(() => setApprovedTargets([]));
  }, []);

  const onResolve = (resolvedId) => {
    // Filter the resolved candidate out of all buckets locally; once empty,
    // signal the parent to refresh its public-side rows.
    setCandidates((prev) => {
      const next = {};
      let totalLeft = 0;
      for (const [k, list] of Object.entries(prev || {})) {
        const filtered = list.filter((c) => c.id !== resolvedId);
        if (filtered.length > 0) {
          next[k] = filtered;
          totalLeft += filtered.length;
        }
      }
      if (totalLeft === 0 && onResolveAll) onResolveAll();
      return next;
    });
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
        borderTop: "4px solid #7c3aed",
        borderRadius: "4px",
        width: 780, maxWidth: "94vw", maxHeight: "86vh",
        display: "flex", flexDirection: "column",
      }}>
        <div style={{
          display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "14px 16px", borderBottom: "1px solid var(--border-color)",
        }}>
          <div>
            <span style={{
              fontFamily: "var(--font-mono)", fontSize: "11px", fontWeight: 700,
              letterSpacing: "0.07em", textTransform: "uppercase", color: "var(--text-primary)",
            }}>
              Exercise candidates
            </span>
            <span style={{ fontSize: "10px", color: "var(--text-muted)", marginLeft: "10px" }}>
              {candidates ? Object.values(candidates).reduce((s, l) => s + (Array.isArray(l) ? l.length : 0), 0) : "…"} pending
            </span>
          </div>
          <button onClick={onClose}
                  style={{ background: "none", border: "none", cursor: "pointer",
                           color: "var(--text-muted)", fontSize: "16px", padding: "2px 4px" }}>
            ✕
          </button>
        </div>

        <div style={{ overflowY: "auto", padding: "8px 0" }}>
          {!candidates ? (
            <div style={{ padding: "24px 16px", color: "var(--text-muted)",
                          fontFamily: "var(--font-mono)", fontSize: "12px" }}>
              Loading…
            </div>
          ) : candidates._error ? (
            <div style={{ padding: "24px 16px", color: "var(--accent-red)",
                          fontFamily: "var(--font-mono)", fontSize: "12px" }}>
              {candidates._error}
            </div>
          ) : Object.keys(candidates).length === 0 ? (
            <div style={{ padding: "24px 16px", color: "var(--text-muted)",
                          fontFamily: "var(--font-mono)", fontSize: "12px", fontStyle: "italic" }}>
              No pending candidates.
            </div>
          ) : Object.entries(candidates)
              .sort(([a], [b]) => (a === "_unnamed_" ? 1 : b === "_unnamed_" ? -1 : a.localeCompare(b)))
              .map(([groupKey, list]) => (
            <div key={groupKey}>
              <div style={{
                padding: "10px 16px 4px",
                fontFamily: "var(--font-mono)", fontSize: "10px",
                letterSpacing: "0.08em", textTransform: "uppercase",
                color: "var(--text-secondary)",
                background: "var(--bg-primary)",
                borderBottom: "1px solid var(--border-color)",
              }}>
                {groupKey === "_unnamed_" ? "Unnamed drills" : groupKey}
                <span style={{ color: "var(--text-muted)", marginLeft: "8px" }}>
                  ({list.length})
                </span>
              </div>
              {list.map((c) => (
                <CandidateCard key={c.id} candidate={c}
                               approvedTargets={approvedTargets}
                               onResolve={onResolve} />
              ))}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
