import { useEffect, useMemo, useState } from "react";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, Legend,
} from "recharts";
import {
  fetchPolls, fetchPollsByQuestion, fetchPollsRoster, fetchPollsTopics,
  fetchPollCandidates,
} from "../api";
import { READ_ONLY } from "../readOnly";
import { partyColour } from "../partyColours";
import PollReviewQueue from "./PollReviewQueue";
import PollEntryModal from "./PollEntryModal";
import PollColourModal from "./PollColourModal";

// The three flagship trackers pinned at the top of the tab. Everything
// else (party-ID, war-risk, vote intent, ad-hoc issue polls) is
// reachable through the topic pill row below.
const FLAGSHIPS = [
  { key: "identity_nccu_3pt",    label: "Taiwan / China Identity",  source: "NCCU ESC, 1992–2025" },
  { key: "unification_nccu_6pt", label: "Unification — Status Quo — Independence", source: "NCCU ESC, 1994–2025" },
  { key: "approval_lai_overall", label: "President Lai Approval",   source: "Multi-pollster" },
];
const FLAGSHIP_KEYS = new Set(FLAGSHIPS.map((f) => f.key));
// Render slots — resolved by key, not array position, so reordering
// FLAGSHIPS can't silently bind the Lai hero to the wrong question.
const APPROVAL_FLAGSHIP = FLAGSHIPS.find((f) => f.key === "approval_lai_overall");
const NCCU_FLAGSHIPS = FLAGSHIPS.filter((f) => f.key !== "approval_lai_overall");

// Per-question option-order palettes. Hand-coded rather than computed
// because each scale has its own natural colour story. Index order MUST
// match the seeded option_order in nccu_esc_seed.json — the chart pivots
// by position, not by label.
//   * identity_nccu_3pt — seed order is Taiwanese / Both / Chinese / NR:
//     green = Taiwanese, grey = Both (the ambivalent middle), red = Chinese,
//     pale = NR. Purple left out deliberately — it now belongs to the
//     hostile end of the sentiment axis and must not encode identity.
//   * unification_nccu_6pt — 6-point scale from "unification ASAP" (red)
//     to "independence ASAP" (green) through status-quo greys. Mirrors
//     the published NCCU chart conventions.
//   * approval_lai_overall — green = satisfied, red = dissatisfied,
//     grey = no opinion. Standard approval-poll convention.
const OPTION_PALETTES = {
  identity_nccu_3pt: ["var(--green)", "var(--muted)", "var(--red)", "var(--pale)"],
  unification_nccu_6pt: [
    "var(--red)",   // 0 unification ASAP
    "var(--rose)",  // 1 SQ→unification
    "var(--pale)",  // 2 SQ decide later
    "var(--muted)", // 3 SQ indefinitely
    "var(--gsoft)", // 4 SQ→independence
    "var(--green)", // 5 independence ASAP
    "var(--dot)",   // 6 non-response (when present)
  ],
  approval_lai_overall: ["var(--green)", "var(--red)", "var(--pale)"],
};
const FALLBACK_PALETTE = [
  "var(--green)", "var(--red)", "var(--blue)", "var(--coop)", "var(--cyan)", "var(--rose)", "var(--pale)",
];

// Pollster bias → chip colour. Mirrors SourceBadge's BIAS_COLORS so
// chips on the Polls tab read the same way as source badges on the
// feed. `academic` is NCCU's bias and is intentionally non-political
// (slate); `state_official` is SIDE-AWARE via `pollsters.place` — a
// TW state ministry (MAC, MoFA, etc.) gets DPP green under the
// current exec; a PRC state outlet gets red. Place comes from the
// /api/polls/roster response.
const POLLSTER_CHIP_COLOURS = {
  academic:          { bg: "var(--muted)", text: "#fff" },        // slate
  state_nationalist: { bg: "var(--nat)", text: "#fff" },
  green:             { bg: "var(--green)", text: "#fff" },
  green_leaning:     { bg: "var(--gsoft)", text: "#14532d" },
  blue:              { bg: "var(--blue)", text: "#fff" },
  blue_leaning:      { bg: "var(--bsoft)", text: "#1e3a5f" },
  centrist:          { bg: "var(--muted)", text: "#fff" },
  unknown:           { bg: "#cbd5e1", text: "#1f2937" },
};

