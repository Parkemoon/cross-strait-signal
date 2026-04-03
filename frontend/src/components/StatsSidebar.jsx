export default function StatsSidebar({ stats }) {
  if (!stats) return null;

  const sectionTitle = (text) => ({
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
      {/* Strait Watch — sentiment gauge */}
      <div style={{ marginBottom: "28px" }}>
        <h3 style={sectionTitle()}>Strait Watch</h3>
        <div
          style={{
            background: "var(--bg-card)",
            border: "1px solid var(--border-color)",
            borderRadius: "3px",
            padding: "16px",
          }}
        >
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              marginBottom: "10px",
              fontSize: "10px",
              fontFamily: "var(--font-mono)",
              color: "var(--text-muted)",
            }}
          >
            <span>Conciliatory</span>
            <span>Escalatory</span>
          </div>
          <div
            style={{
              height: "6px",
              background: "var(--bg-secondary)",
              borderRadius: "3px",
              position: "relative",
            }}
          >
            {/* Track gradient */}
            <div
              style={{
                position: "absolute",
                inset: 0,
                borderRadius: "3px",
                background: "linear-gradient(to right, var(--accent-green), var(--accent-amber), var(--accent-red))",
                opacity: 0.25,
              }}
            />
            {/* Indicator */}
            <div
              style={{
                position: "absolute",
                left: `${((stats.avg_sentiment_score + 1) / 2) * 100}%`,
                top: "50%",
                width: "14px",
                height: "14px",
                borderRadius: "50%",
                background:
                  stats.avg_sentiment_score > 0.3
                    ? "var(--accent-red)"
                    : stats.avg_sentiment_score < -0.3
                    ? "var(--accent-green)"
                    : "var(--accent-amber)",
                transform: "translate(-50%, -50%)",
                border: "2px solid var(--bg-card)",
                boxShadow: "0 1px 3px rgba(0,0,0,0.15)",
                transition: "left 0.5s ease",
              }}
            />
          </div>
          <div
            style={{
              textAlign: "center",
              marginTop: "10px",
              fontSize: "20px",
              fontFamily: "var(--font-mono)",
              fontWeight: 600,
              color:
                stats.avg_sentiment_score > 0.3
                  ? "var(--accent-red)"
                  : stats.avg_sentiment_score < -0.3
                  ? "var(--accent-green)"
                  : "var(--accent-amber)",
            }}
          >
            {stats.avg_sentiment_score > 0 ? "+" : ""}
            {stats.avg_sentiment_score?.toFixed(2)}
          </div>
          <p
            style={{
              textAlign: "center",
              fontSize: "11px",
              fontFamily: "var(--font-body)",
              color: "var(--text-muted)",
              marginTop: "2px",
            }}
          >
            {stats.period_days}-day weighted average
          </p>
        </div>
      </div>

      {/* Source Health */}
      <div style={{ marginBottom: "28px" }}>
        <h3 style={sectionTitle()}>Sources</h3>
        <div
          style={{
            background: "var(--bg-card)",
            border: "1px solid var(--border-color)",
            borderRadius: "3px",
            padding: "12px 16px",
          }}
        >
          {stats.sources?.map((s, i) => (
            <div
              key={i}
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                padding: "5px 0",
                borderBottom:
                  i < stats.sources.length - 1
                    ? "1px solid var(--border-color)"
                    : "none",
              }}
            >
              <span
                style={{
                  fontSize: "13px",
                  fontFamily: "var(--font-body)",
                  color: "var(--text-secondary)",
                  display: "flex",
                  alignItems: "center",
                  gap: "6px",
                }}
              >
                <span
                  style={{
                    width: "8px",
                    height: "8px",
                    borderRadius: "50%",
                    background:
                      s.country === "PRC"
                        ? "var(--accent-red)"
                        : "var(--accent-blue)",
                    display: "inline-block",
                  }}
                />
                {s.name}
              </span>
              <span
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "12px",
                  color: "var(--text-muted)",
                }}
              >
                {s.count}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Topic Breakdown */}
      <div style={{ marginBottom: "28px" }}>
        <h3 style={sectionTitle()}>Topics</h3>
        <div
          style={{
            background: "var(--bg-card)",
            border: "1px solid var(--border-color)",
            borderRadius: "3px",
            padding: "12px 16px",
          }}
        >
          {stats.topics?.map((t, i) => {
            const maxCount = stats.topics[0]?.count || 1;
            return (
              <div key={i} style={{ marginBottom: "8px" }}>
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    marginBottom: "3px",
                    fontSize: "12px",
                  }}
                >
                  <span
                    style={{
                      fontFamily: "var(--font-mono)",
                      color: "var(--text-secondary)",
                    }}
                  >
                    {t.topic_primary?.replace(/_/g, " ")}
                  </span>
                  <span
                    style={{
                      fontFamily: "var(--font-mono)",
                      color: "var(--text-muted)",
                    }}
                  >
                    {t.count}
                  </span>
                </div>
                <div
                  style={{
                    height: "3px",
                    background: "var(--bg-secondary)",
                    borderRadius: "2px",
                    overflow: "hidden",
                  }}
                >
                  <div
                    style={{
                      height: "100%",
                      width: `${(t.count / maxCount) * 100}%`,
                      background: "var(--accent-teal)",
                      borderRadius: "2px",
                      transition: "width 0.5s ease",
                    }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Key Entities */}
      <div>
        <h3 style={sectionTitle()}>Key Entities</h3>
        <div
          style={{
            background: "var(--bg-card)",
            border: "1px solid var(--border-color)",
            borderRadius: "3px",
            padding: "12px 16px",
          }}
        >
          {stats.top_entities?.slice(0, 10).map((e, i) => (
            <div
              key={i}
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                padding: "4px 0",
                borderBottom:
                  i < Math.min(stats.top_entities.length, 10) - 1
                    ? "1px solid var(--border-color)"
                    : "none",
              }}
            >
              <span
                style={{
                  fontSize: "13px",
                  fontFamily: "var(--font-body)",
                  color: "var(--text-secondary)",
                }}
              >
                {e.entity_name_en}
                <span
                  style={{
                    fontSize: "10px",
                    color: "var(--text-muted)",
                    fontFamily: "var(--font-mono)",
                    marginLeft: "6px",
                  }}
                >
                  {e.entity_type}
                </span>
              </span>
              <span
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "12px",
                  color: "var(--text-muted)",
                }}
              >
                {e.mentions}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
