import React, { useEffect, useState } from "react";
import { fetchAltModelSummary, fetchAltModelRefusals } from "../api";
import { modelLabel, armLabel, isRetiredModel } from "../altModels";
import { DocumentHeader, STANDFIRST, SectionRule } from "./documentChrome";
import { MICRO, META_LINE, Quiet } from "./adminChrome";

// Admin › Alt Models — the alt-model experiment's aggregate view (App.js
// gates on !READ_ONLY). Morning Brief phase 2B: the design's §11 table
// (Archivo header over a 1px ink rule, Newsreader 18px figures, --soft row
// rules) over the live /api/alt-models/summary groups, then the metric
// definitions, the frozen 2026-08 findings and the refusal browser.
// Refusal rate is NOT the sole censorship metric: sanitised-but-answered
// output only shows in topic-agreement / score-delta numbers.

const GRID = "1.5fr 72px 88px 88px 88px 80px 1.2fr";

function pct(x) {
  return x === null || x === undefined ? "—" : `${(x * 100).toFixed(1)}%`;
}
function signed(x, d = 3) {
  return x == null ? "—" : `${x >= 0 ? "+" : ""}${x.toFixed(d)}`;
}

const FIG = { fontFamily: "var(--font-headline)", fontSize: "18px", fontWeight: 500, textAlign: "right", color: "var(--ink)", fontVariantNumeric: "tabular-nums" };
const FIG_MUTED = { ...FIG, color: "var(--muted)" };
const HEAD = { ...MICRO, letterSpacing: "0.14em" };
const RIGHT = { textAlign: "right" };

function GroupRow({ g }) {
  const o = g.by_outcome || {};
  const refusalPct = g.total ? (o.refused || 0) / g.total : 0;
  const isControl = g.arm === "control";
  const note = isControl
    ? "Noise floor — the production model re-run on the same articles. Its agreement is the ceiling every other row is judged against, not 100%."
    : [
        `ok ${o.ok ?? 0} · refused ${o.refused ?? 0} · parse ${o.parse_error ?? 0} · api ${o.api_error ?? 0}`,
        Object.keys(g.refusals_by_topic || {}).length
          ? "Refusals by topic: " + Object.entries(g.refusals_by_topic).map(([t, n]) => `${t} ×${n}`).join(", ")
          : null,
      ].filter(Boolean).join(". ");
  return (
    <div style={{
      display: "grid", gridTemplateColumns: GRID, gap: "0 18px", padding: "14px 0",
      borderBottom: "1px solid var(--soft)", alignItems: "baseline",
    }}>
      <span style={{ minWidth: 0 }}>
        <span style={{ fontSize: "13.5px", color: "var(--ink)", fontWeight: 500 }}>{modelLabel(g.model)}</span>
        {" "}
        <span style={{ fontFamily: "var(--font-mono)", fontSize: "8px", letterSpacing: "0.12em", textTransform: "uppercase", color: isControl ? "var(--blue)" : "var(--pale)" }}>
          {armLabel(g.arm)}
        </span>
      </span>
      <span style={FIG_MUTED}>{g.total?.toLocaleString() ?? "—"}</span>
      <span style={FIG}>{pct(g.topic_agreement)}</span>
      <span style={FIG_MUTED}>{g.mean_abs_score_delta == null ? "—" : g.mean_abs_score_delta.toFixed(3)}</span>
      <span style={FIG_MUTED} title="mean signed (alt − Gemini) on the sentiment axis; positive = the model reads coverage as more cooperative">
        {signed(g.mean_score_bias)}
      </span>
      <span style={{ fontFamily: "var(--font-mono)", fontSize: "12px", textAlign: "right", fontWeight: 600, color: refusalPct > 0.02 ? "var(--red)" : "var(--ink)" }}>
        {pct(refusalPct)}
      </span>
      <span style={{ fontSize: "12px", color: "var(--body)", lineHeight: 1.5 }}>{note}</span>
    </div>
  );
}

