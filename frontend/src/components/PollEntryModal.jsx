import { useEffect, useMemo, useState } from "react";
import {
  createPoll,
  fetchPollsRoster,
  fetchPollQuestions,
} from "../api";
import { FAMILY_LABELS } from "./PollsTab";
import {
  FAMILIES, SCALE_TYPES, SLUG_RX,
  CREATE_NEW, CREATE_NEW_POLLSTER,
  fieldStyle, labelStyle, groupKeysByFamily,
  NewPollsterForm,
} from "./pollFormShared";

function emptyOption() {
  return { label_zh: "", label_en: "", percentage: "" };
}

function emptyQuestion() {
  return {
    question_key: "",
    _newKey:      "",
    text_zh:      "",
    text_en:      "",
    family:       "",
    scale_type:   "",
    description:  "",
    options:      [emptyOption(), emptyOption()],
  };
}

function QuestionEditor({ idx, question, allKeys, onChange, onRemove, canRemove }) {
  const grouped = useMemo(() => groupKeysByFamily(allKeys), [allKeys]);
  const isCreatingNew = question.question_key === CREATE_NEW;

  // When the analyst picks an existing key, blank out the new-key
  // creation fields so a half-filled new-key form doesn't get sent.
  const pickExisting = (key) => {
    if (key === CREATE_NEW) {
      onChange({ ...question, question_key: CREATE_NEW });
      return;
    }
    onChange({
      ...question,
      question_key: key,
      _newKey: "", text_zh: "", text_en: "",
      family: "", scale_type: "", description: "",
    });
  };

  const setOption = (i, next) => {
    onChange({ ...question, options: question.options.map((o, j) => (i === j ? next : o)) });
  };
  const addOption = () => {
    onChange({ ...question, options: [...question.options, emptyOption()] });
  };
  const removeOption = (i) => {
    onChange({ ...question, options: question.options.filter((_, j) => j !== i) });
  };

  return (
    <div style={{
      border: "1px solid var(--border-color)",
      padding: "10px 12px",
      marginBottom: "8px",
      background: "var(--bg-primary)",
    }}>
      <div style={{
        display: "flex", justifyContent: "space-between", alignItems: "center",
        marginBottom: "8px",
      }}>
        <span style={{
          fontFamily: "var(--font-mono)",
          fontSize: "9.5px",
          letterSpacing: "0.06em",
          textTransform: "uppercase",
          color: "var(--text-muted)",
        }}>
          Question {idx + 1}
        </span>
        {canRemove && (
          <button
            onClick={onRemove}
            style={{
              padding: "2px 8px", fontFamily: "var(--font-mono)",
              fontSize: "9px", letterSpacing: "0.06em", textTransform: "uppercase",
              background: "transparent", color: "var(--text-muted)",
              border: "1px solid var(--border-color)", cursor: "pointer",
            }}
          >Remove</button>
        )}
      </div>

      <label style={labelStyle()}>Canonical question_key</label>
      <select
        style={fieldStyle()}
        value={question.question_key}
        onChange={(e) => pickExisting(e.target.value)}
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

      {isCreatingNew && (
        <div style={{
          marginTop: "8px",
          padding: "8px 10px",
          background: "var(--bg-card)",
          border: "1px dashed var(--border-color)",
        }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "6px 10px" }}>
            <div style={{ gridColumn: "1 / span 2" }}>
              <label style={labelStyle()}>New question_key (lower_snake_case)</label>
              <input
                style={fieldStyle()}
                placeholder="e.g. approval_lai_overall"
                value={question._newKey}
                onChange={(e) => onChange({ ...question, _newKey: e.target.value })}
              />
            </div>
            <div>
              <label style={labelStyle()}>Family</label>
              <select
                style={fieldStyle()}
                value={question.family}
                onChange={(e) => onChange({ ...question, family: e.target.value })}
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
                value={question.scale_type}
                onChange={(e) => onChange({ ...question, scale_type: e.target.value })}
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
                value={question.text_zh}
                onChange={(e) => onChange({ ...question, text_zh: e.target.value })}
              />
            </div>
            <div style={{ gridColumn: "1 / span 2" }}>
              <label style={labelStyle()}>Canonical wording (English)</label>
              <textarea
                style={{ ...fieldStyle(), minHeight: "36px", fontFamily: "var(--font-body)" }}
                value={question.text_en}
                onChange={(e) => onChange({ ...question, text_en: e.target.value })}
              />
            </div>
            <div style={{ gridColumn: "1 / span 2" }}>
              <label style={labelStyle()}>Description (optional)</label>
              <input
                style={fieldStyle()}
                value={question.description}
                onChange={(e) => onChange({ ...question, description: e.target.value })}
              />
            </div>
          </div>
        </div>
      )}

      {/* Options grid — analyst enters label_zh / label_en / percentage
          per row. option_order defaults to array index on the server. */}
      <div style={{ marginTop: "10px" }}>
        <label style={labelStyle()}>Options</label>
        {question.options.map((opt, i) => (
          <div key={i} style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr 80px 24px",
            gap: "6px",
            marginBottom: "4px",
          }}>
            <input
              style={fieldStyle()}
              placeholder="label (中文)"
              value={opt.label_zh}
              onChange={(e) => setOption(i, { ...opt, label_zh: e.target.value })}
            />
            <input
              style={fieldStyle()}
              placeholder="label (English)"
              value={opt.label_en}
              onChange={(e) => setOption(i, { ...opt, label_en: e.target.value })}
            />
            <input
              type="number"
              step="0.1"
              min="0"
              max="100"
              style={fieldStyle()}
              placeholder="%"
              value={opt.percentage}
              onChange={(e) => setOption(i, { ...opt, percentage: e.target.value })}
            />
            <button
              onClick={() => removeOption(i)}
              disabled={question.options.length <= 1}
              title="Remove option"
              style={{
                background: "transparent", color: "var(--text-muted)",
                border: "1px solid var(--border-color)",
                cursor: question.options.length <= 1 ? "not-allowed" : "pointer",
                fontFamily: "var(--font-mono)", fontSize: "11px",
              }}
            >×</button>
          </div>
        ))}
        <button
          onClick={addOption}
          style={{
            padding: "4px 10px", fontFamily: "var(--font-mono)", fontSize: "10px",
            letterSpacing: "0.06em", textTransform: "uppercase",
            background: "transparent", color: "var(--text-secondary)",
            border: "1px dashed var(--border-color)", cursor: "pointer",
            marginTop: "4px",
          }}
        >+ Add option</button>
      </div>
    </div>
  );
}

