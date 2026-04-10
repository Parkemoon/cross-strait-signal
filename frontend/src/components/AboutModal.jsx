const BIAS_ROWS = [
  { label: "green",             color: "#15803d", text: "#fff",     desc: "Explicitly pro-independence editorial line (e.g. Liberty Times)" },
  { label: "green_leaning",     color: "#4ade80", text: "#14532d",  desc: "State-controlled under DPP-led government (e.g. CNA, YDN)" },
  { label: "blue",              color: "#1d4ed8", text: "#fff",     desc: "Consistent KMT-aligned editorial line (e.g. UDN)" },
  { label: "centrist",          color: "#6b7280", text: "#fff",     desc: "Editorially independent, either local or international (e.g. Zaobao)" },
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
          dynamics through automated bilingual media analysis. It scrapes dozens of active sources across
          the People's Republic of China, Taiwan, Hong Kong, and international Chinese-language outlets — Chinese-language outlets are treated as
          primary, since they break stories earlier and with greater analytical depth than English media on
          either side of the strait, while mainstream international media does great work and often has
          exclusives, access to that information is easy for English speakers, while access to what the
          people who are most impacted think is often lost. Articles are processed through a multi-tier AI
          pipeline, human-reviewed for accuracy, and structured into a filterable intelligence feed.
        </p>
        <p style={{ ...body, marginTop: "12px" }}>
          There is also a social feed covering for the moment the top 50 trending on Weibo and the
          Taiwanese Reddit-style board PTT. Neither of these can be read as giving a representative view
          of a broad swath of cross-strait public opinion, but at the moment it is very hard to access
          data for the social media of choice on either side (WeChat and Douyin for the PRC; Threads,
          Instagram and Facebook for Taiwan).
        </p>
        <p style={{ ...body, marginTop: "12px" }}>
          The system is designed to surface signals from both sides of the strait — including changes to
          Taiwanese "status quo" alongside PRC military activity and nationalist rhetoric. It is
          deliberately not supposed to imply one side's positive or negative activity is a one-way street.
        </p>

        {/* Sentiment axis */}
        <h3 style={sectionHead}>Sentiment axis</h3>
        <p style={body}>
          Each article is scored on a −1.0 to +1.0 scale measuring how the source frames the opposing
          side of the strait.
        </p>
        <div style={{ marginTop: "12px", display: "grid", gridTemplateColumns: "auto 1fr", gap: "6px 16px", alignItems: "baseline" }}>
          {[
            { range: "−1.0 to −0.3", label: "Hostile",      color: "#7c3aed", desc: "Threatening, antagonistic, or confrontational framing of the other side" },
            { range: "−0.3 to +0.3", label: "Neutral",      color: "#6b7280", desc: "Factual reporting without strong positive or negative framing" },
            { range: "+0.3 to +1.0", label: "Cooperative",  color: "#f59e0b", desc: "Warm, engaging framing — dialogue, shared identity, trade, people-to-people ties" },
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
          the PRC?
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
          feed. Translations and classifications can be corrected inline by the analyst, and corrected
          fields are marked as human-verified.
        </p>

        {/* Key Terms */}
        <h3 style={sectionHead}>Key Terms</h3>
        <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
          {[
            { term: "PRC", def: "People's Republic of China — the government in Beijing, which has governed mainland China since 1949." },
            { term: "ROC", def: "Republic of China — the government in Taipei. The ROC was founded in 1912, lost the civil war to the CCP in 1949, and retreated to Taiwan. It continues to govern Taiwan, Kinmen, and Matsu." },
            { term: "Green / Blue", def: "Taiwan's two political camps. Green refers to the DPP and its allies, who broadly favour preserving or advancing Taiwan's separate identity. Blue refers to the KMT and its allies, who favour closer cross-strait engagement. Neither camp formally advocates immediate independence or unification." },
            { term: "DPP", def: "Democratic Progressive Party (民主進步黨) — Taiwan's centre-left ruling party, associated with the green camp. Founded in 1986 during Taiwan's democratisation." },
            { term: "KMT", def: "Kuomintang (中國國民黨), or Chinese Nationalist Party — Taiwan's main opposition, associated with the blue camp. Governed Taiwan from 1949 until losing power to the DPP in 2000." },
            { term: "TPP", def: "Taiwan People's Party (台灣民眾黨) — Taiwan's third-largest party, founded in 2019 by former Taipei mayor Ko Wen-je. Positions itself between green and blue on cross-strait issues." },
            { term: "統獨 (Tǒng-Dú)", def: "The unification–independence spectrum. 統 (tǒng) refers to unification with the mainland; 獨 (dú) refers to formal independence. Most Taiwanese public opinion sits in the middle, favouring maintaining the status quo." },
            { term: "TAO", def: "Taiwan Affairs Office (國台辦) — the PRC government body responsible for Taiwan policy. Its statements are closely watched as signals of Beijing's current posture." },
            { term: "MAC", def: "Mainland Affairs Council (陸委會) — Taiwan's counterpart to the TAO, overseeing cross-strait policy from Taipei." },
            { term: "ADIZ", def: "Air Defence Identification Zone — airspace where a country requires aircraft to identify themselves. PLA incursions into Taiwan's ADIZ are a routine but significant signal of military pressure." },
            { term: "Weibo (微博)", def: "The dominant microblogging platform in the PRC — roughly analogous to X/Twitter. The hot search list reflects what is trending, though it is subject to censorship and algorithmic shaping." },
            { term: "PTT", def: "A long-running Taiwanese BBS (bulletin board) forum, particularly influential among younger and politically engaged Taiwanese. The Military, Gossiping, and HatePolitics boards are monitored here." },
          ].map(({ term, def }) => (
            <div key={term} style={{ display: "grid", gridTemplateColumns: "140px 1fr", gap: "8px", alignItems: "baseline" }}>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: "12px", fontWeight: 600, color: "var(--text-primary)", paddingTop: "1px" }}>
                {term}
              </span>
              <span style={{ fontSize: "13px", fontFamily: "var(--font-body)", color: "var(--text-secondary)", lineHeight: 1.6 }}>
                {def}
              </span>
            </div>
          ))}
        </div>

        {/* Author */}
        <h3 style={sectionHead}>Author</h3>
        <p style={body}>
          Ed Moon — bilingual English–Mandarin analyst, former Supervising Editor at TaiwanPlus.{" "}
          <a
            href="https://theeastandback.substack.com"
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
