export default function FlashTraffic({ escalations }) {
  if (!escalations || escalations.length === 0) return null;

  return (
    <div style={{ marginBottom: "32px" }}>
      <h2
        style={{
          color: "var(--accent-red)",
          fontSize: "14px",
          fontWeight: 700,
          textTransform: "uppercase",
          letterSpacing: "1.5px",
          marginBottom: "16px",
          fontFamily: "'JetBrains Mono', 'Courier New', monospace",
        }}
      >
        ⚡ Flash Traffic
      </h2>
      {escalations.map((item) => (
        <div
          key={item.id}
          style={{
            background: "var(--escalation-bg)",
            borderLeft: "3px solid var(--escalation-border)",
            padding: "16px 20px",
            marginBottom: "12px",
            borderRadius: "4px",
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "10px",
              marginBottom: "8px",
            }}
          >
            <span
              style={{
                background: "var(--accent-red)",
                color: "#fff",
                padding: "2px 8px",
                borderRadius: "3px",
                fontSize: "11px",
                fontWeight: 700,
                fontFamily: "'JetBrains Mono', 'Courier New', monospace",
              }}
            >
              ESCALATION
            </span>
            <span
              style={{
                color: "var(--text-muted)",
                fontSize: "12px",
                fontFamily: "'JetBrains Mono', 'Courier New', monospace",
              }}
            >
              {item.source_name} · {item.published_at?.slice(0, 10)}
            </span>
          </div>
          <h3
            style={{
              fontSize: "15px",
              fontWeight: 600,
              marginBottom: "6px",
              color: "var(--text-primary)",
            }}
          >
            {item.title_en || item.title_original}
          </h3>
          <p
            style={{
              fontSize: "13px",
              color: "var(--text-secondary)",
              lineHeight: 1.6,
              marginBottom: "8px",
            }}
          >
            {item.summary_en}
          </p>
          {item.escalation_note && (
            <p
              style={{
                fontSize: "12px",
                color: "var(--accent-amber)",
                fontStyle: "italic",
              }}
            >
              ⚠ {item.escalation_note}
            </p>
          )}
        </div>
      ))}
    </div>
  );
}