// Validates the modal-side draft against the server's contract, so the
// analyst sees a useful inline error instead of a 400. Mirrors the
// checks in api/routes/polls.py: pollster + fielded_start required,
// at least one question, per-question key shape + new-key fields,
// per-option label + numeric 0–100 percentage.
function validateDraft(envelope, questions) {
  if (!envelope.pollster_slug) return "Pollster is required.";
  if (!envelope.fielded_start) return "Fielded start date is required.";
  if (questions.length === 0)  return "Add at least one question.";

  for (let i = 0; i < questions.length; i++) {
    const q = questions[i];
    if (!q.question_key) return `Question ${i + 1}: pick a question_key.`;
    if (q.question_key === CREATE_NEW) {
      const key = (q._newKey || "").trim();
      if (!SLUG_RX.test(key)) {
        return `Question ${i + 1}: new key must match ^[a-z0-9][a-z0-9_]*$ (got ${JSON.stringify(key)}).`;
      }
      if (!q.family)     return `Question ${i + 1}: family required for new key.`;
      if (!q.scale_type) return `Question ${i + 1}: scale_type required for new key.`;
      if (!q.text_zh && !q.text_en) {
        return `Question ${i + 1}: at least one of text_zh / text_en required for new key.`;
      }
    }
    const opts = q.options || [];
    if (opts.length === 0) return `Question ${i + 1}: at least one option required.`;
    for (let j = 0; j < opts.length; j++) {
      const o = opts[j];
      if (!o.label_zh.trim() && !o.label_en.trim()) {
        return `Question ${i + 1} option ${j + 1}: label (zh or en) required.`;
      }
      const pct = Number(o.percentage);
      if (o.percentage === "" || Number.isNaN(pct)) {
        return `Question ${i + 1} option ${j + 1}: percentage must be numeric.`;
      }
      if (pct < 0 || pct > 100) {
        return `Question ${i + 1} option ${j + 1}: percentage ${pct} outside 0–100.`;
      }
    }
  }
  return null;
}

