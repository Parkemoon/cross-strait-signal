import { useState } from "react";
import { updateDiplomacyStatement, dismissDiplomacyStatement } from "../api";
import {
  DiplomacyFieldsGrid,
  diplomacyDraftFrom,
  isDiplomacyDraftDirty,
  buildDiplomacyPatch,
} from "./DiplomacyReviewQueue";
import { ModalFrame, Btn, ErrorLine } from "./adminChrome";

// Edit / dismiss modal for an already-APPROVED diplomacy statement. Mirrors
// the candidate review card's field grid but exposes only Save + Dismiss —
// approve / merge belong to the pending workflow. The PATCH endpoint is
// status-agnostic, so buildDiplomacyPatch serves both paths unchanged.
// Dismiss demotes a wrongly-approved row to `dismissed` (drops it from the map).
export default function DiplomacyEditModal({ statement, onClose, onSaved, onDismissed }) {
  const [draft, setDraft] = useState(() => diplomacyDraftFrom(statement));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const isDirty = isDiplomacyDraftDirty(draft, statement);

  const handleSave = async () => {
    if (!isDirty) { onClose(); return; }
    setBusy(true);
    setError(null);
    try {
      const patch = buildDiplomacyPatch(draft, statement);
      const updated = await updateDiplomacyStatement(statement.id, patch);
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
      await dismissDiplomacyStatement(statement.id);
      onDismissed(statement.id);
    } catch (e) {
      setError(e.message || String(e));
      setBusy(false);
    }
  };

  return (
    <ModalFrame
      title="Edit approved statement"
      accent="var(--flag)"
      onClose={onClose}
      busy={busy}
      meta={statement.article?.source_name ? (
        <>via <a href={statement.article.url} target="_blank" rel="noreferrer"
                 style={{ color: "var(--muted)", textDecoration: "underline" }}>{statement.article.source_name}</a></>
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
          {/* Original Chinese, for translation / attribution review */}
          {statement.statement_zh && (
            <p style={{ fontFamily: "var(--font-headline)", fontSize: "14px", color: "var(--body)",
                        lineHeight: 1.55, margin: "0 0 12px", fontStyle: "italic" }}>
              {statement.statement_zh}
            </p>
          )}

          <DiplomacyFieldsGrid draft={draft} setDraft={setDraft} />

          <ErrorLine>{error}</ErrorLine>
        </div>
    </ModalFrame>
  );
}
