import React, { useEffect, useState } from "react";
import { fetchAltModelSummary, fetchAltModelRefusals } from "../api";
import { modelLabel, armLabel, isRetiredModel } from "../altModels";

// Alt-model experiment aggregate view (admin only — App.js gates on !READ_ONLY).
// Divergence aggregates + refusal browser over alt_model_analysis rows.
// Refusal rate is NOT the sole censorship metric: sanitised-but-answered
// output only shows in topic-agreement / score-delta numbers.

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
  const isControl = g.arm === "control";
  return (
    <div style={{
      border: "1px solid var(--border-subtle, rgba(0,0,0,0.1))", borderRadius: "6px",
      padding: "16px", marginBottom: "16px", background: "var(--bg-card, transparent)",
    }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: "10px", marginBottom: "12px", flexWrap: "wrap" }}>
        <span style={{ fontSize: "14px", fontWeight: 700 }}>
          {modelLabel(g.model)}
        </span>
        <span style={{ fontSize: "11px", fontFamily: "var(--font-mono)", color: "var(--text-muted)" }}>
          {armLabel(g.arm)} · {g.total} articles
        </span>
        {isControl && (
          <span style={{
            fontSize: "10px", fontFamily: "var(--font-mono)", color: "#2563eb",
            border: "1px solid #2563eb", borderRadius: "2px", padding: "1px 8px",
          }}>
            noise floor — same model rerun; its agreement is the ceiling, not 100%
          </span>
        )}
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
    fetchAltModelSummary()
      .then((d) => setSummary((d?.groups || []).filter((g) => !isRetiredModel(g.model))))
      .catch((e) => setError(String(e)));
    fetchAltModelRefusals({ limit: 50 })
      .then((d) => setRefusals((d?.rows || []).filter((r) => !isRetiredModel(r.model))))
      .catch(() => {});
  }, []);

  return (
    <div>
      <h2 style={{ fontSize: "16px", marginBottom: "4px" }}>Alternate Model Experiment</h2>
      <p style={{ fontSize: "12px", color: "var(--text-muted)", marginBottom: "20px", maxWidth: "640px" }}>
        Approved articles re-analysed by Chinese open-weights models through the identical
        production Tier-1 prompt. Neutral-host arms run the public weights on Western
        infrastructure (trained alignment only); originator arms hit the model creator's
        own endpoint (alignment + serving-layer filtering). Decoding config is
        approximated, not identical, to production Gemini. Kimi K3 was evaluated and
        cleared (see the write-up) but is not proceeding to production — its sweep rows
        stay in the DB for reproducibility and are hidden here.
      </p>

      {/* Metric definitions — every number on the cards below */}
      <div style={{
        border: "1px dashed var(--border-color)", borderRadius: "6px",
        padding: "12px 16px", marginBottom: "20px", maxWidth: "760px",
        fontSize: "12px", color: "var(--text-secondary)", lineHeight: 1.65,
      }}>
        <div style={{ ...tileLabel, marginBottom: "8px" }}>How to read these numbers</div>
        <p style={{ margin: "0 0 6px" }}>
          <strong>Topic agreement</strong> — share of ok articles where the model picked the
          same primary topic as the stored production analysis. The Gemini-control card is
          the calibration: re-running <em>the same production model</em> only reproduces its
          own stored topic ~71% of the time (sampling + model updates + prompt drift), so
          that figure is the ceiling every other row should be judged against — not 100%.
        </p>
        <p style={{ margin: "0 0 6px" }}>
          <strong>Mean |Δ score|</strong> — average absolute gap on the sentiment axis
          (−1 hostile … +1 cooperative) vs production, over agreeing-and-disagreeing rows
          alike. <strong>Score bias</strong> — the same gap <em>signed</em> (model − production):
          positive means the model reads coverage as more cooperative than Gemini does. A
          bias near the control's own drift means no directional lean.
        </p>
        <p style={{ margin: 0 }}>
          <strong>Refusal rate</strong> — outright refusals only. A sanitised-but-answered
          response counts as ok here and would surface instead as topic/score divergence,
          which is why refusals alone are not the censorship metric.
        </p>
      </div>

      {error && <div style={{ color: "#dc2626", fontSize: "12px" }}>{error}</div>}
      {summary && summary.length === 0 && (
        <div style={{ fontSize: "13px", color: "var(--text-muted)" }}>
          No sweeps recorded yet — run <code>scripts/sweep_alt_models.py</code>.
        </div>
      )}
      {(summary || []).map((g) => <GroupCard key={`${g.model}|${g.arm}`} g={g} />)}

      {/* Findings — distilled from ALT_MODEL_EXPERIMENT_WRITEUP.md (frozen
          2026-08 dataset; the cards above are live and include later sweep
          extensions, so headline figures can differ a few points). */}
      {summary && summary.length > 0 && (
        <div style={{
          borderLeft: "3px solid var(--accent-teal)", padding: "12px 16px",
          marginTop: "8px", marginBottom: "8px", maxWidth: "760px",
          background: "rgba(20,184,166,0.04)",
          fontSize: "12px", color: "var(--text-secondary)", lineHeight: 1.65,
        }}>
          <div style={{ ...tileLabel, marginBottom: "8px" }}>
            Findings — 2026-08 write-up
          </div>
          <ul style={{ margin: 0, paddingLeft: "18px" }}>
            <li style={{ marginBottom: "6px" }}>
              <strong>The censorship hypothesis failed on this corpus.</strong> Zero refusals
              across 13k+ articles including PLA drills and 台獨 rhetoric; no pinyin-isation of
              Taiwanese names; the presidential title survived in ~99% of opportunities; and
              summary omission of sensitive entities sits at the Gemini rerun noise floor —
              with politically loaded entities omitted <em>less</em> than average.
            </li>
            <li style={{ marginBottom: "6px" }}>
              <strong>V4F's low headline agreement is mostly a stricter relevance gate, not
              misclassification.</strong> It rules ~29% of articles NOT_RELEVANT — and the gate
              cuts <em>against</em> the censorship story: ~6% NR on sovereignty-marked articles
              vs ~35% on everything else. It keeps the sovereignty material and discards the
              soft-topic fluff. Conditional on both models agreeing an article is relevant,
              agreement is ~60% against the ~78% same-model ceiling.
            </li>
            <li style={{ marginBottom: "6px" }}>
              <strong>No directional sentiment bias.</strong> V4F's signed score bias is the
              same magnitude as the control's own run-to-run drift — nobody is systematically
              softening or hardening the hostility axis. Remaining disagreements are boundary
              disputes on our own fuzziest categories (LEGAL_GREY vs POL_DOMESTIC_TW,
              CULTURE vs POL_TONGDU).
            </li>
            <li>
              Full method, tables and caveats: <code>ALT_MODEL_EXPERIMENT_WRITEUP.md</code>
              (repo root) · reproduce via <code>scripts/alt_model_aggregates.py</code> +{" "}
              <code>scripts/audit_terminology_markers.py</code> +{" "}
              <code>scripts/audit_summary_completeness.py</code>.
            </li>
          </ul>
        </div>
      )}

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
                {" · "}{modelLabel(r.model)} ({armLabel(r.arm)})
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
