const BIAS_ROWS = [
  { label: "green",             color: "#15803d", text: "#fff",     desc: "Explicitly pro-independence editorial line (e.g. Liberty Times)" },
  { label: "green_leaning",     color: "#4ade80", text: "#14532d",  desc: "State-controlled under DPP-led government (e.g. CNA, YDN)" },
  { label: "blue",              color: "#1d4ed8", text: "#fff",     desc: "Consistent KMT-aligned editorial line (e.g. UDN)" },
  { label: "centrist",          color: "#6b7280", text: "#fff",     desc: "Editorially independent (e.g. Zaobao)" },
  { label: "state_official",    color: "#dc2626", text: "#fff",     desc: "PRC state media or government organ (e.g. Xinhua, MFA, TAO)" },
  { label: "state_nationalist", color: "#b91c1c", text: "#fff",     desc: "PRC nationalist commentary (e.g. Global Times, Guancha)" },
];

export default function AboutModal({ onClose }) {
  const sectionHead = {
    fontSize: "11px",
    fontFamily: "var(--font-mono)",
    color: "var(--text-muted)",
    textTransform: "uppercase",
    letterSpacing: "2px",
    marginBottom: "10px",
    marginTop: "28px",
  };

  const body = {
    fontSize: "14px",
    fontFamily: "var(--font-body)",
    color: "var(--text-secondary)",
    lineHeight: 1.7,
    margin: 0,
  };

  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.65)",
        zIndex: 1000,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "24px 16px",
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "var(--bg-card)",
          border: "1px solid var(--border-color)",
          borderRadius: "6px",
          width: "100%",
          maxWidth: "640px",
          maxHeight: "85vh",
          overflowY: "auto",
          padding: "32px",
          position: "relative",
        }}
      >
        {/* Close button */}
        <button
          onClick={onClose}
          style={{
            position: "absolute",
            top: "16px",
            right: "16px",
            background: "none",
            border: "none",
            color: "var(--text-muted)",
            fontSize: "18px",
            cursor: "pointer",
            lineHeight: 1,
            padding: "4px 8px",
          }}
        >
          ✕
        </button>

        {/* Title */}
        <h2 style={{
          fontFamily: "var(--font-headline)",
          fontSize: "26px",
          fontWeight: 400,
          color: "var(--text-primary)",
          margin: "0 0 4px",
        }}>
          Cross-Strait Signal
        </h2>
        <p style={{
          fontFamily: "var(--font-mono)",
          fontSize: "11px",
          color: "var(--text-muted)",
          textTransform: "uppercase",
          letterSpacing: "2px",
          margin: "0 0 20px",
        }}>
          Open-Source Intelligence
        </p>

        <div style={{ height: "2px", background: "var(--text-primary)", opacity: 0.12, marginBottom: "20px" }} />

        {/* What this is */}
        <h3 style={sectionHead}>What this is</h3>
        <p style={body}>
          Cross-Strait Signal is an open-source intelligence dashboard monitoring PRC–Taiwan cross-strait
          dynamics through automated bilingual media analysis. It scrapes ~25 active sources across the
          People's Republic of China, Taiwan, and Singapore — Chinese-language outlets are treated as
          primary, since they break stories earlier and with greater analytical depth than English
          translations. Articles are processed through a multi-tier AI pipeline, human-reviewed for
          accuracy, and structured into a filterable intelligence feed.
        </p>
        <p style={{ ...body, marginTop: "12px" }}>
          The system is designed to surface destabilising signals from <em>both</em> sides of the strait —
          including Taiwanese independence moves and constitutional norm erosion alongside PRC military
          activity. This is not a "China bad, Taiwan good" instrument.
        </p>

        {/* Sentiment axis */}
        <h3 style={sectionHead}>Sentiment axis</h3>
        <p style={body}>
          Each article is scored on a −1.0 to +1.0 scale measuring how the source <em>frames the opposing
          side of the strait</em> — not geopolitical stability in the abstract.
        </p>
        <div style={{ marginTop: "12px", display: "grid", gridTemplateColumns: "auto 1fr", gap: "6px 16px", alignItems: "baseline" }}>
          {[
            { range: "−1.0 to −0.3", label: "Hostile", color: "#dc2626", desc: "Threatening, antagonistic, or confrontational framing of the other side" },
            { range: "−0.3 to +0.3", label: "Neutral",  color: "#d97706", desc: "Factual reporting without strong positive or negative framing" },
            { range: "+0.3 to +1.0", label: "Cooperative", color: "#16a34a", desc: "Warm, engaging framing — dialogue, shared identity, trade, people-to-people ties" },
          ].map(({ range, label, color, desc }) => (
            <>
              <div key={range + "l"} style={{ fontFamily: "var(--font-mono)", fontSize: "12px", color, fontWeight: 600, whiteSpace: "nowrap" }}>
                {label}
              </div>
              <div key={range + "d"} style={{ fontSize: "13px", fontFamily: "var(--font-body)", color: "var(--text-secondary)", lineHeight: 1.5 }}>
                <span style={{ color: "var(--text-muted)", marginRight: "8px", fontFamily: "var(--font-mono)", fontSize: "11px" }}>{range}</span>
                {desc}
              </div>
            </>
          ))}
        </div>
        <p style={{ ...body, marginTop: "12px", fontSize: "13px", color: "var(--text-muted)" }}>
          For PRC sources: how does the article portray Taiwan? For Taiwan sources: how does it portray
          the PRC? Taiwan–US military cooperation does not score as cross-strait cooperative.
          A PLA exercise piece and a DPP sovereignty move both score hostile on this scale.
        </p>

        {/* Source bias */}
        <h3 style={sectionHead}>Source bias labels</h3>
        <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
          {BIAS_ROWS.map(({ label, color, text, desc }) => (
            <div key={label} style={{ display: "flex", alignItems: "baseline", gap: "10px" }}>
              <span style={{
                background: color,
                color: text,
                padding: "2px 8px",
                borderRadius: "2px",
                fontSize: "10px",
                fontWeight: 600,
                fontFamily: "var(--font-mono)",
                whiteSpace: "nowrap",
                flexShrink: 0,
              }}>
                {label}
              </span>
              <span style={{ fontSize: "13px", fontFamily: "var(--font-body)", color: "var(--text-secondary)", lineHeight: 1.5 }}>
                {desc}
              </span>
            </div>
          ))}
        </div>

        {/* AI pipeline */}
        <h3 style={sectionHead}>AI pipeline & human oversight</h3>
        <p style={body}>
          Articles pass through a three-tier pipeline: Gemini 2.5 Flash Lite handles initial
          classification (topic, sentiment, urgency, named entities, key quotes); Gemini 2.5 Flash
          re-reviews escalation-flagged articles; a human review queue catches cases where the two
          models disagree. Every article requires explicit analyst approval before appearing on this
          feed — AI output is a starting point, not the final word. Translations and classifications
          can be corrected inline by the analyst, and corrected fields are marked as human-verified.
        </p>

        {/* Author */}
        <h3 style={sectionHead}>Author</h3>
        <p style={body}>
          Ed Moon — bilingual English–Mandarin analyst, former Supervising Editor and News Director at
          TaiwanPlus, MA Taiwan Studies (SOAS University of London).{" "}
          <a
            href="https://substack.com/@edmooon"
            target="_blank"
            rel="noopener noreferrer"
            style={{ color: "var(--accent-teal)", textDecoration: "none" }}
          >
            The East and Back ↗
          </a>
        </p>

        <div style={{ height: "2px", background: "var(--text-primary)", opacity: 0.08, margin: "28px 0 20px" }} />

        <p style={{ fontSize: "12px", fontFamily: "var(--font-mono)", color: "var(--text-muted)", margin: 0 }}>
          Source code:{" "}
          <a
            href="https://github.com/Parkemoon/cross-strait-signal"
            target="_blank"
            rel="noopener noreferrer"
            style={{ color: "var(--accent-teal)", textDecoration: "none" }}
          >
            github.com/Parkemoon/cross-strait-signal
          </a>
          {" "}· GPL-3.0
        </p>
      </div>
    </div>
  );
}
