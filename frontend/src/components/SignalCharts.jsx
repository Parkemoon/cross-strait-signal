import { useState } from "react";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  ReferenceLine,
} from "recharts";
import { bandColour } from "../sentimentBand";

const TOPIC_LABELS = {
  MIL_EXERCISE:       "Mil Exercise",
  MIL_MOVEMENT:       "Force Movement",
  MIL_HARDWARE:       "Hardware",
  MIL_POLICY:         "Mil. Policy",
  ARMS_SALES:         "Arms Sales",
  MARITIME_GREY:      "Maritime Grey-Zone",
  SEC_LAWFARE:        "Espionage & Lawfare",
  INFO_CYBER:         "Info & Cyber",
  POL_TONGDU:         "統獨",
  CROSS_STRAIT_REG:   "Cross-Strait Reg.",
  CULTURE:            "Culture",
  UNITED_FRONT_INTEG: "United Front",
  PARTY_VISIT:        "Party Visit",
  US_RELATIONS:       "US Relations",
  INTL_RELATIONS:     "Third-Country Dip.",
  DIP_VISIT:          "Diplomatic Visit",
  INT_ORG:            "Intl Orgs",
  DIP_SANCTIONS:      "Sanctions",
  POL_DOMESTIC_TW:    "TW Politics",
  POL_DOMESTIC_PRC:   "PRC Politics",
  HK_MAC:             "HK/Macao",
  ECON_TRADE:         "Trade & Economy",
  SCI_TECH:           "Sci/Tech",
  TRANSPORT:          "Transport",
  DIP_STATEMENT:      "Diplomacy",
  ECON_INVEST:        "Investment",
  ENERGY:             "Energy",
  US_PRC:             "US-PRC",
  US_TAIWAN:          "US-Taiwan",
  INFO_WARFARE:       "Info Warfare",
  CYBER:              "Cyber",
  LEGAL_GREY:         "Grey Zone",
  SPORT:              "Sport",
  HUMANITARIAN:       "Humanitarian",
};

// Rail section label — matches StatsSidebar's RailLabel.
function RailLabel({ title, right }) {
  return (
    <div style={{
      borderTop: "1px solid var(--hair)",
      paddingTop: "14px",
      marginBottom: "8px",
      display: "flex",
      justifyContent: "space-between",
      alignItems: "baseline",
    }}>
      <span style={{
        fontFamily: "var(--font-mono)",
        fontSize: "9px",
        fontWeight: 600,
        letterSpacing: "0.2em",
        textTransform: "uppercase",
        color: "var(--ink)",
      }}>{title}</span>
      {right}
    </div>
  );
}

function fmtSigned(v, digits = 2) {
  if (v == null || Number.isNaN(v)) return "0.00";
  return `${v > 0 ? "+" : ""}${v.toFixed(digits)}`;
}

function SentimentTooltip({ active, payload, label, mode }) {
  if (!active || !payload?.length) return null;
  // Select by dataKey, not position — with the dual-view baseline line the
  // payload carries two entries and their order follows render order.
  const main = payload.find((p) => p.dataKey === "score") ?? payload[0];
  const base = payload.find((p) => p.dataKey === "base");
  const score = main?.value;
  const row = main?.payload || {};
  const count = row.count;
  return (
    <div style={{
      background: "var(--bg)",
      border: "1px solid var(--hair)",
      boxShadow: "0 10px 24px rgba(28,26,22,0.13)",
      padding: "8px 12px",
      fontSize: "11px",
      fontFamily: "var(--font-mono)",
    }}>
      <div style={{ color: "var(--faint)", marginBottom: "4px", letterSpacing: "0.08em" }}>{label}</div>
      <div style={{ color: bandColour(score), fontWeight: 600 }}>
        {mode === "adj" ? "Excess " : ""}{fmtSigned(score, 3)}
      </div>
      {mode === "adj" && row.rawScore != null && row.normScore != null && (
        <div style={{ color: "var(--muted)", fontSize: "10px", marginTop: "2px" }}>
          Raw {fmtSigned(row.rawScore, 2)} · Norm {fmtSigned(row.normScore, 2)}
        </div>
      )}
      {mode !== "adj" && row.normScore != null && row.excessScore != null && (
        <div style={{ color: "var(--muted)", fontSize: "10px", marginTop: "2px" }}>
          Norm {fmtSigned(row.normScore, 2)} · Excess {fmtSigned(row.excessScore, 2)}
        </div>
      )}
      {base?.value != null && (
        <div style={{ color: "var(--muted)", fontSize: "10px", marginTop: "2px" }}>
          Gemini {fmtSigned(base.value, 3)}
        </div>
      )}
      <div style={{ color: "var(--faint)", fontSize: "10px", marginTop: "2px" }}>
        {count} articles
      </div>
    </div>
  );
}