function buildSubmitBody(envelope, questions, reviewedBy) {
  const trim = (s) => (s || "").trim();
  return {
    pollster_slug:    envelope.pollster_slug,
    fielded_start:    envelope.fielded_start,
    fielded_end:      trim(envelope.fielded_end) || undefined,
    sample_size:      envelope.sample_size === "" ? undefined : Number(envelope.sample_size),
    methodology_note: trim(envelope.methodology_note) || undefined,
    source_url:       trim(envelope.source_url) || undefined,
    notes:            trim(envelope.notes) || undefined,
    reviewed_by:      reviewedBy || undefined,
    questions: questions.map((q) => {
      const newKey = q.question_key === CREATE_NEW;
      return {
        question_key: newKey ? trim(q._newKey) : q.question_key,
        text_zh:      newKey ? (trim(q.text_zh) || undefined) : undefined,
        text_en:      newKey ? (trim(q.text_en) || undefined) : undefined,
        family:       newKey ? q.family : undefined,
        scale_type:   newKey ? q.scale_type : undefined,
        description:  newKey ? (trim(q.description) || undefined) : undefined,
        options: q.options.map((o, idx) => ({
          label_zh:     trim(o.label_zh) || undefined,
          label_en:     trim(o.label_en) || undefined,
          option_order: idx,
          percentage:   Number(o.percentage),
        })),
      };
    }),
  };
}

