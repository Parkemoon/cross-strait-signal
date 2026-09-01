import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  ReferenceLine,
} from "recharts";
import { bandColour } from "../sentimentBand";

const TOPIC_LABELS = {
  MIL_EXERCISE:    "Mil Exercise",
  MIL_MOVEMENT:    "Force Movement",
  MIL_HARDWARE:    "Hardware",
  MIL_POLICY:      "Mil. Policy",
  DIP_STATEMENT:   "Diplomacy",
  DIP_VISIT:       "Diplomatic Visit",
  DIP_SANCTIONS:   "Sanctions",
  PARTY_VISIT:     "Party Visit",
  ARMS_SALES:      "Arms Sales",
  ECON_TRADE:      "Trade",
  ECON_INVEST:     "Investment",
  ENERGY:          "Energy",
  SCI_TECH:        "Sci/Tech",
  POL_DOMESTIC_TW: "TW Politics",
  POL_DOMESTIC_PRC:"PRC Politics",
  POL_TONGDU:      "統獨",
  US_PRC:          "US-PRC",
  US_TAIWAN:       "US-Taiwan",
  HK_MAC:          "HK/Macao",
  INFO_WARFARE:    "Info Warfare",
  CYBER:           "Cyber",
  LEGAL_GREY:      "Grey Zone",
  CULTURE:         "Culture",
  SPORT:           "Sport",
  TRANSPORT:       "Transport",
  INT_ORG:         "Intl Orgs",
  HUMANITARIAN:    "Humanitarian",
};

// Rail section label — matches StatsSidebar's RailLabel.
function RailLabel({ title }) {
  return (
    <div style={{
      borderTop: "1px solid var(--hair)",
      paddingTop: "14px",
      marginBottom: "8px",
      fontFamily: "var(--font-mono)",
      fontSize: "9px",
      fontWeight: 600,
      letterSpacing: "0.2em",
      textTransform: "uppercase",
      color: "var(--ink)",
    }}>{title}</div>
  );
}

function SentimentTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  // Select by dataKey, not position — with the dual-view baseline line the
  // payload carries two entries and their order follows render order.
  const main = payload.find((p) => p.dataKey === "score") ?? payload[0];
  const base = payload.find((p) => p.dataKey === "base");
  const score = main?.value;
  const count = main?.payload?.count;
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
        {score > 0 ? "+" : ""}{score?.toFixed(3)}
      </div>
      {base?.value != null && (
        <div style={{ color: "var(--muted)", fontSize: "10px", marginTop: "2px" }}>
          Gemini {base.value > 0 ? "+" : ""}{base.value.toFixed(3)}
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

  const baseByDate = {};
  (baseline || []).forEach((d) => { baseByDate[d.date] = d.avg_score; });

  const formatted = data.map((d) => ({
    date: d.date?.slice(5),
    // A day with articles but no scores yields avg_score: null; keep it null
    // (a gap in the line) rather than letting ?.toFixed → undefined → NaN
    // propagate into the chart and the "NaN" tooltip.
    score: d.avg_score == null ? null : Number(d.avg_score.toFixed(3)),
    base: baseline
      ? (baseByDate[d.date] == null ? null : Number(baseByDate[d.date].toFixed(3)))
      : undefined,
    count: d.article_count,
  }));

  const stroke = accent || "var(--ink)";
  const first = formatted[0]?.date;
  const last = formatted[formatted.length - 1]?.date;

  return (
    <div style={{ marginBottom: "18px" }}>
      <RailLabel title={`Trend — ${days} days`} />
      <ResponsiveContainer width="100%" height={72}>
        <LineChart data={formatted} margin={{ top: 6, right: 6, bottom: 0, left: 6 }}>
          <XAxis dataKey="date" hide />
          <YAxis domain={[-1, 1]} hide />
          <Tooltip content={<SentimentTooltip />} />
          <ReferenceLine y={0} stroke="var(--hair)" strokeDasharray="2 3" />
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
        <span>◀ −1 HOSTILE · +1 COOPERATIVE ▶</span>
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
