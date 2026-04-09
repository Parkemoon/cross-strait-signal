import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  ReferenceLine, BarChart, Bar, Cell, LabelList
} from "recharts";

const TOPIC_COLORS = {
  MIL_EXERCISE: "var(--accent-red)",
  MIL_MOVEMENT: "var(--accent-red)",
  MIL_HARDWARE: "var(--accent-red)",
  DIP_STATEMENT: "var(--accent-amber)",
  DIP_VISIT: "var(--accent-amber)",
  DIP_SANCTIONS: "var(--accent-amber)",
  ECON_TRADE: "var(--accent-green)",
  ECON_INVEST: "var(--accent-green)",
  POL_DOMESTIC: "var(--accent-purple)",
  POL_TONGDU: "var(--accent-red)",
  INFO_WARFARE: "var(--accent-amber)",
  LEGAL_GREY: "var(--accent-teal)",
  HUMANITARIAN: "var(--accent-blue)",
};

const TOPIC_LABELS = {
  MIL_EXERCISE: "Mil Exercise",
  MIL_MOVEMENT: "Force Movement",
  MIL_HARDWARE: "Hardware",
  DIP_STATEMENT: "Diplomacy",
  DIP_VISIT: "State Visit",
  DIP_SANCTIONS: "Sanctions",
  ECON_TRADE: "Trade",
  ECON_INVEST: "Investment",
  POL_DOMESTIC: "Domestic",
  POL_TONGDU: "統獨",
  INFO_WARFARE: "Info Warfare",
  LEGAL_GREY: "Grey Zone",
  HUMANITARIAN: "Humanitarian",
};

function SentimentTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  const score = payload[0]?.value;
  const color = score > 0.3
    ? "var(--accent-red)"
    : score < -0.3
    ? "var(--accent-green)"
    : "var(--accent-amber)";
  return (
    <div style={{
      background: "var(--bg-card)",
      border: "1px solid var(--border-color)",
      borderRadius: "3px",
      padding: "8px 12px",
      fontSize: "12px",
      fontFamily: "var(--font-mono)",
    }}>
      <div style={{ color: "var(--text-muted)", marginBottom: "4px" }}>{label}</div>
      <div style={{ color, fontWeight: 600 }}>
        {score > 0 ? "+" : ""}{score?.toFixed(3)}
      </div>
      <div style={{ color: "var(--text-muted)", fontSize: "10px", marginTop: "2px" }}>
        {payload[1]?.value} articles
      </div>
    </div>
  );
}