export default function PollEntryModal({ onClose, onCreated, reviewedBy }) {
  const [envelope, setEnvelope] = useState({
    pollster_slug:    "",
    fielded_start:    "",
    fielded_end:      "",
    sample_size:      "",
    methodology_note: "",
    source_url:       "",
    notes:            "",
  });
  const [questions, setQuestions]       = useState(() => [emptyQuestion()]);
  const [roster, setRoster]             = useState([]);
  const [allKeys, setAllKeys]           = useState([]);
  const [showCreate, setShowCreate]     = useState(false);
  const [busy, setBusy]                 = useState(false);
  const [error, setError]               = useState(null);

  // Roster for the pollster dropdown + question_key catalogue for the
  // per-question picker. Two independent reads, both cheap and public.
  useEffect(() => {
    fetchPollsRoster()
      .then((r) => setRoster(r.pollsters || []))
      .catch(() => setRoster([]));
    fetchPollQuestions()
      .then((r) => setAllKeys(r.question_keys || []))
      .catch(() => setAllKeys([]));
  }, []);

  const handlePollsterChange = (val) => {
    if (val === CREATE_NEW_POLLSTER) {
      setShowCreate(true);
      return;
    }
    setEnvelope({ ...envelope, pollster_slug: val });
  };

  const updateQuestion = (i, next) => {
    setQuestions((prev) => prev.map((q, idx) => (idx === i ? next : q)));
  };
  const addQuestion = () => setQuestions((prev) => [...prev, emptyQuestion()]);
  const removeQuestion = (i) =>
    setQuestions((prev) => prev.filter((_, idx) => idx !== i));

  const handleSubmit = async () => {
    const v = validateDraft(envelope, questions);
    if (v) { setError(v); return; }
    setBusy(true);
    setError(null);
    try {
      const body = buildSubmitBody(envelope, questions, reviewedBy);
      const result = await createPoll(body);
      onCreated?.(result);
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
        borderTop: "4px solid #0f766e",
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
              Add poll manually
            </span>
            <span style={{ fontSize: "10px", color: "var(--text-muted)", marginLeft: "10px" }}>
              skips pending — lands as approved
            </span>
          </div>
          <button onClick={onClose} disabled={busy}
                  style={{ background: "none", border: "none",
                           cursor: busy ? "default" : "pointer",
                           color: "var(--text-muted)", fontSize: "16px", padding: "2px 4px" }}>
            ✕
          </button>
        </div>

        <div style={{ overflowY: "auto", padding: "14px 16px", opacity: busy ? 0.55 : 1 }}>
          <div style={{
            display: "grid",
            gridTemplateColumns: "2fr 1fr 1fr 1fr",
            gap: "6px 10px",
            marginBottom: "12px",
          }}>
            <div>
              <label style={labelStyle()}>Pollster</label>
              <select
                style={fieldStyle()}
                value={envelope.pollster_slug}
                onChange={(e) => handlePollsterChange(e.target.value)}
              >
                <option value="">— pick a pollster —</option>
                {roster.map((p) => (
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
                  setRoster((prev) => [...prev, {
                    slug, name_en: row.name_en, name_zh: row.name_zh || null,
                    bias: row.bias, status: row.status, approved_count: 0,
                  }]);
                  setEnvelope((env) => ({ ...env, pollster_slug: slug }));
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
                value={envelope.fielded_start}
                onChange={(e) => setEnvelope({ ...envelope, fielded_start: e.target.value })}
              />
            </div>
            <div>
              <label style={labelStyle()}>Fielded end</label>
              <input
                type="date"
                style={fieldStyle()}
                value={envelope.fielded_end}
                onChange={(e) => setEnvelope({ ...envelope, fielded_end: e.target.value })}
              />
            </div>
            <div>
              <label style={labelStyle()}>Sample size</label>
              <input
                type="number"
                style={fieldStyle()}
                value={envelope.sample_size}
                onChange={(e) => setEnvelope({ ...envelope, sample_size: e.target.value })}
              />
            </div>
            <div style={{ gridColumn: "1 / span 4" }}>
              <label style={labelStyle()}>Methodology note (survey-level: mode, weighting, fielding window)</label>
              <input
                style={fieldStyle()}
                value={envelope.methodology_note}
                onChange={(e) => setEnvelope({ ...envelope, methodology_note: e.target.value })}
              />
            </div>
            <div style={{ gridColumn: "1 / span 3" }}>
              <label style={labelStyle()}>Source URL</label>
              <input
                style={fieldStyle()}
                value={envelope.source_url}
                onChange={(e) => setEnvelope({ ...envelope, source_url: e.target.value })}
              />
            </div>
            <div>
              <label style={labelStyle()}>Notes</label>
              <input
                style={fieldStyle()}
                value={envelope.notes}
                onChange={(e) => setEnvelope({ ...envelope, notes: e.target.value })}
              />
            </div>
          </div>

          {questions.map((q, i) => (
            <QuestionEditor
              key={i}
              idx={i}
              question={q}
              allKeys={allKeys}
              onChange={(next) => updateQuestion(i, next)}
              onRemove={() => removeQuestion(i)}
              canRemove={questions.length > 1}
            />
          ))}

          <button
            onClick={addQuestion}
            style={{
              padding: "4px 12px", fontFamily: "var(--font-mono)", fontSize: "10px",
              letterSpacing: "0.06em", textTransform: "uppercase",
              background: "transparent", color: "var(--text-secondary)",
              border: "1px dashed var(--border-color)", cursor: "pointer",
              marginBottom: "10px",
            }}
          >+ Add question</button>

          {error && (
            <div style={{
              color: "var(--accent-red)",
              fontFamily: "var(--font-mono)", fontSize: "10px",
              marginTop: "8px", marginBottom: "8px",
            }}>
              {error}
            </div>
          )}
        </div>

        <div style={{
          display: "flex", gap: "6px", alignItems: "center",
          padding: "12px 16px", borderTop: "1px solid var(--border-color)",
        }}>
          <button disabled={busy} onClick={handleSubmit} style={{
            padding: "5px 14px", fontFamily: "var(--font-mono)",
            fontSize: "10px", letterSpacing: "0.08em", textTransform: "uppercase",
            background: "#16a34a", color: "#fff", border: "none",
            cursor: busy ? "not-allowed" : "pointer",
          }}>
            Save poll
          </button>
          <button disabled={busy} onClick={onClose} style={{
            padding: "5px 14px", fontFamily: "var(--font-mono)",
            fontSize: "10px", letterSpacing: "0.08em", textTransform: "uppercase",
            background: "transparent", color: "var(--text-secondary)",
            border: "1px solid var(--border-color)",
            cursor: busy ? "not-allowed" : "pointer",
          }}>
            Cancel
          </button>
          <span style={{
            marginLeft: "auto", fontFamily: "var(--font-mono)", fontSize: "10px",
            color: "var(--text-muted)",
          }}>
            One envelope · {questions.length} question{questions.length === 1 ? "" : "s"}
          </span>
        </div>
      </div>
    </div>
  );
}
