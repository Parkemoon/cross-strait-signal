import { Copy } from "../copy";
import { BIAS_META } from "./SourceBadge";

// About — a full page since the Morning Brief redesign (was AboutModal).
// Single reading column, max-840: the design's "document" treatment. All
// prose renders through the same site_copy keys the modal used, so analyst
// edits and tests/test_site_copy.py carry over unchanged.

const BIAS_ROWS = [
  { label: "green",             desc: "Explicitly pro-independence editorial line (e.g. Liberty Times)" },
  { label: "green_leaning",     desc: "State-controlled under DPP-led government (e.g. CNA, YDN)" },
  { label: "blue",              desc: "Consistent KMT-aligned editorial line (e.g. UDN)" },
  { label: "blue_leaning",      desc: "Blue-leaning commercial outlet (e.g. ETtoday)" },
  { label: "centrist",          desc: "Editorially independent, either local or international (e.g. Zaobao)" },
  { label: "china_centrist",    desc: "Editorially moderate but Beijing-accommodating (e.g. Ming Pao)" },
  { label: "state_official",    desc: "PRC state media or government organ (e.g. Xinhua, MFA, TAO); also applied to RTHK post-NSL" },
  { label: "state_nationalist", desc: "PRC nationalist commentary (e.g. Global Times, Guancha)" },
];

const TABS = [
  { name: "Military",     desc: "Daily PLA activity around Taiwan from MND briefings (2020–present), plus a reviewed tracker of named exercises on a live map." },
  { name: "Maritime",     desc: "Coast-guard presence in Taiwan-drawn waters (China and Taiwan hulls seen on AIS via Global Fishing Watch, 2017–present) paired with Taiwan's own enforcement statistics. Law-enforcement vessels, not warships — kept beside Military, not inside it. AIS is a floor, and every chart carries its caveat." },
  { name: "Indicators",   desc: "Cross-strait trade, investment, and macro indicators, with a verification angle: the same flows as reported by Taipei, by Beijing, and by Hong Kong, side by side. Where the reporters diverge, that divergence is the signal." },
  { name: "Trade access", desc: "The asymmetric regulatory picture: Taiwan's import bans on PRC goods against the PRC's ECFA suspensions and food-registration blocks." },
  { name: "People",       desc: "Visitor flows, residence and settlement permits, and the mainland-spouse population, in both directions." },
  { name: "Polls",        desc: "Taiwanese public opinion across pollsters on one set of canonical questions, anchored by NCCU's identity and unification series (1992–present)." },
  { name: "Diplomacy",    desc: "A world map of third-country stances on the Taiwan question, split between official government positions and non-official voices such as legislators." },
  { name: "Visits",       desc: "Publicly reported official and party-level visits, meetings and exchanges across the strait, in both directions — including blocked and cancelled trips, because a denied permit is signal too." },
];

const KEY_TERMS = [
  { term: "PRC", def: "People's Republic of China — the government in Beijing, which has governed mainland China since 1949." },
  { term: "ROC", def: "Republic of China — the government in Taipei. The ROC was founded in 1912, lost the civil war to the CCP in 1949, and retreated to Taiwan. It continues to govern Taiwan, Kinmen, and Matsu." },
  { term: "Green / Blue", def: "Taiwan's two political camps. Green refers to the DPP (民主進步黨) and its allies, who broadly favour preserving or advancing Taiwan's separate identity; Blue to the KMT (中國國民黨) and its allies, who favour closer cross-strait engagement. The smaller TPP (台灣民眾黨) positions itself between the two." },
  { term: "TAO", def: "Taiwan Affairs Office (國台辦) — the PRC government body responsible for Taiwan policy. Its statements are closely watched as signals of Beijing's current posture." },
  { term: "MAC", def: "Mainland Affairs Council (陸委會) — Taiwan's counterpart to the TAO, overseeing cross-strait policy from Taipei." },
  { term: "ADIZ", def: "Air Defence Identification Zone — airspace where a country requires aircraft to identify themselves. PLA incursions into Taiwan's ADIZ are a routine but significant signal of military pressure." },
  { term: "Weibo (微博)", def: "The dominant microblogging platform in the PRC — roughly analogous to X/Twitter. The hot search list reflects what is trending, though it is subject to censorship and algorithmic shaping." },
  { term: "PTT", def: "A long-running Taiwanese BBS (bulletin board) forum, particularly influential among younger and politically engaged Taiwanese. The Military, Gossiping, and HatePolitics boards are monitored here." },
];