export function pollsterChipColour(bias, place) {
  if (bias === "state_official") {
    // TW exec under DPP → DPP green; PRC state → red. Default green
    // when place is missing (legacy data; all current state_official
    // pollsters are TW-side per the seed roster).
    return place === "PRC"
      ? { bg: "var(--red)", text: "#fff" }
      : { bg: "var(--green)", text: "#fff" };
  }
  return POLLSTER_CHIP_COLOURS[bias] || { bg: "var(--muted)", text: "#fff" };
}

export const FAMILY_LABELS = {
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
    <div style={{ display: "flex", alignItems: "baseline", gap: "10px", marginBottom: "16px", marginTop: "28px" }}>
      <span style={{
        fontFamily: "var(--font-mono)",
        fontSize: "9.5px",
        fontWeight: 600,
        letterSpacing: "0.24em",
        textTransform: "uppercase",
        color: "var(--ink)",
        whiteSpace: "nowrap",
      }}>
        {children}
      </span>
      <span style={{ flex: 1, borderBottom: "1px solid var(--hair)" }} />
      {right && (
        <span style={{
          fontFamily: "var(--font-mono)",
          fontSize: "9px",
          color: "var(--pale)",
          letterSpacing: "0.08em",
          textAlign: "right",
        }}>
          {right}
        </span>
      )}
    </div>
  );
}

