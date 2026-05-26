import { useState } from "react";
import { createPollster } from "../api";

// Constants and helpers shared by PollReviewQueue and PollEntryModal.
// Both surfaces need the same dropdown contents (one source of truth so
// adding a bias / family / scale_type to one doesn't silently leave the
// other behind) and the same inline "create new pollster" flow.

// Server-side validators in api/routes/polls.py — mirror these constants
// so the dropdowns only offer valid choices. Out-of-set picks 400 at
// submit time. The bias and status enums also gate the POST /pollsters
// create endpoint.
export const FAMILIES   = ["identity", "unification", "approval", "attitude", "vote_intent", "issue"];
export const SCALE_TYPES = [
  "approve_disapprove", "support_oppose", "five_point",
  "six_point", "choice", "numeric",
];
export const POLLSTER_BIASES = [
  "academic", "green", "green_leaning", "centrist",
  "blue_leaning", "blue", "state_official",
];
export const POLLSTER_STATUSES = ["active", "historical", "ad_hoc", "unknown"];

// Identifier shape — same regex gates pollster slug AND question_key
// creation server-side (^[a-z0-9][a-z0-9_]*$).
export const SLUG_RX = /^[a-z0-9][a-z0-9_]*$/;

// Sentinel values for the dropdowns' "create new" branches. Distinct
// from any valid slug / question_key (double underscore prefix).
export const CREATE_NEW           = "__new__";
export const CREATE_NEW_POLLSTER  = "__new_pollster__";

export function fieldStyle() {
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

export function labelStyle() {
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

// Group an array of poll_questions entries by family so the picker can
// render <optgroup>s. Used in both the review queue's per-question
// resolver and the manual-entry modal's per-question editor.
export function groupKeysByFamily(allKeys) {
  const groups = {};
  for (const k of allKeys || []) {
    const fam = k.family || "issue";
    if (!groups[fam]) groups[fam] = [];
    groups[fam].push(k);
  }
  for (const list of Object.values(groups)) {
    list.sort((a, b) => a.question_key.localeCompare(b.question_key));
  }
  return groups;
}

// Inline pollster-creation form. Lives inside either the envelope
// dropdown (review queue) or the pollster picker row (entry modal).
// `gridColumn` defaults to spanning a 4-column parent grid — the
// existing layout in both callers; pass a different value if the
// containing grid changes.
export function NewPollsterForm({ onCreated, onCancel, gridColumn = "1 / span 4" }) {
  const [row, setRow] = useState({
    slug: "", name_en: "", name_zh: "", bias: "", status: "active",
  });
  const [busy, setBusy]   = useState(false);
  const [error, setError] = useState(null);

  const submit = async () => {
    const slug = row.slug.trim();
    if (!SLUG_RX.test(slug)) {
      setError(`slug must match ^[a-z0-9][a-z0-9_]*$ (got ${JSON.stringify(slug)})`);
      return;
    }
    if (!row.name_en.trim()) { setError("name_en is required"); return; }
    if (!row.bias)           { setError("bias is required"); return; }
    setBusy(true);
    setError(null);
    try {
      const created = await createPollster({
        slug,
        name_en: row.name_en.trim(),
        name_zh: row.name_zh.trim() || undefined,
        bias:    row.bias,
        status:  row.status,
      });
      onCreated(created.slug, { ...row, slug });
    } catch (e) {
      setError(e.message || String(e));
      setBusy(false);
    }
  };

  return (
    <div style={{
      gridColumn,
      padding: "8px 10px",
      background: "var(--bg-card)",
      border: "1px dashed var(--border-color)",
      marginTop: "2px",
    }}>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 2fr 2fr 1fr 1fr", gap: "6px 10px" }}>
        <div>
          <label style={labelStyle()}>slug (lower_snake_case)</label>
          <input style={fieldStyle()} placeholder="e.g. apollo"
                 value={row.slug}
                 onChange={(e) => setRow({ ...row, slug: e.target.value })} />
        </div>
        <div>
          <label style={labelStyle()}>Name (English)</label>
          <input style={fieldStyle()} placeholder="Apollo Survey"
                 value={row.name_en}
                 onChange={(e) => setRow({ ...row, name_en: e.target.value })} />
        </div>
        <div>
          <label style={labelStyle()}>Name (Chinese)</label>
          <input style={fieldStyle()} placeholder="阿波羅民調"
                 value={row.name_zh}
                 onChange={(e) => setRow({ ...row, name_zh: e.target.value })} />
        </div>
        <div>
          <label style={labelStyle()}>Bias</label>
          <select style={fieldStyle()} value={row.bias}
                  onChange={(e) => setRow({ ...row, bias: e.target.value })}>
            <option value="">—</option>
            {POLLSTER_BIASES.map((b) => <option key={b} value={b}>{b}</option>)}
          </select>
        </div>
        <div>
          <label style={labelStyle()}>Status</label>
          <select style={fieldStyle()} value={row.status}
                  onChange={(e) => setRow({ ...row, status: e.target.value })}>
            {POLLSTER_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
      </div>
      {error && (
        <div style={{ color: "var(--accent-red)", fontFamily: "var(--font-mono)",
                      fontSize: "10px", marginTop: "6px" }}>{error}</div>
      )}
      <div style={{ display: "flex", gap: "6px", marginTop: "8px" }}>
        <button disabled={busy} onClick={submit} style={{
          padding: "4px 10px", fontFamily: "var(--font-mono)", fontSize: "10px",
          letterSpacing: "0.06em", textTransform: "uppercase",
          background: "var(--text-primary)", color: "var(--bg-primary)",
          border: "none", cursor: busy ? "not-allowed" : "pointer",
        }}>Create pollster</button>
        <button disabled={busy} onClick={onCancel} style={{
          padding: "4px 10px", fontFamily: "var(--font-mono)", fontSize: "10px",
          letterSpacing: "0.06em", textTransform: "uppercase",
          background: "transparent", color: "var(--text-secondary)",
          border: "1px solid var(--border-color)", cursor: "pointer",
        }}>Cancel</button>
      </div>
    </div>
  );
}
