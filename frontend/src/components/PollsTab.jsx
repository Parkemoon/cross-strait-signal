import { useEffect, useMemo, useState } from "react";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, Legend,
} from "recharts";
import {
  fetchPolls, fetchPollsByQuestion, fetchPollsRoster, fetchPollsTopics,
} from "../api";

// The three flagship trackers pinned at the top of the tab. Everything
// else (party-ID, war-risk, vote intent, ad-hoc issue polls) is
// reachable through the topic pill row below.
const FLAGSHIPS = [
  { key: "identity_nccu_3pt",    label: "Taiwan / China Identity",  source: "NCCU ESC, 1992–2025" },
  { key: "unification_nccu_6pt", label: "Unification — Status Quo — Independence", source: "NCCU ESC, 1994–2025" },
  { key: "approval_lai_overall", label: "President Lai Approval",   source: "Multi-pollster" },
];
const FLAGSHIP_KEYS = new Set(FLAGSHIPS.map((f) => f.key));

// Per-question option-order palettes. Hand-coded rather than computed
// because each scale has its own natural colour story:
//   * identity_nccu_3pt — green = Taiwanese, red = Chinese, purple = Both,
//     grey = non-response. Matches the project's broader palette
//     (party-green for TW identity, party-red for PRC identity).
//   * unification_nccu_6pt — 6-point scale from "unification ASAP" (red)
//     to "independence ASAP" (green) through status-quo greys. Mirrors
//     the published NCCU chart conventions.
//   * approval_lai_overall — green = satisfied, red = dissatisfied,
//     grey = no opinion. Standard approval-poll convention.
const OPTION_PALETTES = {
  identity_nccu_3pt: ["#16a34a", "#dc2626", "#7c3aed", "#94a3b8"],
  unification_nccu_6pt: [
    "#dc2626", // 0 unification ASAP
    "#f59e0b", // 1 SQ→unification
    "#94a3b8", // 2 SQ decide later
    "#6b7280", // 3 SQ indefinitely
    "#84cc16", // 4 SQ→independence
    "#16a34a", // 5 independence ASAP
    "#cbd5e1", // 6 non-response (when present)
  ],
  approval_lai_overall: ["#16a34a", "#dc2626", "#94a3b8"],
};
const FALLBACK_PALETTE = [
  "#16a34a", "#dc2626", "#1d4ed8", "#f59e0b", "#7c3aed", "#14B8A6", "#94a3b8",
];

// Pollster bias → chip colour. Mirrors SourceBadge's BIAS_COLORS so
// chips on the Polls tab read the same way as source badges on the
// feed. `academic` is NCCU's bias and is intentionally non-political
// (slate); `state_official` is SIDE-AWARE — slug='mac' is TW executive
// branch (green under the current DPP exec) while any other slug with
// state_official bias is presumed PRC-side (red). When a PRC state
// pollster is added we'll need a side column on the pollsters table,
// but until then a slug-based branch is enough.
const POLLSTER_CHIP_COLOURS = {
  academic:          { bg: "#475569", text: "#fff" },        // slate
  state_nationalist: { bg: "#b91c1c", text: "#fff" },
  green:             { bg: "#15803d", text: "#fff" },
  green_leaning:     { bg: "#4ade80", text: "#14532d" },
  blue:              { bg: "#1d4ed8", text: "#fff" },
  blue_leaning:      { bg: "#93c5fd", text: "#1e3a5f" },
  centrist:          { bg: "#6b7280", text: "#fff" },
  unknown:           { bg: "#cbd5e1", text: "#1f2937" },
};

export function pollsterChipColour(bias, slug) {
  if (bias === "state_official") {
    return slug === "mac"
      ? { bg: "#15803d", text: "#fff" }   // TW exec under DPP — DPP green
      : { bg: "#dc2626", text: "#fff" };  // PRC state — red (future-proofing)
  }
  return POLLSTER_CHIP_COLOURS[bias] || { bg: "#6b7280", text: "#fff" };
}