export function PollsterChip({ slug, name, bias, place }) {
  const { bg, text } = pollsterChipColour(bias, place);
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
    label = "AI"; bg = "var(--bsoft)";
  } else if (poll.reviewed_by && poll.reviewed_by.startsWith("backfill:")) {
    label = "Backfill"; bg = "var(--muted)";
  } else {
    label = "Manual"; bg = "var(--cyan)";
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
  const optionTuples = {}; // pollster_slug → Map(label_en → {order, label, party, colour_override})
  for (const wave of payload.waves) {
    if (!seenPollsters.has(wave.pollster_slug)) {
      seenPollsters.add(wave.pollster_slug);
      pollsterOrder.push({
        slug: wave.pollster_slug,
        name: wave.pollster_name_en,
        bias: wave.pollster_bias,
        place: wave.pollster_place,
      });
    }
    if (!optionTuples[wave.pollster_slug]) optionTuples[wave.pollster_slug] = new Map();
    for (const opt of wave.options || []) {
      const key = opt.label_en || opt.label_zh || `option_${opt.option_order}`;
      if (!optionTuples[wave.pollster_slug].has(key)) {
        optionTuples[wave.pollster_slug].set(key, {
          order: opt.option_order ?? 0,
          label: key,
          party: opt.party || null,
          colour_override: opt.colour_override || null,
        });
      }
    }
  }

  const isCrossPollster = pollsterOrder.length > 1;
  const palette = OPTION_PALETTES[payload.question_key] || FALLBACK_PALETTE;

  // Party mode: when ANY option carries a party/colour identity, party drives
  // the line colour and the pollster becomes the dash encoding (so the same
  // candidate shares a hue across pollsters). Otherwise keep the legacy scheme
  // (single-pollster → positional palette; cross-pollster → pollster bias).
  const optionColour = (o) => o.colour_override || partyColour(o.party);
  let partyMode = false;
  for (const slug of Object.keys(optionTuples)) {
    for (const o of optionTuples[slug].values()) {
      if (optionColour(o)) { partyMode = true; break; }
    }
    if (partyMode) break;
  }
  const pollsterDash = (i) =>
    i === 0 ? undefined : i === 1 ? "4 3" : i === 2 ? "1 2" : "6 2 1 2";

  const series = [];
  pollsterOrder.forEach((p, pIdx) => {
    const opts = Array.from(optionTuples[p.slug].values()).sort((a, b) => a.order - b.order);
    opts.forEach((o, idx) => {
      const positional = palette[o.order] || palette[idx] || FALLBACK_PALETTE[idx % FALLBACK_PALETTE.length];
      let colour, dash, legendName;
      if (partyMode) {
        // Party drives colour; options without a party fall back to positional
        // so they stay distinct. Pollster → dash on cross-pollster overlays.
        colour = optionColour(o) || positional;
        dash = isCrossPollster ? pollsterDash(pIdx) : undefined;
        legendName = isCrossPollster ? `${o.label} — ${p.name}` : o.label;
      } else {
        colour = isCrossPollster ? pollsterChipColour(p.bias, p.place).bg : positional;
        dash = isCrossPollster && idx > 0 ? (idx === 1 ? "4 3" : "1 2") : undefined;
        legendName = isCrossPollster ? `${p.name}: ${o.label}` : o.label;
      }
      series.push({
        dataKey: `${p.slug}__${o.label}`,
        legendName,
        stroke: colour,
        strokeDasharray: dash,
        pollster: p,
        option: o.label,
      });
    });
  });

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


// Presidential approval hero — the redesign's "clear view" block: portrait,
// big approve/disapprove numerals from the LATEST wave, delta vs the same
// pollster's previous wave (never cross-pollster — different houses aren't
// comparable), a stacked share bar, and the trend charts underneath.
// Renders nothing until the approval question has waves.
function PresidentialApproval({ payload }) {
  const info = useMemo(() => {
    if (!payload?.waves?.length) return null;
    const pick = (wave, re, exclude) => {
      const opt = (wave?.options || []).find((o) => {
        const l = o.label_en || "";
        return re.test(l) && (!exclude || !exclude.test(l));
      });
      return opt?.percentage ?? null;
    };
    const approveOf = (w) => pick(w, /satisf|approv/i, /dis/i);
    const disapproveOf = (w) => pick(w, /dissatisf|disapprov/i);

    const waves = [...payload.waves]
      .map((w) => ({ ...w, anchor: w.fielded_end || w.fielded_start }))
      .filter((w) => w.anchor && (approveOf(w) != null || disapproveOf(w) != null))
      .sort((a, b) => a.anchor.localeCompare(b.anchor));
    if (!waves.length) return null;

    // Composite over the trailing 60 days (anchored on the newest wave, so
    // the hero always reflects the last two months of AVAILABLE polling):
    // each pollster's most recent wave in the window, averaged — one
    // prolific house can't dominate. Falls back to single-poll display
    // when only one poll lands in the window.
    const dayShift = (iso, days) => {
      const d = new Date(`${iso}T00:00:00Z`);
      d.setUTCDate(d.getUTCDate() + days);
      return d.toISOString().slice(0, 10);
    };
    const latestAnchor = waves[waves.length - 1].anchor;
    const winStart = dayShift(latestAnchor, -60);
    const priorStart = dayShift(latestAnchor, -120);

    const compositeOver = (from, to) => {
      const byPollster = new Map();
      for (const w of waves) {
        if (w.anchor > to || w.anchor <= from) continue;
        byPollster.set(w.pollster_slug, w); // waves sorted ASC → keeps latest
      }
      const picks = Array.from(byPollster.values());
      if (!picks.length) return null;
      const mean = (fn) => {
        const vals = picks.map(fn).filter((v) => v != null);
        return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
      };
      return {
        approve: mean(approveOf),
        disapprove: mean(disapproveOf),
        polls: picks,
      };
    };

    const cur = compositeOver(winStart, latestAnchor);
    if (!cur || (cur.approve == null && cur.disapprove == null)) return null;
    const prior = compositeOver(priorStart, winStart);

    const single = cur.polls.length === 1 ? cur.polls[0] : null;
    return {
      approve: cur.approve,
      disapprove: cur.disapprove,
      dApprove: prior && cur.approve != null && prior.approve != null ? cur.approve - prior.approve : null,
      dDisapprove: prior && cur.disapprove != null && prior.disapprove != null ? cur.disapprove - prior.disapprove : null,
      caption: single
        ? `${(single.pollster_name_en || "").toUpperCase()} · FIELDED TO ${single.anchor}`
        : `AVG OF ${cur.polls.length} POLLSTERS' LATEST WAVES · TRAILING 60 DAYS TO ${latestAnchor}`,
      deltaNote: prior ? " · CHANGE VS PRECEDING 60 DAYS" : "",
    };
  }, [payload]);

  if (!info) return null;

  const Delta = ({ d }) => d == null ? null : (
    <span style={{ fontFamily: "var(--font-mono)", fontSize: "9.5px", color: "var(--faint)" }}>
      {d >= 0 ? "\u25b2" : "\u25bc"} {d >= 0 ? "+" : "\u2212"}{Math.abs(d).toFixed(1)}
    </span>
  );
  const Figure = ({ label, value, colour, delta }) => (
    <div>
      <div style={{ fontFamily: "var(--font-mono)", fontSize: "8.5px", letterSpacing: "0.12em",
                    color: "var(--faint)", marginBottom: "3px", textTransform: "uppercase" }}>{label}</div>
      <div style={{ display: "flex", alignItems: "baseline", gap: "7px" }}>
        <span style={{ fontFamily: "var(--font-headline)", fontSize: "30px", fontWeight: 500,
                       lineHeight: 1, color: colour }}>
          {value == null ? "\u2014" : `${value.toFixed(1)}%`}
        </span>
        <Delta d={delta} />
      </div>
    </div>
  );
  const rest = Math.max(0, 100 - (info.approve || 0) - (info.disapprove || 0));

  return (
    <div style={{ maxWidth: "560px" }}>
      <div style={{ display: "flex", alignItems: "flex-start", gap: "16px", marginBottom: "14px" }}>
        <img src="/figures/lai_chingte.jpg" alt="Lai Ching-te"
             style={{ width: "52px", height: "52px", borderRadius: "50%", objectFit: "cover",
                      objectPosition: "center top", flexShrink: 0 }} />
        <div>
          <div style={{ fontFamily: "var(--font-headline)", fontSize: "17px", fontWeight: 500, color: "var(--ink)" }}>
            Lai Ching-te 賴清德
          </div>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: "8.5px", letterSpacing: "0.1em",
                        color: "var(--party-dpp)", marginTop: "2px" }}>
            DPP · PRESIDENT OF THE REPUBLIC OF CHINA (TAIWAN)
          </div>
        </div>
      </div>
      <div style={{ display: "flex", gap: "24px", marginBottom: "14px" }}>
        <Figure label="Approve" value={info.approve} colour="var(--green)" delta={info.dApprove} />
        <Figure label="Disapprove" value={info.disapprove} colour="var(--muted)" delta={info.dDisapprove} />
      </div>
      <div style={{ height: "6px", display: "flex", marginBottom: "6px" }}>
        <div style={{ width: `${info.approve || 0}%`, background: "var(--green)" }} />
        <div style={{ width: `${info.disapprove || 0}%`, background: "var(--dot)" }} />
        <div style={{ width: `${rest}%`, background: "var(--soft)" }} />
      </div>
      <div style={{ fontFamily: "var(--font-mono)", fontSize: "8.5px", color: "var(--pale)",
                    letterSpacing: "0.08em" }}>
        {info.caption}{info.deltaNote}
      </div>
    </div>
  );
}

