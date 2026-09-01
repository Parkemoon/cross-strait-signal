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