const PROSE = { fontSize: "13px", color: "var(--body)", lineHeight: 1.65, textWrap: "pretty", margin: "0 0 8px", maxWidth: "760px" };

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

  const totalSwept = (summary || []).reduce((s, g) => s + (g.total || 0), 0);

  return (
    <div>
      <DocumentHeader
        eyebrow="Admin · Alt Models"
        eyebrowColour="var(--flag)"
        title="Same corpus, other scorers"
        standfirst={
          <p style={STANDFIRST}>
            Approved articles re-analysed by Chinese open-weights models through the identical
            production Tier-1 prompt. Neutral-host arms run the public weights on Western
            infrastructure (trained alignment only); originator arms hit the model creator's own
            endpoint (alignment plus serving-layer filtering). Decoding config is approximated, not
            identical, to production Gemini. Kimi K3 was evaluated and cleared but is not
            proceeding to production; its sweep rows stay in the DB and are hidden here.
          </p>
        }
        meta={[summary ? `${totalSwept.toLocaleString()} SWEEP ROWS` : "LOADING", "NOT PUBLIC"]}
      />

      {error && <div style={{ color: "var(--red)", fontSize: "12px" }}>{error}</div>}
      {summary && summary.length === 0 && (
        <Quiet>No sweeps recorded yet — run <code>scripts/sweep_alt_models.py</code>.</Quiet>
      )}

      {summary && summary.length > 0 && (
        <div style={{ overflowX: "auto" }}>
          <div style={{ minWidth: "820px" }}>
            <div style={{ display: "grid", gridTemplateColumns: GRID, gap: "0 18px", paddingBottom: "8px", borderBottom: "1px solid var(--ink)" }}>
              <span style={HEAD}>Model · arm</span>
              <span style={{ ...HEAD, ...RIGHT }}>N</span>
              <span style={{ ...HEAD, ...RIGHT }}>Topic agree</span>
              <span style={{ ...HEAD, ...RIGHT }}>Mean |Δ|</span>
              <span style={{ ...HEAD, ...RIGHT }}>Score bias</span>
              <span style={{ ...HEAD, ...RIGHT }}>Refused</span>
              <span style={HEAD}>Outcomes</span>
            </div>
            {summary.map((g) => <GroupRow key={`${g.model}|${g.arm}`} g={g} />)}
          </div>
        </div>
      )}

      <SectionRule>How to read these numbers</SectionRule>
      <p style={PROSE}>
        <strong>Topic agreement</strong> — share of ok articles where the model picked the same
        primary topic as the stored production analysis. The Gemini-control row is the
        calibration: re-running <em>the same production model</em> only reproduces its own
        stored topic ~71% of the time (sampling, model updates, prompt drift), so that figure
        is the ceiling every other row should be judged against, not 100%.
      </p>
      <p style={PROSE}>
        <strong>Mean |Δ|</strong> — average absolute gap on the sentiment axis (−1 hostile …
        +1 cooperative) vs production, over agreeing and disagreeing rows alike.{" "}
        <strong>Score bias</strong> — the same gap <em>signed</em> (model − production):
        positive means the model reads coverage as more cooperative than Gemini does. A bias
        near the control's own drift means no directional lean.
      </p>
      <p style={PROSE}>
        <strong>Refused</strong> — outright refusals only. A sanitised-but-answered response
        counts as ok here and would surface instead as topic or score divergence, which is why
        refusals alone are not the censorship metric.
      </p>

      {/* Findings — distilled from ALT_MODEL_EXPERIMENT_WRITEUP.md (refreshed
          2026-08-28 against the full 15.4k-row corpus; the table above is live,
          so headline figures can drift a point or two as the daily sweep runs). */}
      {summary && summary.length > 0 && (
        <>
          <SectionRule right="2026-08 WRITE-UP · REFRESHED 08-28">Findings</SectionRule>
          <ol style={{ ...PROSE, paddingLeft: "20px" }}>
            <li style={{ marginBottom: "8px" }}>
              <strong>The censorship hypothesis failed on this corpus.</strong> Zero refusals
              across 15k+ articles including PLA drills and 台獨 rhetoric; no pinyin-isation of
              Taiwanese names; a "Taiwan leader"-type formulation appeared in 0.3% of opportunities;
              and summary omission of sensitive entities sits at the Gemini rerun noise floor,
              with politically loaded entities omitted <em>less</em> than average.
            </li>
            <li style={{ marginBottom: "8px" }}>
              <strong>V4F's low headline agreement is mostly a stricter relevance gate, not
              misclassification.</strong> It rules ~31% of articles NOT_RELEVANT, and the gate
              cuts <em>against</em> the censorship story: ~6% NR on sovereignty-marked articles
              vs ~37% on everything else. Conditional on both models agreeing an article is
              relevant, agreement is ~60% against the ~78% same-model ceiling.
            </li>
            <li style={{ marginBottom: "8px" }}>
              <strong>No directional sentiment bias.</strong> V4F's signed score bias is the same
              magnitude as the control's own run-to-run drift. Remaining disagreements are
              boundary disputes on our own fuzziest categories (POL_DOMESTIC_TW vs POL_TONGDU,
              CULTURE vs POL_TONGDU, LEGAL_GREY vs POL_DOMESTIC_TW).
            </li>
            <li>
              Full method, tables and caveats: <code>ALT_MODEL_EXPERIMENT_WRITEUP.md</code> (repo
              root) · reproduce via <code>scripts/alt_model_aggregates.py</code>,{" "}
              <code>scripts/audit_terminology_markers.py</code> and{" "}
              <code>scripts/audit_summary_completeness.py</code>.
            </li>
          </ol>
        </>
      )}

      {refusals.length > 0 && (
        <>
          <SectionRule right={`${refusals.length} SHOWN`}>Refusal browser</SectionRule>
          {refusals.map((r) => (
            <div key={r.id} style={{ borderLeft: "2px solid var(--red)", padding: "6px 14px", marginBottom: "12px" }}>
              <div style={{ fontFamily: "var(--font-headline)", fontSize: "16px", fontWeight: 500, lineHeight: 1.3, color: "var(--ink)" }}>
                {r.title_en || r.title_original}
              </div>
              <div style={{ ...META_LINE, margin: "3px 0 5px" }}>
                {r.source_name} · {r.topic_primary} · GEMINI {signed(r.gemini_score, 2)} · {modelLabel(r.model)} ({armLabel(r.arm)})
                {r.finish_reason === "content_filter" ? " · PROVIDER FILTER" : ""}
              </div>
              {r.refusal_text && (
                <div style={{ fontSize: "12px", color: "var(--body)", whiteSpace: "pre-wrap", lineHeight: 1.55 }}>
                  {r.refusal_text.slice(0, 400)}
                </div>
              )}
            </div>
          ))}
        </>
      )}

      <p style={{ ...PROSE, color: "var(--faint)", fontSize: "12px", marginTop: "24px" }}>
        Methodology caveats: decoding config is approximated (Gemini runs JSON mode plus thinking;
        the OpenRouter arms cannot), and a sanitised answer classifies as ok. Only the production
        model feeds the site; nothing on this page enters an editorial queue.
      </p>
    </div>
  );
}