const FAMILY_LABELS = {
  identity:    "Identity",
  unification: "Unification",
  approval:    "Approval",
  attitude:    "Cross-strait attitude",
  vote_intent: "Vote intent",
  issue:       "Issue polls",
};

// "2025-01-01" → "2025". For long-range axes the year alone is enough;
// the tooltip carries the full date so the precision isn't lost.
function tickYear(iso) {
  return iso ? iso.slice(0, 4) : "";
}

function fmtDate(iso) {
  if (!iso) return "";
  const [y, m, d] = iso.split("-");
  const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  return `${months[Number(m) - 1]} ${Number(d)}, ${y}`;
}

function fmtPct(v) {
  if (v === null || v === undefined) return "—";
  return `${Number(v).toFixed(1)}%`;
}

function SectionHeader({ children, right }) {
  return (
    <div style={{ marginBottom: "16px", marginTop: "28px" }}>
      <div style={{ height: "2px", background: "var(--border-color)", marginBottom: "9px" }} />
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <span style={{
          fontFamily: "var(--font-mono)",
          fontSize: "11px",
          fontWeight: 600,
          letterSpacing: "0.14em",
          textTransform: "uppercase",
          color: "var(--text-primary)",
        }}>
          {children}
        </span>
        {right && (
          <span style={{
            fontFamily: "var(--font-mono)",
            fontSize: "10px",
            color: "var(--text-muted)",
          }}>
            {right}
          </span>
        )}
      </div>
      <div style={{ height: "1px", background: "var(--border-color)", marginTop: "9px" }} />
    </div>
  );
}

function PollsterChip({ slug, name, bias }) {
  const { bg, text } = pollsterChipColour(bias, slug);
  return (
    <span style={{
      display: "inline-block",
      padding: "2px 8px",
      fontFamily: "var(--font-mono)",
      fontSize: "10px",
      letterSpacing: "0.06em",
      textTransform: "uppercase",
      background: bg,
      color: text,
    }}>
      {name}
    </span>
  );
}

function ProvenanceChip({ poll }) {
  // The three discriminators documented in database.md:
  //   - source_article_id NOT NULL → AI extraction
  //   - reviewed_by LIKE 'backfill:%' → script-seeded (NCCU long series)
  //   - otherwise → manual analyst entry
  let label, bg;
  if (poll.source_article_id) {
    label = "AI"; bg = "#7c3aed";
  } else if (poll.reviewed_by && poll.reviewed_by.startsWith("backfill:")) {
    label = "Backfill"; bg = "#475569";
  } else {
    label = "Manual"; bg = "#0f766e";
  }
  return (
    <span style={{
      display: "inline-block",
      padding: "1px 6px",
      fontFamily: "var(--font-mono)",
      fontSize: "9px",
      letterSpacing: "0.06em",
      textTransform: "uppercase",
      background: bg,
      color: "#fff",
    }}>{label}</span>
  );
}

