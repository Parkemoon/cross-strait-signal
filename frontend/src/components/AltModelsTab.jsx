import React, { useEffect, useState } from "react";
import { fetchAltModelSummary, fetchAltModelRefusals } from "../api";

// Alt-model experiment aggregate view (admin only — App.js gates on !READ_ONLY).
// Divergence aggregates + refusal browser over alt_model_analysis rows.
// Refusal rate is NOT the sole censorship metric: sanitised-but-answered
// output only shows in topic-agreement / score-delta numbers.

const MODEL_LABELS = {
  "deepseek/deepseek-v4-flash": "DeepSeek V4 Flash",
  "moonshotai/kimi-k3": "Kimi K3",
};

const ARM_LABELS = {
  neutral: "Neutral host",
  originator: "Originator endpoint",
  control: "Gemini control",
};

const tileLabel = {
  fontSize: "10px", fontFamily: "var(--font-mono)", color: "var(--text-muted)",
  textTransform: "uppercase", letterSpacing: "1px", marginBottom: "4px",
};
const tileValue = { fontSize: "20px", fontFamily: "var(--font-mono)", fontWeight: 600 };

function pct(x) {
  return x === null || x === undefined ? "—" : `${(x * 100).toFixed(1)}%`;
}

function GroupCard({ g }) {
  const o = g.by_outcome;
  const refusalPct = g.total ? (o.refused / g.total) : 0;
  return (
    <div style={{
      border: "1px solid var(--border-subtle, rgba(0,0,0,0.1))", borderRadius: "6px",
      padding: "16px", marginBottom: "16px", background: "var(--bg-card, transparent)",
    }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: "10px", marginBottom: "12px", flexWrap: "wrap" }}>
        <span style={{ fontSize: "14px", fontWeight: 700 }}>
          {MODEL_LABELS[g.model] || g.model}
        </span>
        <span style={{ fontSize: "11px", fontFamily: "var(--font-mono)", color: "var(--text-muted)" }}>
          {ARM_LABELS[g.arm] || g.arm} · {g.total} articles
        </span>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))", gap: "12px" }}>
        <div>
          <div style={tileLabel}>Outcomes</div>
          <div style={{ fontSize: "12px", fontFamily: "var(--font-mono)", lineHeight: 1.7 }}>
            ok {o.ok} · <span style={{ color: "#dc2626" }}>refused {o.refused}</span>
            <br />parse {o.parse_error} · api {o.api_error}
          </div>
        </div>
        <div>
          <div style={tileLabel}>Refusal rate</div>
          <div style={{ ...tileValue, color: refusalPct > 0.02 ? "#dc2626" : "inherit" }}>
            {pct(refusalPct)}
          </div>
        </div>
        <div>
          <div style={tileLabel}>Topic agreement</div>
          <div style={tileValue}>{pct(g.topic_agreement)}</div>
        </div>
        <div>
          <div style={tileLabel}>Mean |Δ score|</div>
          <div style={tileValue}>
            {g.mean_abs_score_delta == null ? "—" : g.mean_abs_score_delta.toFixed(3)}
          </div>
        </div>
        <div>
          <div style={tileLabel}>Score bias</div>
          <div style={tileValue} title="mean signed (alt − Gemini) on the sentiment axis; positive = alt scores more cooperative, negative = more hostile">
            {g.mean_score_bias == null ? "—"
              : `${g.mean_score_bias >= 0 ? "+" : ""}${g.mean_score_bias.toFixed(3)}`}
          </div>
        </div>
      </div>

      {Object.keys(g.refusals_by_topic || {}).length > 0 && (
        <div style={{ marginTop: "12px" }}>
          <div style={tileLabel}>Refusals by topic</div>
          <div style={{ fontSize: "11px", fontFamily: "var(--font-mono)", color: "var(--text-secondary)" }}>
            {Object.entries(g.refusals_by_topic).map(([t, n]) => `${t} ×${n}`).join(" · ")}
          </div>
        </div>
      )}
    </div>
  );
}

export default function AltModelsTab() {
  const [summary, setSummary] = useState(null);
  const [refusals, setRefusals] = useState([]);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchAltModelSummary().then((d) => setSummary(d?.groups || [])).catch((e) => setError(String(e)));
    fetchAltModelRefusals({ limit: 50 }).then((d) => setRefusals(d?.rows || [])).catch(() => {});
  }, []);

  return (
    <div>
      <h2 style={{ fontSize: "16px", marginBottom: "4px" }}>Alternate Model Experiment</h2>
      <p style={{ fontSize: "12px", color: "var(--text-muted)", marginBottom: "20px", maxWidth: "640px" }}>
        Approved articles re-analysed by Chinese open-weights models through the identical
        production Tier-1 prompt. Neutral-host arms run the public weights on Western
        infrastructure (trained alignment only); originator arms hit the model creator's
        own endpoint (alignment + serving-layer filtering). Decoding config is
        approximated, not identical, to production Gemini.
      </p>

      {error && <div style={{ color: "#dc2626", fontSize: "12px" }}>{error}</div>}
      {summary && summary.length === 0 && (
        <div style={{ fontSize: "13px", color: "var(--text-muted)" }}>
          No sweeps recorded yet — run <code>scripts/sweep_alt_models.py</code>.
        </div>
      )}
      {(summary || []).map((g) => <GroupCard key={`${g.model}|${g.arm}`} g={g} />)}

      {refusals.length > 0 && (
        <div style={{ marginTop: "24px" }}>
          <h3 style={{ fontSize: "13px", textTransform: "uppercase", letterSpacing: "1px", fontFamily: "var(--font-mono)", color: "var(--text-muted)", marginBottom: "10px" }}>
            Refusal browser
          </h3>
          {refusals.map((r) => (
            <div key={r.id} style={{
              borderLeft: "3px solid #dc2626", padding: "8px 12px", marginBottom: "10px",
              background: "rgba(220,38,38,0.04)",
            }}>
              <div style={{ fontSize: "12px", fontWeight: 600 }}>
                {r.title_en || r.title_original}
              </div>
              <div style={{ fontSize: "10px", fontFamily: "var(--font-mono)", color: "var(--text-muted)", margin: "2px 0 4px" }}>
                {r.source_name} · {r.topic_primary} · Gemini {r.gemini_score >= 0 ? "+" : ""}{r.gemini_score}
                {" · "}{MODEL_LABELS[r.model] || r.model} ({ARM_LABELS[r.arm] || r.arm})
                {r.finish_reason === "content_filter" ? " · provider filter" : ""}
              </div>
              {r.refusal_text && (
                <div style={{ fontSize: "11px", color: "var(--text-secondary)", whiteSpace: "pre-wrap" }}>
                  {r.refusal_text.slice(0, 400)}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
