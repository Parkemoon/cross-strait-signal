import { useEffect, useState } from "react";
import { fetchAltModelSummary } from "../api";
import { modelLabel, armLabel, modelTint, modelTintRgba, isRetiredModel } from "../altModels";
import { MICRO, META_LINE } from "./adminChrome";

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
//
// Phase 2B restyle: a segmented control in the design's button language
// (Archivo micro-caps, hair borders, active = solid) on a hairline row;
// an active lens keeps the model's tint so a lensed feed is never mistaken
// for production.

const SEG = {
  fontFamily: "var(--font-mono)", fontSize: "9px", letterSpacing: "0.14em", textTransform: "uppercase",
  padding: "6px 12px", cursor: "pointer", lineHeight: 1, border: "none", background: "transparent",
  color: "var(--muted)", transition: "color 0.12s, background-color 0.12s",
};

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
        display: "flex", alignItems: "center", gap: "12px", flexWrap: "wrap",
        marginBottom: "14px", padding: "8px 0",
        borderTop: "1px solid var(--hair)", borderBottom: "1px solid var(--hair)",
        background: lens ? modelTintRgba(current.model, 0.05) : "transparent",
      }}
      onClick={(e) => e.stopPropagation()}
    >
      <span style={{ ...MICRO, color: "var(--ink)", fontWeight: 600, letterSpacing: "0.2em", paddingLeft: "2px" }}>
        Model lens
      </span>
      {groups.length > 1 && (
        <select
          value={`${current.model}|${current.arm}`}
          onChange={pickCombo}
          className="field"
          style={{
            fontFamily: "var(--font-mono)", fontSize: "10px", letterSpacing: "0.06em",
            padding: "4px 8px", background: "var(--bg)", color: "var(--ink)",
            border: "1px solid var(--hair)", borderRadius: 0, cursor: "pointer",
          }}
        >
          {groups.map((g) => (
            <option key={`${g.model}|${g.arm}`} value={`${g.model}|${g.arm}`}>
              {modelLabel(g.model)} · {armLabel(g.arm)} ({g.total})
            </option>
          ))}
        </select>
      )}
      <span style={{ display: "inline-flex", border: "1px solid var(--hair)", borderRadius: 0 }}>
        {[
          ["gemini", "Gemini only"],
          ["model", `${modelLabel(current.model)} only`],
          ["both", "Both"],
        ].map(([key, label], i) => {
          const on = mode === key;
          return (
            <button
              key={key}
              onClick={() => setMode(key)}
              aria-pressed={on}
              style={{
                ...SEG,
                // Divider between segments — without it adjacent inactive
                // segments read as one button.
                borderLeft: i > 0 ? "1px solid var(--hair)" : "none",
                background: on ? (key === "gemini" ? "var(--ink)" : tint) : "transparent",
                color: on ? "var(--bg)" : "var(--muted)",
              }}
            >
              {label}
            </button>
          );
        })}
      </span>
      {mode !== "gemini" && (
        <span style={META_LINE}>
          {armLabel(current.arm).toUpperCase()} · {current.total} SWEPT ARTICLES
          {mode === "both" ? " · AMBER = TOPIC DIVERGES" : ""}
        </span>
      )}
    </div>
  );
}