// Pivot the /by-question payload into Recharts shape. Always keys series
// by (pollster_slug, option_label_en) so the chart handles single-
// pollster (NCCU identity/unification) and cross-pollster (Lai approval)
// uniformly. The legend label drops the pollster prefix when there's
// only one pollster, so the cross-pollster overlay only carries the
// extra weight when there's analytical reason to.
function pivotByQuestion(payload) {
  if (!payload || !payload.waves || payload.waves.length === 0) {
    return { data: [], series: [], pollsterCount: 0 };
  }

  // Collect all (pollster_slug, option_label_en, option_order) tuples in
  // the canonical order they appear (option_order ASC within a wave;
  // pollsters in order of first appearance). This drives both the series
  // list and the chart legend ordering.
  const pollsterOrder = [];
  const seenPollsters = new Set();
  const optionTuples = {}; // pollster_slug → Map(label_en → {order, pollster_bias})
  for (const wave of payload.waves) {
    if (!seenPollsters.has(wave.pollster_slug)) {
      seenPollsters.add(wave.pollster_slug);
      pollsterOrder.push({
        slug: wave.pollster_slug,
        name: wave.pollster_name_en,
        bias: wave.pollster_bias,
      });
    }
    if (!optionTuples[wave.pollster_slug]) optionTuples[wave.pollster_slug] = new Map();
    for (const opt of wave.options || []) {
      const key = opt.label_en || opt.label_zh || `option_${opt.option_order}`;
      if (!optionTuples[wave.pollster_slug].has(key)) {
        optionTuples[wave.pollster_slug].set(key, {
          order: opt.option_order ?? 0,
          label: key,
        });
      }
    }
  }

  const isCrossPollster = pollsterOrder.length > 1;
  const palette = OPTION_PALETTES[payload.question_key] || FALLBACK_PALETTE;

  const series = [];
  for (const p of pollsterOrder) {
    const opts = Array.from(optionTuples[p.slug].values()).sort((a, b) => a.order - b.order);
    opts.forEach((o, idx) => {
      const colour = isCrossPollster
        // Cross-pollster: pollster identity drives colour, option drives line style.
        ? pollsterChipColour(p.bias, p.slug).bg
        : (palette[o.order] || palette[idx] || FALLBACK_PALETTE[idx % FALLBACK_PALETTE.length]);
      series.push({
        dataKey: `${p.slug}__${o.label}`,
        legendName: isCrossPollster ? `${p.name}: ${o.label}` : o.label,
        stroke: colour,
        strokeDasharray: isCrossPollster && idx > 0 ? (idx === 1 ? "4 3" : "1 2") : undefined,
        pollster: p,
        option: o.label,
      });
    });
  }

  // Pivot waves → time-keyed rows, anchored on fielded_end (falling back
  // to fielded_start) so annual series like NCCU plot at the year-final
  // publication date rather than Jan 1. For typical 1–3-day polls
  // start≈end so the anchor is effectively the same. If two pollsters
  // share an anchor date their option keys coalesce into one row;
  // Recharts tolerates missing keys (no dot rendered for that point).
  const rowByAnchor = new Map();
  for (const wave of payload.waves) {
    const anchor = wave.fielded_end || wave.fielded_start;
    if (!rowByAnchor.has(anchor)) {
      rowByAnchor.set(anchor, { anchor });
    }
    const row = rowByAnchor.get(anchor);
    for (const opt of wave.options || []) {
      const optKey = opt.label_en || opt.label_zh || `option_${opt.option_order}`;
      row[`${wave.pollster_slug}__${optKey}`] = opt.percentage;
    }
  }
  const data = Array.from(rowByAnchor.values())
    .sort((a, b) => a.anchor.localeCompare(b.anchor));

  return { data, series, pollsterCount: pollsterOrder.length };
}

