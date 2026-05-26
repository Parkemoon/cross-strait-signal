import { useEffect, useMemo, useState } from "react";
import {
  fetchPollCandidates,
  fetchPolls,
  fetchPollsRoster,
  approvePoll,
  dismissPoll,
  mergePoll,
  updatePoll,
  createPollster,
} from "../api";
import { pollsterChipColour, PollsterChip, FAMILY_LABELS } from "./PollsTab";

// Server-side validators in api/routes/polls.py — mirror here so the
// dropdowns and "create new question" form only offer valid choices.
// Out-of-set picks would 400 at approve time.
const FAMILIES   = ["identity", "unification", "approval", "attitude", "vote_intent", "issue"];
const SCALE_TYPES = [
  "approve_disapprove", "support_oppose", "five_point",
  "six_point", "choice", "numeric",
];
const POLLSTER_BIASES  = [
  "academic", "green", "green_leaning", "centrist",
  "blue_leaning", "blue", "state_official",
];
const POLLSTER_STATUSES = ["active", "historical", "ad_hoc", "unknown"];
const QUESTION_KEY_RX = /^[a-z0-9][a-z0-9_]*$/;
const CREATE_NEW           = "__new__";
const CREATE_NEW_POLLSTER  = "__new_pollster__";

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

function fmtPct(v) {
  if (v === null || v === undefined) return "—";
  return `${Number(v).toFixed(1)}%`;
}

// Build the envelope-edit draft from a candidate row. Empty string is the
// form's "absent" sentinel for nullable text/number fields; the approve
// path sends a field only when the draft differs from the original.
function envelopeDraftFrom(c) {
  return {
    pollster_slug:    c.pollster_slug || "",
    fielded_start:    c.fielded_start || "",
    fielded_end:      c.fielded_end   || "",
    sample_size:      c.sample_size == null ? "" : String(c.sample_size),
    methodology_note: c.methodology_note || "",
    source_url:       c.source_url || "",
    notes:            c.notes || "",
  };
}

// Initial per-question resolution defaults. We DON'T pre-select an
// existing question_key — every question requires an explicit analyst
// pick. The "create new" branch pre-fills text_zh/text_en from the AI's
// extraction so the analyst usually just picks a family + scale_type
// and saves.
function resolutionDraftFor(pendingQuestion) {
  return {
    question_key: "",
    text_zh:      pendingQuestion.question_text_zh || "",
    text_en:      pendingQuestion.question_text_en || "",
    family:       "",
    scale_type:   "",
    description:  "",
  };
}