function PollTrendChart({ payload, height = 240, onOpenColours, hideLegend }) {
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
    <div style={{ position: "relative" }}>
      {!READ_ONLY && onOpenColours && (
        <button
          onClick={() => onOpenColours(payload)}
          title="Assign party / candidate colours to this chart's options"
          style={{
            position: "absolute", top: 0, right: 0, zIndex: 2,
            padding: "3px 8px", fontFamily: "var(--font-mono)", fontSize: "9px",
            letterSpacing: "0.06em", textTransform: "uppercase",
            border: "1px solid var(--border-color)", background: "var(--bg-card)",
            color: "var(--text-muted)", cursor: "pointer",
          }}
        >
          Colours
        </button>
      )}
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
        {!hideLegend && (
          <Legend
            wrapperStyle={{ fontFamily: "var(--font-mono)", fontSize: "10px" }}
            iconType="line"
          />
        )}
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
    </div>
  );
}

// Latest-wave values as a swatch legend — the design's "numbers written
// clearly next to the chart". Colours come from the SAME pivot the chart
// uses, so legend and lines can't disagree.
function CurrentValues({ payload }) {
  const { series } = useMemo(() => pivotByQuestion(payload), [payload]);
  const latest = payload?.waves?.length ? payload.waves[payload.waves.length - 1] : null;
  if (!latest) return null;
  const strokeFor = (label) =>
    series.find((sr) => sr.dataKey === `${latest.pollster_slug}__${label}`)?.stroke || "var(--muted)";
  const opts = [...(latest.options || [])].sort((a, b) => (a.option_order ?? 0) - (b.option_order ?? 0));
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "6px", marginTop: "10px" }}>
      {opts.map((o) => {
        const label = o.label_en || o.label_zh || `option_${o.option_order}`;
        const colour = strokeFor(label);
        return (
          <div key={label} style={{ display: "flex", alignItems: "center", gap: "8px", fontSize: "11.5px" }}>
            <span style={{ width: "14px", height: "2px", background: colour, flexShrink: 0 }} />
            <span style={{ color: "var(--body)", flex: 1, fontFamily: "var(--font-body)" }}>
              {o.label_en}{o.label_zh && o.label_zh !== o.label_en ? <span style={{ color: "var(--pale)" }}> {o.label_zh}</span> : null}
            </span>
            <span style={{ fontFamily: "var(--font-mono)", fontWeight: 600, color: colour }}>
              {o.percentage != null ? `${o.percentage.toFixed(1)}%` : "—"}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function FlagshipStrip({ flagship, payload, onOpenColours, compact, hero }) {
  // Right-rail shows live state when data exists (wave count + latest
  // date) and falls back to the static source attribution when empty —
  // so the attribution never duplicates the subtitle below.
  const waveCount = payload?.waves?.length || 0;
  const latestWave = waveCount > 0 ? payload.waves[payload.waves.length - 1] : null;
  const rightRail = latestWave
    ? `${waveCount} wave${waveCount === 1 ? "" : "s"} · latest ${fmtDate(latestWave.fielded_end || latestWave.fielded_start)}`
    : null;

  const chart = (
    <PollTrendChart payload={payload} height={compact ? 210 : 260}
                    onOpenColours={onOpenColours} hideLegend={compact && !hero} />
  );

  return (
    <section style={{ marginBottom: compact ? 0 : "32px", minWidth: 0 }}>
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
      {hero ? (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(340px, 1fr))",
                      gap: "20px 40px", alignItems: "center", marginBottom: "24px" }}>
          <div style={{ minWidth: 0 }}>{hero}</div>
          <div style={{ minWidth: 0 }}>{chart}</div>
        </div>
      ) : (
        <>
          {chart}
          {compact && <CurrentValues payload={payload} />}
        </>
      )}
    </section>
  );
}

// Group the /topics payload into the families shown in the "Other
// Trackers" selector: drop pinned flagships and zero-data questions, sort
// each family's questions most-used-first, and order the families by the
// canonical FAMILY_LABELS sequence (stable, not by volatile counts).
// Returned shape: [{ family, label, questions: [...] }]. Pure so PollsTab
// can both render it and resolve a family's top question for auto-open.
const FAMILY_ORDER = Object.keys(FAMILY_LABELS);

function buildOtherFamilies(topics) {
  if (!topics?.families) return [];
  const out = [];
  for (const fam of topics.families) {
    const questions = (fam.questions || [])
      .filter((q) => !FLAGSHIP_KEYS.has(q.question_key) && (q.approved_count || 0) > 0)
      .sort((a, b) => (b.approved_count - a.approved_count) || a.question_key.localeCompare(b.question_key));
    if (questions.length === 0) continue;
    out.push({ family: fam.family, label: FAMILY_LABELS[fam.family] || fam.family, questions });
  }
  out.sort((a, b) => {
    const ia = FAMILY_ORDER.indexOf(a.family);
    const ib = FAMILY_ORDER.indexOf(b.family);
    return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
  });
  return out;
}

// Two-tier selector for the "Other Trackers" section. Tier 1 is a compact
// family dropdown (scales as 2026 vote-intent races flood the list); tier 2
// is a pill row of that family's questions. Picking a family auto-opens its
// top question (handled in PollsTab), so tier 2 doubles as the active marker.
function OtherTrackers({ families, selectedFamily, selectedKey, onSelectFamily, onSelectQuestion }) {
  if (families.length === 0) {
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

  const activeFamily = families.find((f) => f.family === selectedFamily) || null;

  return (
    <div style={{ padding: "4px 0 12px 0" }}>
      {/* Tier 1 — family dropdown */}
      <select
        value={selectedFamily || ""}
        onChange={(e) => onSelectFamily(e.target.value || null)}
        style={{
          padding: "6px 10px",
          fontFamily: "var(--font-mono)",
          fontSize: "11px",
          letterSpacing: "0.06em",
          textTransform: "uppercase",
          background: "var(--bg-card)",
          color: "var(--text-primary)",
          border: "1px solid var(--border-color)",
          cursor: "pointer",
          minWidth: "240px",
        }}
      >
        <option value="">— Select category —</option>
        {families.map((f) => (
          <option key={f.family} value={f.family}>
            {f.label} ({f.questions.length})
          </option>
        ))}
      </select>

      {/* Tier 2 — questions within the chosen family. Family context is
          established by the dropdown, so pills show the readable question
          text (truncated, full text on hover) rather than the bare key. */}
      {activeFamily && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: "8px", marginTop: "12px" }}>
          {activeFamily.questions.map((q) => {
            const active = q.question_key === selectedKey;
            const label = q.question_text_en || q.question_key;
            const shown = label.length > 52 ? `${label.slice(0, 51)}…` : label;
            return (
              <button
                key={q.question_key}
                onClick={() => onSelectQuestion(q.question_key)}
                title={q.question_text_en || q.question_key}
                style={{
                  padding: "5px 10px",
                  fontFamily: "var(--font-mono)",
                  fontSize: "10px",
                  letterSpacing: "0.04em",
                  background: active ? "var(--accent)" : "var(--bg-card)",
                  color: active ? "#fff" : "var(--text-primary)",
                  border: "1px solid var(--border-color)",
                  cursor: "pointer",
                  display: "inline-flex",
                  gap: "8px",
                  alignItems: "baseline",
                  textAlign: "left",
                }}
              >
                <span>{shown}</span>
                <span style={{ opacity: 0.55 }}>· {q.approved_count}</span>
              </button>
            );
          })}
        </div>
      )}
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
        <PollsterChip slug={poll.pollster_slug} name={poll.pollster_name_en} bias={poll.pollster_bias} place={poll.pollster_place} />
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
  const [selectedFamily, setSelectedFamily] = useState(null);
  const [selectedKey, setSelectedKey] = useState(null);
  const [selectedPayload, setSelectedPayload] = useState(null);
  const [error, setError] = useState(null);
  const [pendingCount, setPendingCount] = useState(0);
  const [reviewOpen, setReviewOpen] = useState(false);
  const [entryOpen,  setEntryOpen]  = useState(false);
  const [colourPayload, setColourPayload] = useState(null); // chart payload whose colours are being edited

  // After saving colour assignments, refetch just the affected question so
  // the chart re-renders with the new party colours. Updates the flagship
  // store and/or the on-demand payload depending on where the key lives.
  const refreshQuestion = (key) => {
    if (!key) return;
    fetchPollsByQuestion(key).then((data) => {
      if (FLAGSHIP_KEYS.has(key)) setFlagshipData((prev) => ({ ...prev, [key]: data }));
      setSelectedPayload((cur) => (cur && cur.question_key === key ? data : cur));
    }).catch(() => {});
  };

  // After a manual entry / approve / dismiss, the public reads need a
  // refresh — recent feed + every flagship payload that could newly
  // have a wave. Shared between PollReviewQueue's onClose and
  // PollEntryModal's onCreated so the two paths converge on the same
  // post-write refresh.
  const refreshPublicReads = () => {
    fetchPolls({ limit: 30 }).then((d) => setRecentPolls(d?.polls || [])).catch(() => {});
    FLAGSHIPS.forEach((f) => {
      fetchPollsByQuestion(f.key)
        .then((data) => setFlagshipData((prev) => ({ ...prev, [f.key]: data })))
        .catch(() => {});
    });
  };

  // Pending count badge — admin build only. Light call (no JOINs the
  // public reads don't already do), refreshed on review-modal close.
  const loadPendingCount = () => {
    if (READ_ONLY) return;
    fetchPollCandidates()
      .then((r) => setPendingCount(r.total_pending || 0))
      .catch(() => setPendingCount(0));
  };
  useEffect(() => { loadPendingCount(); }, []);

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

  // "Other Trackers" families (flagships + zero-data questions stripped).
  // Drives both the tier-1 dropdown and top-question resolution for auto-open.
  const otherFamilies = useMemo(() => buildOtherFamilies(topicsData), [topicsData]);

  // Picking a family auto-opens its most-used question (questions are
  // pre-sorted most-used-first in buildOtherFamilies). Clearing the family
  // (— Select category —) drops the chart too.
  const selectFamily = (family) => {
    setSelectedFamily(family);
    if (!family) { setSelectedKey(null); return; }
    const fam = otherFamilies.find((f) => f.family === family);
    setSelectedKey(fam?.questions[0]?.question_key ?? null);
  };

  // Headline counts for the section right-rail.
  const totalApprovedPolls = recentPolls?.length ?? 0;
  const activePollsterCount = useMemo(
    () => (rosterData?.pollsters || []).filter((p) => (p.approved_count || 0) > 0).length,
    [rosterData],
  );

  return (
    <main style={{ padding: "28px 32px", minWidth: 0 }}>
      <header style={{
        marginBottom: "8px",
        display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "12px",
      }}>
        <div>
          <h1 style={{
            fontFamily: "var(--font-serif)",
            fontSize: "26px",
            fontWeight: 400,
            letterSpacing: "0.01em",
            margin: 0,
          }}>
            Taiwan Polling
          </h1>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: "11px",
                        color: "var(--text-muted)", marginTop: "4px" }}>
            Taiwan public opinion on identity, unification, presidential approval, and cross-strait attitudes.
            {activePollsterCount > 0 && ` · ${activePollsterCount} pollster${activePollsterCount === 1 ? "" : "s"} with data`}
          </div>
        </div>
        {!READ_ONLY && (
          <div style={{ display: "flex", gap: "6px", flexShrink: 0 }}>
            <button onClick={() => setEntryOpen(true)}
                    title="Add a poll manually (analyst-spotted, outside the AI pipeline)"
                    style={{
                      padding: "5px 12px",
                      fontFamily: "var(--font-mono)",
                      fontSize: "10px",
                      letterSpacing: "0.08em",
                      textTransform: "uppercase",
                      border: "1px solid var(--border-color)",
                      background: "transparent",
                      color: "var(--text-secondary)",
                      cursor: "pointer",
                      whiteSpace: "nowrap",
                    }}>
              + Add poll
            </button>
            <button onClick={() => setReviewOpen(true)}
                    title={`${pendingCount} pending`}
                    style={{
                      padding: "5px 12px",
                      fontFamily: "var(--font-mono)",
                      fontSize: "10px",
                      letterSpacing: "0.08em",
                      textTransform: "uppercase",
                      border: `1px solid ${pendingCount > 0 ? "var(--flag)" : "var(--border-color)"}`,
                      background: pendingCount > 0 ? "color-mix(in srgb, var(--flag) 12%, transparent)" : "transparent",
                      color: pendingCount > 0 ? "var(--flag)" : "var(--text-muted)",
                      cursor: "pointer",
                      whiteSpace: "nowrap",
                    }}>
              ✎ Review{pendingCount > 0 ? ` (${pendingCount})` : ""}
            </button>
          </div>
        )}
      </header>

      {error && (
        <div style={{ padding: "10px 14px", marginTop: "16px",
                      border: "1px solid var(--red)", background: "color-mix(in srgb, var(--red) 8%, transparent)",
                      color: "var(--red)", fontFamily: "var(--font-mono)", fontSize: "11px" }}>
          {error}
        </div>
      )}

      {/* Presidential approval — hero (latest-wave numbers + portrait) with
          the cross-pollster trend chart beside it. */}
      <FlagshipStrip flagship={APPROVAL_FLAGSHIP} payload={flagshipData[APPROVAL_FLAGSHIP.key]}
                     onOpenColours={setColourPayload} compact
                     hero={<PresidentialApproval payload={flagshipData[APPROVAL_FLAGSHIP.key]} />} />

      {/* NCCU identity + unification — half-width, side by side, each with
          the latest wave's numbers beside the chart. Source-faithful (all
          options visible). See [[feedback-analyst-charts]] for the rule
          against composite/summary lines on analyst charts. */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(380px, 1fr))",
                    gap: "12px 44px", alignItems: "start", marginBottom: "32px" }}>
        {NCCU_FLAGSHIPS.map((f) => (
          <FlagshipStrip key={f.key} flagship={f} payload={flagshipData[f.key]}
                         onOpenColours={setColourPayload} compact />
        ))}
      </div>

      {/* Other Trackers — two-tier: a category dropdown, then question pills
          within that category. Picking a category auto-opens its top
          question; picking a question fetches its /by-question payload and
          renders a 4th chart strip below. */}
      <SectionHeader right={otherFamilies.length
        ? `${otherFamilies.length} categor${otherFamilies.length === 1 ? "y" : "ies"}`
        : ""}>Other Trackers</SectionHeader>
      <OtherTrackers
        families={otherFamilies}
        selectedFamily={selectedFamily}
        selectedKey={selectedKey}
        onSelectFamily={selectFamily}
        onSelectQuestion={setSelectedKey}
      />

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
          <PollTrendChart payload={selectedPayload} height={300} onOpenColours={setColourPayload} />
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

      {reviewOpen && (
        <PollReviewQueue
          onClose={() => {
            setReviewOpen(false);
            loadPendingCount();
            refreshPublicReads();
          }}
          onResolveAll={() => setPendingCount(0)}
        />
      )}

      {entryOpen && (
        <PollEntryModal
          onClose={() => setEntryOpen(false)}
          onCreated={() => {
            setEntryOpen(false);
            refreshPublicReads();
          }}
        />
      )}

      {colourPayload && (
        <PollColourModal
          payload={colourPayload}
          onClose={() => setColourPayload(null)}
          onSaved={() => {
            const key = colourPayload.question_key;
            setColourPayload(null);
            refreshQuestion(key);
          }}
        />
      )}
    </main>
  );
}