function SectionRule({ children }) {
  return (
    <div style={{ display: "flex", alignItems: "baseline", gap: "10px", margin: "32px 0 12px" }}>
      <span style={{
        fontFamily: "var(--font-mono)", fontSize: "9.5px", fontWeight: 600,
        letterSpacing: "0.24em", textTransform: "uppercase", color: "var(--ink)",
        whiteSpace: "nowrap",
      }}>{children}</span>
      <span style={{ flex: 1, borderBottom: "1px solid var(--hair)" }} />
    </div>
  );
}

const BODY = {
  fontSize: "14px",
  fontFamily: "var(--font-body)",
  color: "var(--body)",
  lineHeight: 1.75,
  margin: 0,
  textWrap: "pretty",
};

export default function AboutTab() {
  return (
    <main style={{ maxWidth: "840px", margin: "0 auto", padding: "30px 48px 56px", minWidth: 0 }}>
      {/* Page header */}
      <div style={{ borderBottom: "1px solid var(--hair)", paddingBottom: "16px", marginBottom: "24px" }}>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: "9px", letterSpacing: "0.24em",
                      color: "var(--faint)", marginBottom: "7px", textTransform: "uppercase" }}>
          About / Method
        </div>
        <h2 style={{ fontFamily: "var(--font-headline)", fontSize: "34px", fontWeight: 500,
                     lineHeight: 1.1, color: "var(--ink)", margin: "0 0 10px" }}>
          About Cross-Strait Signal
        </h2>
        <Copy k="about.what"
              as="p"
              style={{ ...BODY, fontSize: "14px", color: "var(--muted)", maxWidth: "620px" }}
              fallback={"Cross-Strait Signal is an open-source intelligence dashboard monitoring PRC–Taiwan cross-strait dynamics through automated bilingual media analysis. It scrapes 37 active sources across the People's Republic of China, Taiwan, Hong Kong, and international Chinese-language outlets. Chinese-language sources are treated as primary: they break stories earlier and in greater depth than English-language media on either side of the strait. International outlets do strong work and often land exclusives, but that reporting is already easy for English speakers to reach — what gets lost is what the people most affected are reading and saying. Articles are processed through a multi-tier AI pipeline, human-reviewed for accuracy, and structured into a filterable intelligence feed."} />
      </div>

      <Copy k="about.social"
            as="p"
            style={BODY}
            fallback={"There is also a social feed covering for the moment the top 50 trending on Weibo and the Taiwanese Reddit-style board PTT. Neither of these can be read as giving a representative view of a broad swath of cross-strait public opinion, but at the moment it is very hard to access data for the social media of choice on either side (WeChat and Douyin for the PRC; Threads, Instagram and Facebook for Taiwan)."} />
      <Copy k="about.bidirectional"
            as="p"
            style={{ ...BODY, marginTop: "12px" }}
            fallback={"The system is designed to surface signals from both sides of the strait — including changes to Taiwanese \"status quo\" alongside PRC military activity and nationalist rhetoric. It is deliberately not supposed to imply one side's positive or negative activity is a one-way street."} />

      <SectionRule>Beyond the feed</SectionRule>
      <Copy k="about.beyond_intro"
            as="p"
            style={BODY}
            fallback={"The article feed is one instrument among several. The dashboard also tracks:"} />
      <div style={{ marginTop: "14px", display: "flex", flexDirection: "column", gap: "0" }}>
        {TABS.map(({ name, desc }, i) => (
          <div key={name} style={{ display: "grid", gridTemplateColumns: "110px 1fr", gap: "14px",
                                   alignItems: "baseline", padding: "9px 0",
                                   borderBottom: i < TABS.length - 1 ? "1px solid var(--soft)" : "none" }}>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: "9.5px", fontWeight: 600,
                           letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--ink)" }}>
              {name}
            </span>
            <span style={{ fontSize: "13px", fontFamily: "var(--font-body)", color: "var(--body)", lineHeight: 1.6, textWrap: "pretty" }}>
              {desc}
            </span>
          </div>
        ))}
      </div>

      <SectionRule>Sentiment axis</SectionRule>
      <Copy k="about.sentiment_axis"
            as="p"
            style={BODY}
            fallback={"Each article is scored on a −1.0 to +1.0 scale measuring how the source frames the opposing side of the strait."} />
      {/* Banded axis bar — hostile purple · neutral · cooperative amber */}
      <div style={{ border: "1px solid var(--hair)", padding: "18px 20px", margin: "14px 0" }}>
        <div style={{ height: "5px", display: "flex", marginBottom: "12px" }}>
          <div style={{ flex: 1, background: "var(--hostile)" }} />
          <div style={{ flex: 1, background: "var(--dot)" }} />
          <div style={{ flex: 1, background: "var(--coop)" }} />
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
                      gap: "20px", fontSize: "12px", color: "var(--body)", lineHeight: 1.55 }}>
          {[
            { range: "−1.0 to −0.3 hostile", color: "var(--hostile)", desc: "Threatening, antagonistic, or confrontational framing of the other side" },
            { range: "−0.3 to +0.3 neutral", color: "var(--faint)", desc: "Factual reporting without strong positive or negative framing" },
            { range: "+0.3 to +1.0 cooperative", color: "var(--coop)", desc: "Warm, engaging framing — dialogue, shared identity, trade, people-to-people ties" },
          ].map(({ range, color, desc }) => (
            <div key={range}>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: "8.5px", letterSpacing: "0.12em",
                            color, marginBottom: "4px", textTransform: "uppercase" }}>{range}</div>
              {desc}
            </div>
          ))}
        </div>
      </div>
      <Copy k="about.sentiment_axis_detail"
            as="p"
            style={{ ...BODY, fontSize: "13px", color: "var(--muted)" }}
            fallback={"For PRC sources: how does the article portray Taiwan? For Taiwan sources: how does it portray the PRC? Third-country statements about Taiwan are deliberately excluded from this axis — they feed the Diplomacy map instead."} />

      <SectionRule>Diplomacy stance axis</SectionRule>
      <Copy k="about.diplomacy_axis"
            as="p"
            style={BODY}
            fallback={"The Diplomacy map uses a separate scale, scored −1.0 to +1.0: how far a third country's statement leans toward Beijing's position or Taipei's. It deliberately uses different colours — red toward Beijing, green toward Taipei, following each side's own political conventions — so it cannot be misread as the purple/amber sentiment axis. Country fill reflects the average of official-tier statements (governments and heads of state); pins mark the aggregate of non-official voices, which often diverge from the government line."} />

      <SectionRule>Source alignment labels</SectionRule>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: "8px 26px" }}>
        {BIAS_ROWS.map(({ label, desc }) => {
          const meta = BIAS_META[label] || {};
          return (
            <div key={label} style={{ display: "flex", gap: "10px", alignItems: "flex-start",
                                      fontSize: "12.5px", color: "var(--body)", lineHeight: 1.5 }}>
              <span style={{
                width: "9px", height: "9px", flexShrink: 0, marginTop: "4px",
                background: meta.marker === "●" ? "transparent" : meta.colour,
                border: meta.marker === "●" ? `2px solid ${meta.colour}` : "none",
                borderRadius: meta.marker === "●" ? "50%" : 0,
              }} />
              <span style={{ textWrap: "pretty" }}>
                <span style={{ fontWeight: 600, color: meta.colour, fontFamily: "var(--font-mono)",
                               fontSize: "10px", letterSpacing: "0.08em", textTransform: "uppercase" }}>
                  {label.replace(/_/g, " ")}
                </span>
                {" — "}{desc}
              </span>
            </div>
          );
        })}
      </div>

      <SectionRule>AI pipeline &amp; human oversight</SectionRule>
      <Copy k="about.pipeline"
            as="p"
            style={BODY}
            fallback={"Articles pass through a three-tier pipeline: Gemini 3.1 Flash Lite handles initial classification (topic, sentiment, urgency, named entities, key quotes); Gemini 3.5 Flash independently re-reviews escalation-flagged articles without seeing the first tier's answers; a human review queue catches cases where the two disagree. Every article requires explicit analyst approval before appearing on this feed, and the same editorial gate applies to every derived record — military exercises, poll extractions, diplomacy statements, and quotes attributed to key figures all sit in analyst review queues until approved. Translations and classifications can be corrected inline, and corrected fields are marked as human-verified."} />

      <SectionRule>Key terms</SectionRule>
      <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
        {KEY_TERMS.map(({ term, def }) => (
          <div key={term} style={{ display: "grid", gridTemplateColumns: "130px 1fr", gap: "14px", alignItems: "baseline" }}>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", fontWeight: 600,
                           letterSpacing: "0.08em", color: "var(--ink)", textTransform: "uppercase" }}>
              {term}
            </span>
            <span style={{ fontSize: "13px", fontFamily: "var(--font-body)", color: "var(--body)", lineHeight: 1.6, textWrap: "pretty" }}>
              {def}
            </span>
          </div>
        ))}
      </div>

      <SectionRule>Data sources</SectionRule>
      <Copy k="about.sources"
            as="p"
            style={BODY}
            fallback={"News analysis is built on the 37-source roster. Structured data comes from: Taiwan's Mainland Affairs Council open datasets (trade, investment, visitor flows, polling); UN Comtrade (PRC-reported trade, discontinued by Beijing after Dec 2024); Hong Kong Census & Statistics Department; Taiwan MND daily briefings, with 2020–2026 history backfilled from PLATracker; Taiwan NIA residence statistics; Global Fishing Watch's AIS presence data and Taiwan CGA statistical reports for the coast-guard tracker; BOFT and ECFA notifications plus the PRC's CIFER registry; NCCU Election Study Center long-series polling alongside TVBS, My-Formosa, ETtoday and MAC surveys; Natural Earth map data."} />

      {/* Footer — attribution */}
      <div style={{ borderTop: "1px solid var(--hair)", marginTop: "32px", paddingTop: "18px",
                    display: "flex", justifyContent: "space-between", gap: "24px", flexWrap: "wrap",
                    fontSize: "12.5px", fontFamily: "var(--font-body)", color: "var(--muted)", lineHeight: 1.6 }}>
        <div>
          Built and maintained by <span style={{ color: "var(--ink)", fontWeight: 600 }}>Ed Moon</span> —
          bilingual English–Mandarin analyst, former Supervising Editor at TaiwanPlus.{" "}
          <a href="https://theeastandback.substack.com" target="_blank" rel="noopener noreferrer"
             style={{ color: "var(--muted)", textDecoration: "none", borderBottom: "1px solid var(--dot)" }}>
            The East and Back ↗
          </a>
        </div>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: "9px", letterSpacing: "0.1em",
                      color: "var(--pale)", textAlign: "right", flexShrink: 0, lineHeight: 1.9 }}>
          <a href="https://github.com/Parkemoon/cross-strait-signal" target="_blank" rel="noopener noreferrer"
             style={{ color: "var(--pale)", textDecoration: "none", borderBottom: "1px solid var(--dot)" }}>
            GITHUB.COM/PARKEMOON/CROSS-STRAIT-SIGNAL
          </a>
          <br />GPL-3.0
        </div>
      </div>
    </main>
  );
}