// End-of-line dot: only the last non-null point gets a marker, coloured by
// its sentiment band — the design's "amber end dot" made band-aware.
function makeEndDot(formatted) {
  let lastIdx = -1;
  formatted.forEach((d, i) => { if (d.score != null) lastIdx = i; });
  return function EndDot(props) {
    const { cx, cy, index, value } = props;
    if (index !== lastIdx || value == null) return null;
    return <circle cx={cx} cy={cy} r={2.5} fill={bandColour(value)} />;
  };
}

// `baseline` (optional): a second {date, avg_score}[] series drawn as a grey
// dashed line — the alt-model lens's "Both" view overlays production Gemini
// this way. `accent` (optional) recolours the main line (the model's tint).
export function SentimentTrendChart({ data, days, baseline, accent }) {
  const [mode, setMode] = useState("raw");

  if (!data || data.length === 0) {
    return (
      <div style={{
        padding: "24px 0",
        color: "var(--muted)",
        fontFamily: "var(--font-body)",
        fontSize: "11px",
      }}>
        No trend data for this period
      </div>
    );
  }

  const hasExcess = data.some((d) => d.avg_excess != null);
  const activeMode = hasExcess ? mode : "raw";

  const baseByDate = {};
  (baseline || []).forEach((d) => {
    baseByDate[d.date] = activeMode === "adj" && d.avg_excess != null ? d.avg_excess : d.avg_score;
  });

  const formatted = data.map((d) => {
    const rawVal = d.avg_score == null ? null : Number(d.avg_score.toFixed(3));
    const excVal = d.avg_excess == null ? null : Number(d.avg_excess.toFixed(3));
    const normVal = d.avg_baseline == null ? null : Number(d.avg_baseline.toFixed(3));
    return {
      date: d.date?.slice(5),
      // A day with articles but no scores yields avg_score: null; keep it null
      // (a gap in the line) rather than letting ?.toFixed → undefined → NaN
      // propagate into the chart and the "NaN" tooltip.
      score: activeMode === "adj" ? excVal : rawVal,
      rawScore: rawVal,
      excessScore: excVal,
      normScore: normVal,
      base: baseline
        ? (baseByDate[d.date] == null ? null : Number(baseByDate[d.date].toFixed(3)))
        : undefined,
      count: d.article_count,
    };
  });

  const stroke = accent || "var(--ink)";
  const first = formatted[0]?.date;
  const last = formatted[formatted.length - 1]?.date;

  const modeToggle = hasExcess ? (
    <span
      style={{
        display: "inline-flex",
        gap: "4px",
        fontFamily: "var(--font-mono)",
        fontSize: "8.5px",
        letterSpacing: "0.1em",
      }}
      title="Toggle between raw headline sentiment and Source x Topic baseline-adjusted excess tone"
    >
      {[
        { key: "raw", label: "RAW" },
        { key: "adj", label: "ADJ" },
      ].map((opt, idx) => (
        <span key={opt.key} style={{ display: "inline-flex", alignItems: "center", gap: "4px" }}>
          {idx > 0 && <span style={{ color: "var(--dot)" }}>·</span>}
          <button
            type="button"
            onClick={() => setMode(opt.key)}
            style={{
              background: "none",
              border: "none",
              padding: 0,
              cursor: "pointer",
              fontFamily: "var(--font-mono)",
              fontSize: "8.5px",
              letterSpacing: "0.1em",
              fontWeight: activeMode === opt.key ? 700 : 400,
              color: activeMode === opt.key ? "var(--ink)" : "var(--pale)",
              borderBottom: activeMode === opt.key ? "1px solid var(--ink)" : "1px solid transparent",
            }}
          >
            {opt.label}
          </button>
        </span>
      ))}
    </span>
  ) : null;

  return (
    <div style={{ marginBottom: "18px" }}>
      <RailLabel title={`Trend — ${days} days`} right={modeToggle} />
      <ResponsiveContainer width="100%" height={72}>
        <LineChart data={formatted} margin={{ top: 6, right: 6, bottom: 0, left: 6 }}>
          <XAxis dataKey="date" hide />
          <YAxis domain={[-1, 1]} hide />
          <Tooltip content={<SentimentTooltip mode={activeMode} />} />
          <ReferenceLine y={0} stroke="var(--hair)" strokeDasharray="2 3" />
          {!baseline && activeMode === "raw" && hasExcess && (
            <Line
              type="monotone"
              dataKey="normScore"
              stroke="var(--dot)"
              strokeWidth={1}
              strokeDasharray="2 3"
              dot={false}
              isAnimationActive={false}
            />
          )}
          {baseline && (
            <Line
              type="monotone"
              dataKey="base"
              stroke="var(--dot)"
              strokeWidth={1.2}
              strokeDasharray="4 3"
              dot={false}
              isAnimationActive={false}
            />
          )}
          <Line
            type="monotone"
            dataKey="score"
            stroke={stroke}
            strokeWidth={1.2}
            dot={makeEndDot(formatted)}
            activeDot={{ r: 3.5, fill: stroke }}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
      <div style={{
        display: "flex",
        justifyContent: "space-between",
        marginTop: "3px",
        fontSize: "8.5px",
        fontFamily: "var(--font-mono)",
        color: "var(--pale)",
        letterSpacing: "0.08em",
      }}>
        <span>{first}</span>
        <span>{activeMode === "adj" ? "◀ −1 MORE HOSTILE · +1 MORE COOP VS NORM ▶" : "◀ −1 HOSTILE · +1 COOPERATIVE ▶"}</span>
        <span>{last}</span>
      </div>
    </div>
  );
}

