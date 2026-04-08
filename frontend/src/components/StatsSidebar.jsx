import { SentimentTrendChart, TopicBreakdownChart } from "./SignalCharts";

function StabilityGauge({ label, score, days, compact }) {
  const safeScore = score ?? 0;
  const color = safeScore > 0.3
    ? "var(--accent-red)"
    : safeScore < -0.3
    ? "var(--accent-green)"
    : "var(--accent-amber)";

  return (
    <div style={{
      background: "var(--bg-card)",
      border: "1px solid var(--border-color)",
      borderRadius: "3px",
      padding: compact ? "10px 12px" : "14px 16px",
      marginBottom: "8px",
    }}>
      <div style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        marginBottom: "8px",
      }}>
        <span style={{
          fontSize: "10px",
          fontFamily: "var(--font-mono)",
          color: "var(--text-muted)",
          textTransform: "uppercase",
          letterSpacing: "1px",
        }}>
          {label}
        </span>
        <span style={{
          fontSize: compact ? "13px" : "16px",
          fontFamily: "var(--font-mono)",
          fontWeight: 600,
          color,
        }}>
          {safeScore > 0 ? "+" : ""}{safeScore.toFixed(2)}
        </span>
      </div>
      <div style={{
        display: "flex",
        justifyContent: "space-between",
        marginBottom: "6px",
        fontSize: "9px",
        fontFamily: "var(--font-mono)",
        color: "var(--text-muted)",
      }}>
        <span>Hostile</span>
        <span>Cooperative</span>
      </div>
      <div style={{
        height: "4px",
        background: "var(--bg-secondary)",
        borderRadius: "3px",
        position: "relative",
      }}>
        <div style={{
          position: "absolute",
          inset: 0,
          borderRadius: "3px",
          background: "linear-gradient(to right, var(--accent-red), var(--accent-amber), var(--accent-green))",
          opacity: 0.25,
        }} />
        <div style={{
          position: "absolute",
          left: `${((safeScore + 1) / 2) * 100}%`,
          top: "50%",
          width: compact ? "10px" : "12px",
          height: compact ? "10px" : "12px",
          borderRadius: "50%",
          background: color,
          transform: "translate(-50%, -50%)",
          border: "2px solid var(--bg-card)",
          boxShadow: "0 1px 3px rgba(0,0,0,0.15)",
          transition: "left 0.5s ease",
        }} />
      </div>
      {days && (
        <p style={{
          textAlign: "center",
          fontSize: "10px",
          fontFamily: "var(--font-body)",
          color: "var(--text-muted)",
          marginTop: "6px",
        }}>
          {days}-day weighted average
        </p>
      )}
    </div>
  );
}

export default function StatsSidebar({ stats, onTopicClick }) {
  if (!stats) return null;

  const sectionTitle = () => ({
    fontSize: "10px",
    fontFamily: "var(--font-mono)",
    color: "var(--text-muted)",
    textTransform: "uppercase",
    letterSpacing: "2px",
    marginBottom: "14px",
    fontWeight: 500,
  });

  return (
    <div>
      {/* Strait Watch */}
      <div style={{ marginBottom: "28px" }}>
        <h3 style={sectionTitle()}>Strait Watch</h3>

        <StabilityGauge
          label="Overall"
          score={stats.avg_sentiment_score}
          days={stats.period_days}
        />

        {stats.sentiment_by_country?.map((c) => (
          <StabilityGauge
            key={c.country}
            label={
              c.country === "PRC" ? "PRC Sources" :
              c.country === "TW" ? "Taiwan Sources" :
              "International Sources"
            }
            score={c.avg_score}
          />
        ))}

        {stats.sentiment_by_bias?.length > 0 && (
          <>
            <div style={{
              fontSize: "10px",
              fontFamily: "var(--font-mono)",
              color: "var(--text-muted)",
              textTransform: "uppercase",
              letterSpacing: "1.5px",
              marginTop: "12px",
              marginBottom: "8px",
            }}>
              Taiwan by camp
            </div>
            {stats.sentiment_by_bias.map((b) => (
              <StabilityGauge
                key={b.bias}
                label={
                  b.bias === "green" ? "Green" :
                  b.bias === "green_leaning" ? "Green-leaning" :
                  b.bias === "blue" ? "Blue" : b.bias
                }
                score={b.avg_score}
                compact
              />
            ))}
          </>
        )}
      </div>

      {/* Stability Trend Chart */}
      <SentimentTrendChart
        data={stats.sentiment_trend}
        days={stats.period_days}
      />

      {/* Topic Breakdown Chart */}
      <TopicBreakdownChart
        data={stats.topics}
        onTopicClick={onTopicClick}
      />

      {/* Source Health */}
      <div style={{ marginBottom: "28px" }}>
        <h3 style={sectionTitle()}>Sources</h3>
        <div style={{
          background: "var(--bg-card)",
          border: "1px solid var(--border-color)",
          borderRadius: "3px",
          padding: "12px 16px",
        }}>
          {stats.sources?.map((s, i) => (
            <div
              key={i}
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                padding: "5px 0",
                borderBottom: i < stats.sources.length - 1
                  ? "1px solid var(--border-color)"
                  : "none",
              }}
            >
              <span style={{
                fontSize: "13px",
                fontFamily: "var(--font-body)",
                color: "var(--text-secondary)",
                display: "flex",
                alignItems: "center",
                gap: "6px",
              }}>
                <span style={{
                  width: "8px",
                  height: "8px",
                  borderRadius: "50%",
                  background: s.country === "PRC"
                    ? "var(--accent-red)"
                    : "var(--accent-blue)",
                  display: "inline-block",
                }} />
                {s.name}
              </span>
              <span style={{
                fontFamily: "var(--font-mono)",
                fontSize: "12px",
                color: "var(--text-muted)",
              }}>
                {s.count}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Key Entities */}
      <div>
        <h3 style={sectionTitle()}>Key Entities</h3>
        <div style={{
          background: "var(--bg-card)",
          border: "1px solid var(--border-color)",
          borderRadius: "3px",
          padding: "12px 16px",
        }}>
          {stats.top_entities?.slice(0, 10).map((e, i) => (
            <div
              key={i}
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                padding: "4px 0",
                borderBottom: i < Math.min(stats.top_entities.length, 10) - 1
                  ? "1px solid var(--border-color)"
                  : "none",
              }}
            >
              <span style={{
                fontSize: "13px",
                fontFamily: "var(--font-body)",
                color: "var(--text-secondary)",
              }}>
                {e.entity_name_en}
                <span style={{
                  fontSize: "10px",
                  color: "var(--text-muted)",
                  fontFamily: "var(--font-mono)",
                  marginLeft: "6px",
                }}>
                  {e.entity_type}
                </span>
              </span>
              <span style={{
                fontFamily: "var(--font-mono)",
                fontSize: "12px",
                color: "var(--text-muted)",
              }}>
                {e.mentions}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}