export default function FlashTraffic({ escalations }) {
  if (!escalations || escalations.length === 0) return null;

  return (
    <div style={{ marginBottom: "32px" }}>
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          gap: "10px",
          marginBottom: "14px",
        }}
      >
        <h2
          style={{
            fontFamily: "var(--font-headline)",
            fontSize: "20px",
            fontWeight: 400,
            color: "var(--accent-red)",
          }}
        >
          Priority Signals
        </h2>
        <span
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "11px",
            color: "var(--text-muted)",
          }}
        >
          {escalations.length} active
        </span>
      </div>

      {escalations.map((item) => (
        <div
          key={item.id}
          style={{
            background: "var(--escalation-bg)",
            borderLeft: "4px solid var(--escalation-border)",
            padding: "18px 22px",
            marginBottom: "12px",
            borderRadius: "2px",
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "10px",
              marginBottom: "10px",
            }}
          >
            <span
              style={{
                background: "var(--accent-red)",
                color: "#fff",
                padding: "2px 10px",
                borderRadius: "2px",
                fontSize: "10px",
                fontWeight: 600,
                fontFamily: "var(--font-mono)",
                letterSpacing: "1px",
                textTransform: "uppercase",
              }}
            >
              Signal
            </span>
            <span
              style={{
                color: "var(--text-muted)",
                fontSize: "12px",
                fontFamily: "var(--font-mono)",
              }}
            >
              {item.source_name} · {item.published_at?.slice(0, 10)}
            </span>
          </div>

          <h3
            style={{
              fontFamily: "var(--font-headline)",
              fontSize: "17px",
              fontWeight: 400,
              marginBottom: "8px",
              color: "var(--text-primary)",
              lineHeight: 1.4,
            }}
          >
            {item.title_en || item.title_original}
          </h3>

          <p
            style={{
              fontSize: "14px",
              fontFamily: "var(--font-body)",
              color: "var(--text-secondary)",
              lineHeight: 1.65,
              marginBottom: "8px",
            }}
          >
            {item.summary_en}
          </p>

          {item.escalation_note && (
            <p
              style={{
                fontSize: "13px",
                fontFamily: "var(--font-body)",
                color: "var(--accent-amber)",
                fontStyle: "italic",
                lineHeight: 1.5,
              }}
            >
              ▸ {item.escalation_note}
            </p>
          )}
        </div>
      ))}

      {/* Divider after priority signals */}
      <div
        style={{
          height: "1px",
          background: "var(--border-color)",
          marginTop: "8px",
          marginBottom: "8px",
        }}
      />
    </div>
  );
}
