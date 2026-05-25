import { useState } from "react";
import { updateMilitaryExercise, dismissMilitaryExercise } from "../api";
import {
  ExerciseFieldsGrid,
  exerciseDraftFrom,
  isExerciseDraftDirty,
  buildExercisePatch,
} from "./ExerciseReviewQueue";

// Edit / dismiss modal for an already-approved exercise. Mirrors the
// shape of the candidate review card but with only Save + Dismiss
// actions (no approve/merge — those belong to the pending workflow).
export default function ExerciseEditModal({ exercise, onClose, onSaved, onDismissed }) {
  const [draft, setDraft] = useState(() => exerciseDraftFrom(exercise));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const isDirty = isExerciseDraftDirty(draft, exercise);

  const handleSave = async () => {
    if (!isDirty) { onClose(); return; }
    setBusy(true);
    setError(null);
    try {
      const patchBody = buildExercisePatch(draft, exercise);
      const updated = await updateMilitaryExercise(exercise.id, patchBody);
      onSaved(updated);
    } catch (e) {
      setError(e.message || String(e));
      setBusy(false);
    }
  };

  const handleDismiss = async () => {
    setBusy(true);
    setError(null);
    try {
      await dismissMilitaryExercise(exercise.id);
      onDismissed(exercise.id);
    } catch (e) {
      setError(e.message || String(e));
      setBusy(false);
    }
  };

  return (
    <div
      onClick={(e) => e.target === e.currentTarget && !busy && onClose()}
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
        width: 720, maxWidth: "94vw", maxHeight: "86vh",
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
              Edit approved exercise
            </span>
            {exercise.article?.source_name && (
              <span style={{ fontSize: "10px", color: "var(--text-muted)", marginLeft: "10px" }}>
                via{" "}
                <a href={exercise.article.url} target="_blank" rel="noreferrer"
                   style={{ color: "var(--text-secondary)", textDecoration: "underline" }}>
                  {exercise.article.source_name}
                </a>
              </span>
            )}
          </div>
          <button onClick={onClose} disabled={busy}
                  style={{ background: "none", border: "none",
                           cursor: busy ? "default" : "pointer",
                           color: "var(--text-muted)", fontSize: "16px", padding: "2px 4px" }}>
            ✕
          </button>
        </div>

        <div style={{ overflowY: "auto", padding: "14px 16px", opacity: busy ? 0.55 : 1 }}>
          <ExerciseFieldsGrid draft={draft} setDraft={setDraft} />

          {error && (
            <div style={{ color: "var(--accent-red)", fontFamily: "var(--font-mono)",
                          fontSize: "10px", marginTop: "8px" }}>
              {error}
            </div>
          )}
        </div>

        <div style={{
          display: "flex", gap: "8px", alignItems: "center",
          padding: "12px 16px", borderTop: "1px solid var(--border-color)",
        }}>
          <button disabled={busy || !isDirty} onClick={handleSave}
                  style={{
                    padding: "5px 14px", fontFamily: "var(--font-mono)",
                    fontSize: "10px", letterSpacing: "0.08em", textTransform: "uppercase",
                    background: isDirty ? "#16a34a" : "transparent",
                    color: isDirty ? "#fff" : "var(--text-muted)",
                    border: isDirty ? "none" : "1px solid var(--border-color)",
                    cursor: busy || !isDirty ? "not-allowed" : "pointer",
                  }}>
            Save
          </button>
          <button disabled={busy} onClick={handleDismiss}
                  style={{
                    padding: "5px 14px", fontFamily: "var(--font-mono)",
                    fontSize: "10px", letterSpacing: "0.08em", textTransform: "uppercase",
                    background: "transparent", color: "var(--accent-red, #dc2626)",
                    border: "1px solid var(--accent-red, #dc2626)",
                    cursor: busy ? "not-allowed" : "pointer",
                  }}>
            Dismiss
          </button>
          <div style={{ flex: 1 }} />
          <button disabled={busy} onClick={onClose}
                  style={{
                    padding: "5px 14px", fontFamily: "var(--font-mono)",
                    fontSize: "10px", letterSpacing: "0.08em", textTransform: "uppercase",
                    background: "transparent", color: "var(--text-secondary)",
                    border: "1px solid var(--border-color)",
                    cursor: busy ? "not-allowed" : "pointer",
                  }}>
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