// Group existing question keys by family for the picker's <optgroup>s.
function groupKeysByFamily(allKeys) {
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

function QuestionResolver({ idx, pendingQuestion, allKeys, resolution, setResolution }) {
  const grouped = useMemo(() => groupKeysByFamily(allKeys), [allKeys]);
  const isCreatingNew = resolution.question_key === CREATE_NEW;
  const isSkipped     = !!resolution._skip;
  const options = pendingQuestion.options || [];

  return (
    <div style={{
      border: "1px solid var(--border-color)",
      padding: "10px 12px",
      marginBottom: "8px",
      background: "var(--bg-primary)",
      opacity: isSkipped ? 0.45 : 1,
    }}>
      {/* AI-extracted question wording — read-only, just for analyst
          to audit what they're about to commit. */}
      <div style={{
        display: "flex", justifyContent: "space-between", alignItems: "center",
        marginBottom: "4px",
      }}>
        <span style={{
          fontFamily: "var(--font-mono)",
          fontSize: "9.5px",
          letterSpacing: "0.06em",
          textTransform: "uppercase",
          color: "var(--text-muted)",
        }}>
          Question {idx + 1} — AI extraction{isSkipped ? " (skipped)" : ""}
        </span>
        <button
          onClick={() => setResolution({ ...resolution, _skip: !isSkipped })}
          style={{
            padding: "2px 8px", fontFamily: "var(--font-mono)",
            fontSize: "9px", letterSpacing: "0.06em", textTransform: "uppercase",
            background: "transparent",
            color: isSkipped ? "var(--text-primary)" : "var(--text-muted)",
            border: "1px solid var(--border-color)",
            cursor: "pointer",
          }}
        >
          {isSkipped ? "Restore" : "Skip"}
        </button>
      </div>
      {pendingQuestion.question_text_zh && (
        <div style={{
          fontFamily: "var(--font-mono)", fontSize: "11px",
          color: "var(--text-primary)", marginBottom: "2px",
        }}>
          {pendingQuestion.question_text_zh}
        </div>
      )}
      {pendingQuestion.question_text_en && (
        <div style={{
          fontFamily: "var(--font-body)", fontSize: "11px",
          color: "var(--text-secondary)", marginBottom: "8px",
          fontStyle: "italic",
        }}>
          {pendingQuestion.question_text_en}
        </div>
      )}

      {/* Options + percentages — these are what will be materialised
          into poll_results under the picked question_key. */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
        gap: "2px 14px",
        marginBottom: "10px",
        paddingLeft: "10px",
        borderLeft: "2px solid var(--border-color)",
      }}>
        {options.map((o, i) => (
          <div key={i} style={{
            display: "flex", justifyContent: "space-between",
            fontFamily: "var(--font-mono)", fontSize: "11px",
          }}>
            <span>{o.label_en || o.label_zh || `option ${i + 1}`}</span>
            <span style={{ color: "var(--text-muted)" }}>{fmtPct(o.percentage)}</span>
          </div>
        ))}
      </div>

      {/* question_key picker. <optgroup> per family + "create new" sentinel. */}
      {!isSkipped && (<>
      <label style={labelStyle()}>Map to canonical question</label>
      <select
        style={fieldStyle()}
        value={resolution.question_key}
        onChange={(e) => setResolution({ ...resolution, question_key: e.target.value })}
      >
        <option value="">— pick a question_key —</option>
        <option value={CREATE_NEW}>+ Create new question_key…</option>
        {FAMILIES.filter((f) => grouped[f]?.length).map((fam) => (
          <optgroup key={fam} label={FAMILY_LABELS[fam] || fam}>
            {grouped[fam].map((k) => (
              <option key={k.question_key} value={k.question_key}>
                {k.question_key} — {k.question_text_en || k.question_text_zh}
              </option>
            ))}
          </optgroup>
        ))}
      </select>
      </>)}

      {!isSkipped && isCreatingNew && (
        <div style={{
          marginTop: "8px",
          padding: "8px 10px",
          background: "var(--bg-card)",
          border: "1px dashed var(--border-color)",
        }}>
          <div style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: "6px 10px",
          }}>
            <div style={{ gridColumn: "1 / span 2" }}>
              <label style={labelStyle()}>New question_key (lower_snake_case)</label>
              <input
                style={fieldStyle()}
                placeholder="e.g. approval_lai_overall"
                value={resolution._newKey || ""}
                onChange={(e) => setResolution({ ...resolution, _newKey: e.target.value })}
              />
            </div>
            <div>
              <label style={labelStyle()}>Family</label>
              <select
                style={fieldStyle()}
                value={resolution.family}
                onChange={(e) => setResolution({ ...resolution, family: e.target.value })}
              >
                <option value="">—</option>
                {FAMILIES.map((f) =>
                  <option key={f} value={f}>{FAMILY_LABELS[f] || f}</option>
                )}
              </select>
            </div>
            <div>
              <label style={labelStyle()}>Scale type</label>
              <select
                style={fieldStyle()}
                value={resolution.scale_type}
                onChange={(e) => setResolution({ ...resolution, scale_type: e.target.value })}
              >
                <option value="">—</option>
                {SCALE_TYPES.map((s) =>
                  <option key={s} value={s}>{s.replace(/_/g, " ")}</option>
                )}
              </select>
            </div>
            <div style={{ gridColumn: "1 / span 2" }}>
              <label style={labelStyle()}>Canonical wording (Chinese)</label>
              <textarea
                style={{ ...fieldStyle(), minHeight: "36px", fontFamily: "var(--font-body)" }}
                value={resolution.text_zh}
                onChange={(e) => setResolution({ ...resolution, text_zh: e.target.value })}
              />
            </div>
            <div style={{ gridColumn: "1 / span 2" }}>
              <label style={labelStyle()}>Canonical wording (English)</label>
              <textarea
                style={{ ...fieldStyle(), minHeight: "36px", fontFamily: "var(--font-body)" }}
                value={resolution.text_en}
                onChange={(e) => setResolution({ ...resolution, text_en: e.target.value })}
              />
            </div>
            <div style={{ gridColumn: "1 / span 2" }}>
              <label style={labelStyle()}>Description (optional)</label>
              <input
                style={fieldStyle()}
                value={resolution.description}
                onChange={(e) => setResolution({ ...resolution, description: e.target.value })}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function NewPollsterForm({ onCreated, onCancel }) {
  const [newRow, setNewRow] = useState({
    slug: "", name_en: "", name_zh: "", bias: "", status: "active",
  });
  const [busy, setBusy]   = useState(false);
  const [error, setError] = useState(null);

  const submit = async () => {
    const slug = newRow.slug.trim();
    if (!QUESTION_KEY_RX.test(slug)) {
      setError(`slug must match ^[a-z0-9][a-z0-9_]*$ (got ${JSON.stringify(slug)})`);
      return;
    }
    if (!newRow.name_en.trim()) { setError("name_en is required"); return; }
    if (!newRow.bias)           { setError("bias is required"); return; }
    setBusy(true);
    setError(null);
    try {
      const created = await createPollster({
        slug,
        name_en: newRow.name_en.trim(),
        name_zh: newRow.name_zh.trim() || undefined,
        bias:    newRow.bias,
        status:  newRow.status,
      });
      onCreated(created.slug, { ...newRow, slug });
    } catch (e) {
      setError(e.message || String(e));
      setBusy(false);
    }
  };

  return (
    <div style={{
      gridColumn: "1 / span 4",
      padding: "8px 10px",
      background: "var(--bg-card)",
      border: "1px dashed var(--border-color)",
      marginTop: "2px",
    }}>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 2fr 2fr 1fr 1fr", gap: "6px 10px" }}>
        <div>
          <label style={labelStyle()}>slug (lower_snake_case)</label>
          <input style={fieldStyle()} placeholder="e.g. apollo"
                 value={newRow.slug}
                 onChange={(e) => setNewRow({ ...newRow, slug: e.target.value })} />
        </div>
        <div>
          <label style={labelStyle()}>Name (English)</label>
          <input style={fieldStyle()} placeholder="Apollo Survey"
                 value={newRow.name_en}
                 onChange={(e) => setNewRow({ ...newRow, name_en: e.target.value })} />
        </div>
        <div>
          <label style={labelStyle()}>Name (Chinese)</label>
          <input style={fieldStyle()} placeholder="阿波羅民調"
                 value={newRow.name_zh}
                 onChange={(e) => setNewRow({ ...newRow, name_zh: e.target.value })} />
        </div>
        <div>
          <label style={labelStyle()}>Bias</label>
          <select style={fieldStyle()} value={newRow.bias}
                  onChange={(e) => setNewRow({ ...newRow, bias: e.target.value })}>
            <option value="">—</option>
            {POLLSTER_BIASES.map((b) => <option key={b} value={b}>{b}</option>)}
          </select>
        </div>
        <div>
          <label style={labelStyle()}>Status</label>
          <select style={fieldStyle()} value={newRow.status}
                  onChange={(e) => setNewRow({ ...newRow, status: e.target.value })}>
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

function EnvelopeFields({ draft, setDraft, rosterPollsters, onPollsterCreated }) {
  const pollsters = rosterPollsters || [];
  const [showCreate, setShowCreate] = useState(false);

  const handlePollsterChange = (val) => {
    if (val === CREATE_NEW_POLLSTER) {
      setShowCreate(true);
      // Don't change draft.pollster_slug yet — the inline form will set
      // it on successful create. Keep the current selection visible.
      return;
    }
    setDraft({ ...draft, pollster_slug: val });
  };

  return (
    <div style={{
      display: "grid",
      gridTemplateColumns: "2fr 1fr 1fr 1fr",
      gap: "6px 10px",
      marginBottom: "10px",
    }}>
      <div>
        <label style={labelStyle()}>Pollster</label>
        <select
          style={fieldStyle()}
          value={draft.pollster_slug}
          onChange={(e) => handlePollsterChange(e.target.value)}
        >
          {!pollsters.find((p) => p.slug === draft.pollster_slug) && draft.pollster_slug && (
            <option value={draft.pollster_slug}>{draft.pollster_slug} (current)</option>
          )}
          {pollsters.map((p) => (
            <option key={p.slug} value={p.slug}>
              {p.name_en || p.name_zh || p.slug} ({p.bias})
            </option>
          ))}
          <option value={CREATE_NEW_POLLSTER}>+ Create new pollster…</option>
        </select>
      </div>
      {showCreate && (
        <NewPollsterForm
          onCreated={(slug, row) => {
            // Parent owns the roster — push the new row up and adopt the
            // new slug as the current selection. Server returns the
            // canonical slug (trimmed); use that, not the raw input.
            onPollsterCreated?.({
              slug,
              name_en: row.name_en,
              name_zh: row.name_zh || null,
              bias:    row.bias,
              status:  row.status,
              approved_count: 0,
            });
            setDraft({ ...draft, pollster_slug: slug });
            setShowCreate(false);
          }}
          onCancel={() => setShowCreate(false)}
        />
      )}
      <div>
        <label style={labelStyle()}>Fielded start</label>
        <input
          type="date"
          style={fieldStyle()}
          value={draft.fielded_start}
          onChange={(e) => setDraft({ ...draft, fielded_start: e.target.value })}
        />
      </div>
      <div>
        <label style={labelStyle()}>Fielded end</label>
        <input
          type="date"
          style={fieldStyle()}
          value={draft.fielded_end}
          onChange={(e) => setDraft({ ...draft, fielded_end: e.target.value })}
        />
      </div>
      <div>
        <label style={labelStyle()}>Sample size</label>
        <input
          type="number"
          style={fieldStyle()}
          value={draft.sample_size}
          onChange={(e) => setDraft({ ...draft, sample_size: e.target.value })}
        />
      </div>

      <div style={{ gridColumn: "1 / span 4" }}>
        <label style={labelStyle()}>Methodology note (survey-level: mode, weighting, fielding window)</label>
        <input
          style={fieldStyle()}
          value={draft.methodology_note}
          onChange={(e) => setDraft({ ...draft, methodology_note: e.target.value })}
        />
      </div>

      <div style={{ gridColumn: "1 / span 3" }}>
        <label style={labelStyle()}>Source URL</label>
        <input
          style={fieldStyle()}
          value={draft.source_url}
          onChange={(e) => setDraft({ ...draft, source_url: e.target.value })}
        />
      </div>
      <div>
        <label style={labelStyle()}>Notes</label>
        <input
          style={fieldStyle()}
          value={draft.notes}
          onChange={(e) => setDraft({ ...draft, notes: e.target.value })}
        />
      </div>
    </div>
  );
}

// Build a minimal envelope override payload for /approve. Sending only
// fields the analyst touched keeps the server's "absent → keep current"
// semantics intact (e.g. an empty string in methodology_note becomes NULL
// only when the analyst actively cleared it).
function buildEnvelopeOverrides(draft, candidate) {
  const orig = envelopeDraftFrom(candidate);
  const out = {};
  for (const k of Object.keys(draft)) {
    if (draft[k] === orig[k]) continue;
    if (k === "sample_size") {
      out[k] = draft[k] === "" ? null : Number(draft[k]);
    } else {
      out[k] = draft[k];
    }
  }
  return out;
}

// Validate resolutions before hitting the network — same checks the
// server runs, surfaced inline so the analyst doesn't round-trip a 400.
function validateResolutions(resolutions) {
  if (!resolutions.some((r) => !r._skip)) {
    return "Every question is skipped — use Dismiss instead.";
  }
  for (let i = 0; i < resolutions.length; i++) {
    const r = resolutions[i];
    if (r._skip) continue;
    if (!r.question_key) return `Question ${i + 1}: pick a question_key.`;
    if (r.question_key === CREATE_NEW) {
      const key = (r._newKey || "").trim();
      if (!QUESTION_KEY_RX.test(key)) {
        return `Question ${i + 1}: new key must match ^[a-z0-9][a-z0-9_]*$ (got ${JSON.stringify(key)}).`;
      }
      if (!r.family)     return `Question ${i + 1}: family required for new key.`;
      if (!r.scale_type) return `Question ${i + 1}: scale_type required for new key.`;
      if (!r.text_zh && !r.text_en) {
        return `Question ${i + 1}: at least one of text_zh / text_en required for new key.`;
      }
    }
  }
  return null;
}

// Server-side approve body: order-aligned with pending_questions[].
function buildApproveBody(resolutions, envelopeOverrides, reviewedBy) {
  // Server expects an order-aligned entry for every pending question;
  // skipped ones come through with skip=true and an empty question_key,
  // which the server then drops from materialisation.
  const questions = resolutions.map((r) => {
    if (r._skip) {
      return { question_key: "", skip: true };
    }
    if (r.question_key === CREATE_NEW) {
      return {
        question_key: (r._newKey || "").trim(),
        text_zh:      r.text_zh || null,
        text_en:      r.text_en || null,
        family:       r.family,
        scale_type:   r.scale_type,
        description:  r.description || null,
      };
    }
    return { question_key: r.question_key };
  });
  return {
    questions,
    ...envelopeOverrides,
    ...(reviewedBy ? { reviewed_by: reviewedBy } : {}),
  };
}

function CandidateCard({ candidate, allKeys, rosterPollsters, mergeTargets, reviewedBy, onResolve, onApproveDone, onPollsterCreated }) {
  const [envelope,    setEnvelope]    = useState(() => envelopeDraftFrom(candidate));
  const [resolutions, setResolutions] = useState(() =>
    (candidate.pending_questions || []).map(resolutionDraftFor)
  );
  const [busy,        setBusy]        = useState(false);
  const [error,       setError]       = useState(null);
  const [mergeTarget, setMergeTarget] = useState("");

  const colour = pollsterChipColour(candidate.pollster_bias, candidate.pollster_slug);

  const setResolutionAt = (i, next) => {
    setResolutions((prev) => prev.map((r, idx) => (idx === i ? next : r)));
  };

  const handleApprove = async () => {
    const validationError = validateResolutions(resolutions);
    if (validationError) { setError(validationError); return; }
    setBusy(true);
    setError(null);
    try {
      const overrides = buildEnvelopeOverrides(envelope, candidate);
      const body = buildApproveBody(resolutions, overrides, reviewedBy);
      const result = await approvePoll(candidate.poll_id, body);
      // Approve has side effects (auto-merge of same-key pending OR
      // being merged into an existing approved twin). Either path
      // needs a full reload to show the resulting state — local
      // filtering would lie about what's still pending.
      const needsReload = result?.auto_merged > 0 || result?.status === "merged_into_existing";
      if (needsReload && onApproveDone) {
        onApproveDone(result.auto_merged || 0);
      } else {
        onResolve(candidate.poll_id);
      }
    } catch (e) {
      setError(e.message || String(e));
      setBusy(false);
    }
  };

  const handleDismiss = async () => {
    setBusy(true);
    setError(null);
    try {
      await dismissPoll(candidate.poll_id, reviewedBy);
      onResolve(candidate.poll_id);
    } catch (e) {
      setError(e.message || String(e));
      setBusy(false);
    }
  };

  const handleMerge = async () => {
    if (!mergeTarget) return;
    setBusy(true);
    setError(null);
    try {
      // If the analyst edited envelope fields, PATCH them through
      // before the merge so the dismissed-into-merged row carries the
      // correction (useful for audit; the surviving target keeps its
      // own values).
      const overrides = buildEnvelopeOverrides(envelope, candidate);
      if (Object.keys(overrides).length > 0) {
        await updatePoll(candidate.poll_id, overrides);
      }
      await mergePoll(candidate.poll_id, Number(mergeTarget), reviewedBy);
      onResolve(candidate.poll_id);
    } catch (e) {
      setError(e.message || String(e));
      setBusy(false);
    }
  };

  return (
    <div style={{
      padding: "12px 16px",
      borderBottom: "1px solid var(--border-color)",
      opacity: busy ? 0.55 : 1,
    }}>
      {/* Header — pollster chip, source link, confidence, created_at. */}
      <div style={{
        display: "flex", justifyContent: "space-between", alignItems: "baseline",
        marginBottom: "8px", gap: "8px", flexWrap: "wrap",
      }}>
        <div style={{ display: "flex", gap: "8px", alignItems: "baseline" }}>
          <PollsterChip
            slug={candidate.pollster_slug}
            name={candidate.pollster_name_en || candidate.pollster_name_zh || candidate.pollster_slug}
            bias={candidate.pollster_bias}
          />
          <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--text-muted)" }}>
            {candidate.fielded_start}{candidate.fielded_end && candidate.fielded_end !== candidate.fielded_start
              ? ` – ${candidate.fielded_end}` : ""}
          </span>
        </div>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--text-muted)" }}>
          {candidate.article?.url ? (
            <a href={candidate.article.url} target="_blank" rel="noreferrer"
               style={{ color: "var(--text-secondary)", textDecoration: "underline" }}>
              {candidate.article.source_name}
            </a>
          ) : <span>manual</span>}
          {candidate.article?.published_at &&
            <span> · {candidate.article.published_at.slice(0, 10)}</span>}
          {candidate.confidence != null &&
            <span> · conf {Number(candidate.confidence).toFixed(2)}</span>}
        </div>
      </div>

      <EnvelopeFields draft={envelope} setDraft={setEnvelope}
                      rosterPollsters={rosterPollsters}
                      onPollsterCreated={onPollsterCreated} />

      {(candidate.pending_questions || []).map((pq, i) => (
        <QuestionResolver
          key={i}
          idx={i}
          pendingQuestion={pq}
          allKeys={allKeys}
          resolution={resolutions[i]}
          setResolution={(next) => setResolutionAt(i, next)}
        />
      ))}

      {error && (
        <div style={{
          color: "var(--accent-red)",
          fontFamily: "var(--font-mono)", fontSize: "10px",
          marginBottom: "6px",
        }}>
          {error}
        </div>
      )}

      <div style={{
        display: "flex", gap: "6px", alignItems: "center", flexWrap: "wrap",
        marginTop: "8px",
      }}>
        <button disabled={busy} onClick={handleApprove} style={{
          padding: "5px 12px", fontFamily: "var(--font-mono)",
          fontSize: "10px", letterSpacing: "0.08em", textTransform: "uppercase",
          background: "#16a34a", color: "#fff", border: "none",
          cursor: busy ? "not-allowed" : "pointer",
        }}>
          Approve
        </button>
        <button disabled={busy} onClick={handleDismiss} style={{
          padding: "5px 12px", fontFamily: "var(--font-mono)",
          fontSize: "10px", letterSpacing: "0.08em", textTransform: "uppercase",
          background: "transparent", color: "var(--text-secondary)",
          border: "1px solid var(--border-color)",
          cursor: busy ? "not-allowed" : "pointer",
        }}>
          Dismiss
        </button>

        <select value={mergeTarget}
                onChange={(e) => setMergeTarget(e.target.value)}
                style={{ ...fieldStyle(), width: "260px", marginLeft: "auto" }}>
          <option value="">Merge into…</option>
          {mergeTargets.map((t) => (
            <option key={t.poll_id} value={t.poll_id}>
              {t.pollster_name_en || t.pollster_slug} · {t.fielded_start}
              {t.questions?.[0]?.question_key ? ` · ${t.questions[0].question_key}` : ""}
            </option>
          ))}
        </select>
        <button disabled={busy || !mergeTarget} onClick={handleMerge} style={{
          padding: "5px 10px", fontFamily: "var(--font-mono)",
          fontSize: "10px", letterSpacing: "0.08em", textTransform: "uppercase",
          background: "transparent",
          color: mergeTarget ? "var(--text-primary)" : "var(--text-muted)",
          border: "1px solid var(--border-color)",
          cursor: busy || !mergeTarget ? "not-allowed" : "pointer",
        }}>
          Merge
        </button>
      </div>
    </div>
  );
}

export default function PollReviewQueue({ onClose, onResolveAll, reviewedBy }) {
  const [candidates,    setCandidates]    = useState(null);   // null = loading, [] = empty, [...] = rows
  const [allKeys,       setAllKeys]       = useState([]);
  const [rosterPollsters, setRoster]      = useState([]);
  const [mergeTargets,  setMergeTargets]  = useState([]);
  const [topError,      setTopError]      = useState(null);

  const loadCandidates = () => {
    fetchPollCandidates()
      .then((r) => {
        setCandidates(r.candidates || []);
        setAllKeys(r.question_keys || []);
      })
      .catch((e) => setTopError(e.message || String(e)));
  };

  useEffect(() => {
    loadCandidates();
    // Pollster roster for the envelope dropdown — every active pollster
    // shows even if it has zero approved polls (roster endpoint LEFT JOINs).
    fetchPollsRoster()
      .then((r) => setRoster(r.pollsters || []))
      .catch(() => setRoster([]));
    // Recent approved polls = merge target pool. 100 is plenty; the
    // duplicate cases analysts hit are usually within days of each other.
    fetchPolls({ limit: 100 })
      .then((r) => setMergeTargets(r.polls || []))
      .catch(() => setMergeTargets([]));
  }, []);

  const onResolve = (resolvedId) => {
    setCandidates((prev) => {
      const next = (prev || []).filter((c) => c.poll_id !== resolvedId);
      if (next.length === 0 && onResolveAll) onResolveAll();
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
        borderTop: "4px solid #d4a94a",
        borderRadius: "4px",
        width: 880, maxWidth: "94vw", maxHeight: "88vh",
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
              Poll candidates
            </span>
            <span style={{ fontSize: "10px", color: "var(--text-muted)", marginLeft: "10px" }}>
              {candidates ? `${candidates.length} pending` : "…"}
            </span>
          </div>
          <button onClick={onClose} style={{
            background: "none", border: "none", cursor: "pointer",
            color: "var(--text-muted)", fontSize: "16px", padding: "2px 4px",
          }}>
            ✕
          </button>
        </div>

        <div style={{ overflowY: "auto", padding: "8px 0" }}>
          {topError ? (
            <div style={{ padding: "24px 16px", color: "var(--accent-red)",
                          fontFamily: "var(--font-mono)", fontSize: "12px" }}>
              {topError}
            </div>
          ) : candidates === null ? (
            <div style={{ padding: "24px 16px", color: "var(--text-muted)",
                          fontFamily: "var(--font-mono)", fontSize: "12px" }}>
              Loading…
            </div>
          ) : candidates.length === 0 ? (
            <div style={{ padding: "24px 16px", color: "var(--text-muted)",
                          fontFamily: "var(--font-mono)", fontSize: "12px", fontStyle: "italic" }}>
              No pending candidates.
            </div>
          ) : (
            candidates.map((c) => (
              <CandidateCard
                key={c.poll_id}
                candidate={c}
                allKeys={allKeys}
                rosterPollsters={rosterPollsters}
                mergeTargets={mergeTargets}
                reviewedBy={reviewedBy}
                onResolve={onResolve}
                onApproveDone={loadCandidates}
                onPollsterCreated={(p) => setRoster((prev) => [...prev, p])}
              />
            ))
          )}
        </div>
      </div>
    </div>
  );
}
