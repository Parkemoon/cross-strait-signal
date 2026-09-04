import { useState } from "react";
import { updateMilitaryExercise, dismissMilitaryExercise } from "../api";
import {
  ExerciseFieldsGrid,
  exerciseDraftFrom,
  isExerciseDraftDirty,
  buildExercisePatch,
} from "./ExerciseReviewQueue";
import { ModalFrame, Btn, ErrorLine } from "./adminChrome";

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
    <ModalFrame
      title="Edit approved exercise"
      accent="var(--hostile)"
      onClose={onClose}
      busy={busy}
      meta={exercise.article?.source_name ? (
        <>via <a href={exercise.article.url} target="_blank" rel="noreferrer"
                 style={{ color: "var(--muted)", textDecoration: "underline" }}>{exercise.article.source_name}</a></>
      ) : null}
      footer={
        <>
          <Btn variant="primary" disabled={busy || !isDirty} onClick={handleSave}>Save</Btn>
          <Btn variant="danger" disabled={busy} onClick={handleDismiss}>Dismiss</Btn>
          <div style={{ flex: 1 }} />
          <Btn variant="outline" disabled={busy} onClick={onClose}>Cancel</Btn>
        </>
      }
    >

        <div>
          <ExerciseFieldsGrid draft={draft} setDraft={setDraft} />

          <ErrorLine>{error}</ErrorLine>
        </div>
    </ModalFrame>
  );
}