export function SentimentTrendChart({ data, days }) {
  if (!data || data.length === 0) {
    return (
      <div style={{
        padding: "32px",
        textAlign: "center",
        color: "var(--text-muted)",
        fontFamily: "var(--font-mono)",
        fontSize: "12px",
      }}>
        No trend data for this period
      </div>
    );
  }

  const formatted = data.map((d) => ({
    date: d.date?.slice(5),
    score: parseFloat(d.avg_score?.toFixed(3)),
    count: d.article_count,
  }));

  return (
    <div style={{ marginBottom: "28px" }}>
      <div style={{
        fontSize: "10px",
        fontFamily: "var(--font-mono)",
        color: "var(--text-muted)",
        textTransform: "uppercase",
        letterSpacing: "2px",
        marginBottom: "14px",
        fontWeight: 500,
      }}>
        Stability Trend — {days}d
      </div>
      <div style={{
        background: "var(--bg-card)",
        border: "1px solid var(--border-color)",
        borderRadius: "3px",
        padding: "16px 8px 8px",
      }}>
        <ResponsiveContainer width="100%" height={120}>
          <LineChart data={formatted} margin={{ top: 4, right: 8, bottom: 0, left: -8 }}>
            <XAxis
              dataKey="date"
              tick={{ fontSize: 9, fontFamily: "var(--font-mono)", fill: "var(--text-muted)" }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              yAxisId="score"
              domain={[-1, 1]}
              ticks={[-1, -0.5, 0, 0.5, 1]}
              tickFormatter={(v) => v === 1 ? "+1" : v === -1 ? "-1" : v}
              width={28}
              tick={{ fontSize: 9, fontFamily: "var(--font-mono)", fill: "var(--text-muted)" }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis yAxisId="count" hide />
            <Tooltip content={<SentimentTooltip />} />
            <ReferenceLine yAxisId="score" y={0} stroke="var(--border-color)" strokeDasharray="3 3" />
            <ReferenceLine yAxisId="score" y={0.3} stroke="var(--accent-red)" strokeOpacity={0.2} strokeDasharray="2 4" />
            <ReferenceLine yAxisId="score" y={-0.3} stroke="var(--accent-green)" strokeOpacity={0.2} strokeDasharray="2 4" />
            <Line
              yAxisId="score"
              type="monotone"
              dataKey="score"
              stroke="var(--accent-teal)"
              strokeWidth={2}
              dot={{ r: 3, fill: "var(--accent-teal)", strokeWidth: 0 }}
              activeDot={{ r: 5, fill: "var(--accent-teal)" }}
            />
            <Line
              yAxisId="count"
              dataKey="count"
              stroke="transparent"
              dot={false}
            />
          </LineChart>
        </ResponsiveContainer>
        <div style={{
          display: "flex",
          justifyContent: "space-between",
          padding: "6px 8px 0",
          fontSize: "9px",
          fontFamily: "var(--font-mono)",
          color: "var(--text-muted)",
        }}>
          <span style={{ color: "var(--accent-red)" }}>Hostile</span>
          <span style={{ color: "var(--accent-green)" }}>Cooperative</span>
        </div>
      </div>
    </div>
  );
}

export function TopicBreakdownChart({ data, onTopicClick }) {
  if (!data || data.length === 0) {
    return (
      <div style={{
        padding: "32px",
        textAlign: "center",
        color: "var(--text-muted)",
        fontFamily: "var(--font-mono)",
        fontSize: "12px",
      }}>
        No topic data for this period
      </div>
    );
  }

  const formatted = data.slice(0, 10).map((d) => ({
    topic: d.topic_primary,
    label: TOPIC_LABELS[d.topic_primary] || d.topic_primary?.replace(/_/g, " "),
    count: d.count,
    color: TOPIC_COLORS[d.topic_primary] || "var(--accent-teal)",
  }));

  return (
    <div style={{ marginBottom: "28px" }}>
      <div style={{
        fontSize: "10px",
        fontFamily: "var(--font-mono)",
        color: "var(--text-muted)",
        textTransform: "uppercase",
        letterSpacing: "2px",
        marginBottom: "14px",
        fontWeight: 500,
      }}>
        Topic Breakdown
      </div>
      <div style={{
        background: "var(--bg-card)",
        border: "1px solid var(--border-color)",
        borderRadius: "3px",
        padding: "16px 8px 8px",
      }}>
        <ResponsiveContainer width="100%" height={220}>
          <BarChart
            data={formatted}
            layout="vertical"
            margin={{ top: 0, right: 40, bottom: 0, left: 4 }}
            onClick={(data) => {
              if (data?.activePayload?.[0] && onTopicClick) {
                onTopicClick(data.activePayload[0].payload.topic);
              }
            }}
            style={{ cursor: onTopicClick ? "pointer" : "default" }}
          >
            <XAxis
              type="number"
              tick={{ fontSize: 9, fontFamily: "var(--font-mono)", fill: "var(--text-muted)" }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              type="category"
              dataKey="label"
              width={72}
              tick={{ fontSize: 9, fontFamily: "var(--font-mono)", fill: "var(--text-muted)" }}
              axisLine={false}
              tickLine={false}
            />
            <Tooltip
              cursor={{ fill: "var(--bg-secondary)" }}
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null;
                return (
                  <div style={{
                    background: "var(--bg-card)",
                    border: "1px solid var(--border-color)",
                    borderRadius: "3px",
                    padding: "6px 10px",
                    fontSize: "12px",
                    fontFamily: "var(--font-mono)",
                    color: "var(--text-primary)",
                  }}>
                    {payload[0].payload.label}: {payload[0].value}
                    {onTopicClick && (
                      <div style={{ fontSize: "10px", color: "var(--text-muted)", marginTop: "2px" }}>
                        Click to filter
                      </div>
                    )}
                  </div>
                );
              }}
            />
            <Bar dataKey="count" radius={[0, 2, 2, 0]}>
              {formatted.map((entry, i) => (
                <Cell key={i} fill={entry.color} fillOpacity={0.8} />
              ))}
              <LabelList
                dataKey="count"
                position="right"
                style={{ fontSize: 9, fontFamily: "var(--font-mono)", fill: "var(--text-muted)" }}
              />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
        {onTopicClick && (
          <p style={{
            textAlign: "center",
            fontSize: "10px",
            fontFamily: "var(--font-mono)",
            color: "var(--text-muted)",
            marginTop: "6px",
          }}>
            Click a bar to filter by topic
          </p>
        )}
      </div>
    </div>
  );
}