import { useEffect, useState } from "react";
import { fetchAltModelSummary } from "../api";
import { modelLabel, armLabel, modelTint, modelTintRgba, isRetiredModel } from "../altModels";

// Feed-level model lens (admin only — parent gates on !READ_ONLY).
// Three views over the Signal Feed:
//   Gemini only  — production feed, untouched.
//   <model> only — the swept (model, arm)'s classifications replace
//                  production's, no Gemini chrome on the cards.
//   Both         — production primary, the model's output alongside.
// Options come from /api/alt-models/summary, so only combinations that
// actually have sweep rows are offered. The model/both views narrow the
// feed to swept articles (server-side INNER JOIN) — until the corpus is
// fully re-run, that subset is much smaller than the feed.

export default function AltModelLens({ lens, onChange, dual, onDualChange }) {
  const [groups, setGroups] = useState([]);
  // Which swept (model, arm) the model/both views use — only surfaced as a
  // dropdown when more than one combo has sweep rows.
  const [combo, setCombo] = useState(null);

  useEffect(() => {
    fetchAltModelSummary()
      // The gemini-control arm is the tab's calibration baseline, not a feed
      // lens — viewing the feed "through Gemini" is what the Gemini-only
      // segment already means. Offer only real alt-model arms here.
      .then((d) => setGroups((d?.groups || [])
        .filter((g) => !isRetiredModel(g.model) && g.arm !== "control")))
      .catch(() => setGroups([]));
  }, []);

  // No sweeps recorded → nothing to offer; keep the feed chrome unchanged.
  if (groups.length === 0) return null;

  const active = lens
    ? groups.find((g) => g.model === lens.model && g.arm === lens.arm)
    : null;
  const current = active || combo || groups[0];
  const mode = lens ? (dual ? "both" : "model") : "gemini";
  const tint = modelTint(current.model);

  const setMode = (m) => {
    if (m === "gemini") {
      onChange(null);
      return;
    }
    onDualChange(m === "both");
    onChange({ model: current.model, arm: current.arm });
  };

  const pickCombo = (e) => {
    const [model, arm] = e.target.value.split("|");
    const g = groups.find((x) => x.model === model && x.arm === arm);
    if (!g) return;
    setCombo(g);
    if (lens) onChange({ model: g.model, arm: g.arm });
  };

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: "10px",
        flexWrap: "wrap",
        marginBottom: "14px",
        padding: "8px 10px",
        border: lens ? `1px solid ${tint}` : "1px dashed var(--border-color)",
        background: lens ? modelTintRgba(current.model, 0.05) : "transparent",
      }}
      onClick={(e) => e.stopPropagation()}
    >
      <span style={{
        fontSize: "10px",
        fontFamily: "var(--font-mono)",
        color: "var(--text-muted)",
        textTransform: "uppercase",
        letterSpacing: "1px",
      }}>
        Model lens
      </span>
      {groups.length > 1 && (
        <select
          value={`${current.model}|${current.arm}`}
          onChange={pickCombo}
          style={{
            padding: "4px 8px",
            background: "var(--bg-card)",
            color: "var(--text-primary)",
            border: "1px solid var(--border-color)",
            borderRadius: "3px",
            fontSize: "12px",
            fontFamily: "var(--font-mono)",
            cursor: "pointer",
          }}
        >
          {groups.map((g) => (
            <option key={`${g.model}|${g.arm}`} value={`${g.model}|${g.arm}`}>
              {modelLabel(g.model)} · {armLabel(g.arm)} ({g.total})
            </option>
          ))}
        </select>
      )}
      <span style={{
        display: "inline-flex",
        border: "1px solid var(--border-color)",
        borderRadius: "3px",
        overflow: "hidden",
      }}>
        {[
          ["gemini", "Gemini only"],
          ["model", `${modelLabel(current.model)} only`],
          ["both", "Both"],
        ].map(([key, label], i) => (
          <button
            key={key}
            onClick={() => setMode(key)}
            style={{
              padding: "3px 10px",
              fontSize: "11px",
              fontFamily: "var(--font-mono)",
              cursor: "pointer",
              border: "none",
              // Divider between segments — without it adjacent inactive
              // segments read as one button.
              borderLeft: i > 0 ? "1px solid var(--border-color)" : "none",
              background: mode === key
                ? (key === "gemini" ? "#6b7280" : tint)
                : "transparent",
              color: mode === key ? "#fff" : "var(--text-muted)",
            }}
          >
            {label}
          </button>
        ))}
      </span>
      {mode !== "gemini" && (
        <span style={{
          fontSize: "10px",
          fontFamily: "var(--font-mono)",
          color: "var(--text-muted)",
        }}>
          {armLabel(current.arm)} · {current.total} swept articles
          {mode === "both" ? " · amber = topic diverges" : ""}
        </span>
      )}
    </div>
  );
}