function PollTrendChart({ payload, height = 240 }) {
  const { data, series, pollsterCount } = useMemo(() => pivotByQuestion(payload), [payload]);

  if (!payload) {
    return (
      <div style={{ height, display: "flex", alignItems: "center", justifyContent: "center",
                    color: "var(--text-muted)", fontFamily: "var(--font-mono)", fontSize: "12px" }}>
        Loading…
      </div>
    );
  }
  if (data.length === 0) {
    return (
      <div style={{ height, display: "flex", alignItems: "center", justifyContent: "center",
                    color: "var(--text-muted)", fontFamily: "var(--font-mono)", fontSize: "12px",
                    border: "1px dashed var(--border-color)", flexDirection: "column", gap: "6px" }}>
        <div>No approved waves yet for this question.</div>
        <div style={{ fontSize: "10px" }}>
          Question is seeded as canonical; data appears once polls are extracted + analyst-approved.
        </div>
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 10, right: 24, left: 0, bottom: 4 }}>
        <CartesianGrid stroke="var(--border-color)" strokeDasharray="3 3" />
        <XAxis
          dataKey="anchor"
          tickFormatter={tickYear}
          tick={{ fill: "var(--text-muted)", fontFamily: "var(--font-mono)", fontSize: 10 }}
          stroke="var(--border-color)"
          minTickGap={28}
        />
        <YAxis
          domain={[0, "auto"]}
          tickFormatter={(v) => `${v}%`}
          tick={{ fill: "var(--text-muted)", fontFamily: "var(--font-mono)", fontSize: 10 }}
          stroke="var(--border-color)"
          width={42}
        />
        <Tooltip
          contentStyle={{
            background: "var(--bg-card)",
            border: "1px solid var(--border-color)",
            fontFamily: "var(--font-mono)",
            fontSize: "11px",
          }}
          labelFormatter={fmtDate}
          formatter={(v) => fmtPct(v)}
        />
        <Legend
          wrapperStyle={{ fontFamily: "var(--font-mono)", fontSize: "10px" }}
          iconType="line"
        />
        {series.map((s) => (
          <Line
            key={s.dataKey}
            type="monotone"
            dataKey={s.dataKey}
            name={s.legendName}
            stroke={s.stroke}
            strokeDasharray={s.strokeDasharray}
            strokeWidth={1.6}
            dot={pollsterCount > 1 ? { r: 2 } : false}
            activeDot={{ r: 4 }}
            connectNulls
            isAnimationActive={false}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}

function FlagshipStrip({ flagship, payload }) {
  // Right-rail shows live state when data exists (wave count + latest
  // date) and falls back to the static source attribution when empty —
  // so the attribution never duplicates the subtitle below.
  const waveCount = payload?.waves?.length || 0;
  const latestWave = waveCount > 0 ? payload.waves[payload.waves.length - 1] : null;
  const rightRail = latestWave
    ? `${waveCount} wave${waveCount === 1 ? "" : "s"} · latest ${fmtDate(latestWave.fielded_end || latestWave.fielded_start)}`
    : null;

  return (
    <section style={{ marginBottom: "32px" }}>
      <SectionHeader right={rightRail}>{flagship.label}</SectionHeader>
      <div style={{
        fontFamily: "var(--font-mono)",
        fontSize: "10px",
        letterSpacing: "0.08em",
        textTransform: "uppercase",
        color: "var(--text-muted)",
        marginBottom: "8px",
      }}>
        {flagship.source}
      </div>
      <PollTrendChart payload={payload} height={260} />
    </section>
  );
}

function TopicPills({ topics, selectedKey, onSelect }) {
  // Flatten + filter — pills only show questions that are NOT pinned
  // flagships. We also hide questions with zero approved polls so the
  // pill row doesn't advertise dead-end clicks.
  const pills = useMemo(() => {
    if (!topics?.families) return [];
    const out = [];
    for (const fam of topics.families) {
      for (const q of fam.questions) {
        if (FLAGSHIP_KEYS.has(q.question_key)) continue;
        if ((q.approved_count || 0) === 0) continue;
        out.push({ ...q, family: fam.family });
      }
    }
    // Sort by approved_count DESC across families so the most-used
    // trackers surface first; the family label is shown on the pill.
    out.sort((a, b) => (b.approved_count - a.approved_count) || a.question_key.localeCompare(b.question_key));
    return out;
  }, [topics]);

  if (pills.length === 0) {
    return (
      <div style={{
        padding: "12px 0",
        fontFamily: "var(--font-mono)",
        fontSize: "11px",
        color: "var(--text-muted)",
      }}>
        No other approved poll questions yet. Extracted candidates will surface here once the review queue is worked.
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: "8px", padding: "4px 0 12px 0" }}>
      {pills.map((p) => {
        const active = p.question_key === selectedKey;
        return (
          <button
            key={p.question_key}
            onClick={() => onSelect(p.question_key)}
            style={{
              padding: "5px 10px",
              fontFamily: "var(--font-mono)",
              fontSize: "10px",
              letterSpacing: "0.06em",
              textTransform: "uppercase",
              background: active ? "var(--accent)" : "var(--bg-card)",
              color: active ? "#fff" : "var(--text-primary)",
              border: "1px solid var(--border-color)",
              cursor: "pointer",
              display: "inline-flex",
              gap: "8px",
              alignItems: "baseline",
            }}
            title={p.question_text_en}
          >
            <span style={{ opacity: 0.65 }}>{FAMILY_LABELS[p.family] || p.family}</span>
            <span>{p.question_key}</span>
            <span style={{ opacity: 0.55 }}>· {p.approved_count}</span>
          </button>
        );
      })}
    </div>
  );
}

function PollCard({ poll }) {
  return (
    <article style={{
      padding: "16px",
      border: "1px solid var(--border-color)",
      background: "var(--bg-card)",
      marginBottom: "12px",
    }}>
      <header style={{ display: "flex", gap: "10px", flexWrap: "wrap",
                       alignItems: "baseline", marginBottom: "10px" }}>
        <PollsterChip slug={poll.pollster_slug} name={poll.pollster_name_en} bias={poll.pollster_bias} />
        <ProvenanceChip poll={poll} />
        <span style={{ fontFamily: "var(--font-mono)", fontSize: "11px",
                       color: "var(--text-primary)" }}>
          {fmtDate(poll.fielded_start)}
          {poll.fielded_end && poll.fielded_end !== poll.fielded_start ? ` – ${fmtDate(poll.fielded_end)}` : ""}
        </span>
        {poll.sample_size && (
          <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px",
                         color: "var(--text-muted)" }}>
            n = {poll.sample_size.toLocaleString()}
          </span>
        )}
      </header>
      <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
        {(poll.questions || []).map((q) => (
          <div key={q.question_key}>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: "10px",
                          letterSpacing: "0.06em", textTransform: "uppercase",
                          color: "var(--text-muted)", marginBottom: "4px" }}>
              {q.question_key} · {FAMILY_LABELS[q.family] || q.family}
            </div>
            <div style={{ fontSize: "13px", color: "var(--text-primary)", lineHeight: 1.45,
                          marginBottom: "6px" }}>
              {q.question_text_en}
            </div>
            <div style={{ display: "grid",
                          gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
                          gap: "4px 12px" }}>
              {(q.options || []).slice().sort((a, b) => a.option_order - b.option_order).map((o) => (
                <div key={`${o.label_en}-${o.option_order}`} style={{
                  display: "flex",
                  justifyContent: "space-between",
                  fontFamily: "var(--font-mono)",
                  fontSize: "11px",
                }}>
                  <span style={{ color: "var(--text-primary)" }}>{o.label_en || o.label_zh}</span>
                  <span style={{ color: "var(--text-muted)" }}>{fmtPct(o.percentage)}</span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
      {poll.methodology_note && (
        <div style={{ marginTop: "10px", fontFamily: "var(--font-mono)", fontSize: "10px",
                      color: "var(--text-muted)", fontStyle: "italic" }}>
          {poll.methodology_note}
        </div>
      )}
    </article>
  );
}

export default function PollsTab() {
  const [flagshipData, setFlagshipData] = useState({}); // question_key → payload | null
  const [topicsData, setTopicsData] = useState(null);
  const [recentPolls, setRecentPolls] = useState(null);
  const [rosterData, setRosterData] = useState(null);
  const [selectedKey, setSelectedKey] = useState(null);
  const [selectedPayload, setSelectedPayload] = useState(null);
  const [error, setError] = useState(null);

  // Initial load — fan out the four independent calls in parallel.
  // Each flagship is its own /by-question call so empty flagships
  // (Lai approval at the moment) still resolve and render their
  // "no waves yet" placeholder.
  useEffect(() => {
    let cancelled = false;
    Promise.all([
      ...FLAGSHIPS.map((f) => fetchPollsByQuestion(f.key).then((data) => ({ key: f.key, data }))),
      fetchPollsTopics().then((d) => ({ key: "__topics__", data: d })),
      fetchPolls({ limit: 30 }).then((d) => ({ key: "__recent__", data: d })),
      fetchPollsRoster().then((d) => ({ key: "__roster__", data: d })),
    ]).then((results) => {
      if (cancelled) return;
      const flagships = {};
      let topics = null, recent = null, roster = null;
      for (const r of results) {
        if (r.key === "__topics__") topics = r.data;
        else if (r.key === "__recent__") recent = r.data;
        else if (r.key === "__roster__") roster = r.data;
        else flagships[r.key] = r.data;
      }
      setFlagshipData(flagships);
      setTopicsData(topics);
      setRecentPolls(recent?.polls || []);
      setRosterData(roster);
    }).catch((e) => {
      if (!cancelled) setError(e.message || String(e));
    });
    return () => { cancelled = true; };
  }, []);

  // Fetch the selected non-flagship payload on demand. Reset whenever
  // selectedKey changes so a quick pill-click sequence doesn't render
  // stale data into a different chart.
  useEffect(() => {
    if (!selectedKey) {
      setSelectedPayload(null);
      return;
    }
    let cancelled = false;
    setSelectedPayload(null);
    fetchPollsByQuestion(selectedKey)
      .then((data) => { if (!cancelled) setSelectedPayload(data); })
      .catch((e) => { if (!cancelled) setError(e.message || String(e)); });
    return () => { cancelled = true; };
  }, [selectedKey]);

  // Headline counts for the section right-rail.
  const totalApprovedPolls = recentPolls?.length ?? 0;
  const activePollsterCount = useMemo(
    () => (rosterData?.pollsters || []).filter((p) => (p.approved_count || 0) > 0).length,
    [rosterData],
  );

  return (
    <main style={{ padding: "28px 32px", minWidth: 0 }}>
      <header style={{ marginBottom: "8px" }}>
        <h1 style={{
          fontFamily: "var(--font-serif)",
          fontSize: "26px",
          fontWeight: 400,
          letterSpacing: "0.01em",
          margin: 0,
        }}>
          Poll Tracker
        </h1>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: "11px",
                      color: "var(--text-muted)", marginTop: "4px" }}>
          Taiwan public opinion on identity, unification, presidential approval, and cross-strait attitudes.
          {activePollsterCount > 0 && ` · ${activePollsterCount} pollster${activePollsterCount === 1 ? "" : "s"} with data`}
        </div>
      </header>

      {error && (
        <div style={{ padding: "10px 14px", marginTop: "16px",
                      border: "1px solid #dc2626", background: "rgba(220, 38, 38, 0.08)",
                      color: "#dc2626", fontFamily: "var(--font-mono)", fontSize: "11px" }}>
          {error}
        </div>
      )}

      {/* Flagship strips — three full-width charts, source-faithful (all
          options visible). See [[feedback-analyst-charts]] for the rule
          against composite/summary lines on analyst charts. */}
      {FLAGSHIPS.map((f) => (
        <FlagshipStrip key={f.key} flagship={f} payload={flagshipData[f.key]} />
      ))}

      {/* Topic pill row — other canonical questions with data. Click →
          fetches the question's full /by-question payload and renders
          a 4th chart strip below. */}
      <SectionHeader right="Click to expand">Other Trackers</SectionHeader>
      <TopicPills topics={topicsData} selectedKey={selectedKey} onSelect={(k) =>
        setSelectedKey((cur) => (cur === k ? null : k))} />

      {selectedKey && (
        <section style={{ marginBottom: "32px" }}>
          <SectionHeader
            right={
              selectedPayload?.waves
                ? `${selectedPayload.waves.length} wave${selectedPayload.waves.length === 1 ? "" : "s"}`
                : ""
            }
          >
            {selectedPayload?.question_text_en || selectedKey}
          </SectionHeader>
          <PollTrendChart payload={selectedPayload} height={300} />
        </section>
      )}

      {/* Recent polls feed — most recent approved polls. Each card
          surfaces pollster + provenance + per-question option rollup.
          Provenance chips (AI / Backfill / Manual) per the three
          discriminators documented in database.md. */}
      <SectionHeader right={`${totalApprovedPolls} recent`}>Recent Polls</SectionHeader>
      {recentPolls === null ? (
        <div style={{ padding: "20px", fontFamily: "var(--font-mono)", fontSize: "11px",
                      color: "var(--text-muted)" }}>Loading…</div>
      ) : recentPolls.length === 0 ? (
        <div style={{ padding: "20px", fontFamily: "var(--font-mono)", fontSize: "11px",
                      color: "var(--text-muted)" }}>No approved polls yet.</div>
      ) : (
        recentPolls.map((p) => <PollCard key={p.poll_id} poll={p} />)
      )}
    </main>
  );
}