// Dotted-leader topic list — label … count, click to filter.
export function TopicBreakdownChart({ data, onTopicClick }) {
  if (!data || data.length === 0) {
    return (
      <div style={{
        padding: "24px 0",
        color: "var(--muted)",
        fontFamily: "var(--font-body)",
        fontSize: "11px",
      }}>
        No topic data for this period
      </div>
    );
  }

  const rows = data.slice(0, 8).map((d) => ({
    topic: d.topic_primary,
    label: TOPIC_LABELS[d.topic_primary] || d.topic_primary?.replace(/_/g, " "),
    count: d.count,
  }));

  return (
    <div style={{ marginBottom: "18px" }}>
      <RailLabel title="Topics — 30 days" />
      <div style={{ display: "flex", flexDirection: "column", gap: "5px" }}>
        {rows.map((r) => (
          <div
            key={r.topic}
            className={onTopicClick ? "filter-row" : undefined}
            onClick={onTopicClick ? () => onTopicClick(r.topic) : undefined}
            title={onTopicClick ? `Filter by ${r.label}` : undefined}
            onMouseEnter={onTopicClick ? (e) => { e.currentTarget.firstChild.style.color = "var(--ink)"; } : undefined}
            onMouseLeave={onTopicClick ? (e) => { e.currentTarget.firstChild.style.color = "var(--body)"; } : undefined}
            style={{
              display: "flex",
              alignItems: "baseline",
              justifyContent: "space-between",
              fontSize: "11px",
              color: "var(--body)",
              cursor: onTopicClick ? "pointer" : "default",
            }}
          >
            <span style={{ fontFamily: "var(--font-body)", transition: "color 0.1s" }}>{r.label}</span>
            <span style={{ flex: 1, borderBottom: "1px dotted var(--dot)", margin: "0 6px" }} />
            <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--faint)" }}>{r.count}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
