export default function StatsSidebar({ stats }) {
  if (!stats) return null;

  return (
    <div>
      {/* Sentiment gauge */}
      <div
        style={{
          background: "var(--bg-card)",
          padding: "16px",
          borderRadius: "4px",
          marginBottom: "16px",
        }}
      >
        <h3
          style={{
            fontSize: "11px",
            color: "var(--text-muted)",
            textTransform: "uppercase",
            letterSpacing: "1.5px",
            marginBottom: "12px",
            fontFamily: "'JetBrains Mono', 'Courier New', monospace",
          }}
        >
          Cross-Strait Temperature
        </h3>
        <div
          style={{
            height: "8px",
            background: "var(--bg-secondary)",
            borderRadius: "4px",
            position: "relative",
            marginBottom: "6px",
          }}
        >
          <div
            style={{
              position: "absolute",
              left: `${((stats.avg_sentiment_score + 1) / 2) * 100}%`,
              top: "-4px",
              width: "16px",
              height: "16px",
              borderRadius: "50%",
              background:
                stats.avg_sentiment_score > 0.3
                  ? "var(--accent-red)"
                  : stats.avg_sentiment_score < -0.3
                  ? "var(--accent-green)"
                  : "var(--accent-amber)",
              transform: "translateX(-50%)",
              transition: "left 0.5s",
            }}
          />
        </div>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            fontSize: "10px",
            color: "var(--text-muted)",
            fontFamily: "'JetBrains Mono', 'Courier New', monospace",
          }}
        >
          <span>CONCILIATORY</span>
          <span>ESCALATORY</span>
        </div>
      </div>

      {/* Source health */}
      <div
        style={{
          background: "var(--bg-card)",
          padding: "16px",
          borderRadius: "4px",
          marginBottom: "16px",
        }}
      >
        <h3
          style={{
            fontSize: "11px",
            color: "var(--text-muted)",
            textTransform: "uppercase",
            letterSpacing: "1.5px",
            marginBottom: "12px",
            fontFamily: "'JetBrains Mono', 'Courier New', monospace",
          }}
        >
          Source Health
        </h3>
        {stats.sources?.map((s, i) => (
          <div
            key={i}
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              padding: "4px 0",
              fontSize: "13px",
            }}
          >
            <span style={{ color: "var(--text-secondary)" }}>
              <span
                style={{
                  color: s.country === "PRC" ? "var(--accent-red)" : "var(--accent-blue)",
                  marginRight: "6px",
                }}
              >
                ●
              </span>
              {s.name}
            </span>
            <span
              style={{
                color: "var(--text-muted)",
                fontFamily: "'JetBrains Mono', 'Courier New', monospace",
                fontSize: "12px",
              }}
            >
              {s.count}
            </span>
          </div>
        ))}
      </div>

      {/* Topic breakdown */}
      <div
        style={{
          background: "var(--bg-card)",
          padding: "16px",
          borderRadius: "4px",
          marginBottom: "16px",
        }}
      >
        <h3
          style={{
            fontSize: "11px",
            color: "var(--text-muted)",
            textTransform: "uppercase",
            letterSpacing: "1.5px",
            marginBottom: "12px",
            fontFamily: "'JetBrains Mono', 'Courier New', monospace",
          }}
        >
          Topics ({stats.period_days}d)
        </h3>
        {stats.topics?.map((t, i) => (
          <div
            key={i}
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              padding: "3px 0",
              fontSize: "12px",
            }}
          >
            <span
              style={{
                color: "var(--text-secondary)",
                fontFamily: "'JetBrains Mono', 'Courier New', monospace",
              }}
            >
              {t.topic_primary?.replace(/_/g, "-")}
            </span>
            <span
              style={{
                color: "var(--text-muted)",
                fontFamily: "'JetBrains Mono', 'Courier New', monospace",
              }}
            >
              {t.count}
            </span>
          </div>
        ))}
      </div>

      {/* Top entities */}
      <div
        style={{
          background: "var(--bg-card)",
          padding: "16px",
          borderRadius: "4px",
        }}
      >
        <h3
          style={{
            fontSize: "11px",
            color: "var(--text-muted)",
            textTransform: "uppercase",
            letterSpacing: "1.5px",
            marginBottom: "12px",
            fontFamily: "'JetBrains Mono', 'Courier New', monospace",
          }}
        >
          Top Entities ({stats.period_days}d)
        </h3>
        {stats.top_entities?.slice(0, 10).map((e, i) => (
          <div
            key={i}
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              padding: "3px 0",
              fontSize: "12px",
            }}
          >
            <span style={{ color: "var(--text-secondary)" }}>
              {e.entity_name_en}
            </span>
            <span
              style={{
                color: "var(--text-muted)",
                fontFamily: "'JetBrains Mono', 'Courier New', monospace",
              }}
            >
              {e.mentions}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}