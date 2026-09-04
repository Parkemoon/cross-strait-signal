import { useState, useEffect } from "react";
import { fetchReviewQueue, resolveReview, updateArticleTranslation } from "../api";
import { bandColour } from "../sentimentBand";
import SourceBadge from "./SourceBadge";
import { DocumentHeader, STANDFIRST } from "./documentChrome";
import { Btn, FIELD, LABEL, MICRO, META_LINE, Quiet } from "./adminChrome";

// Admin › Review — the human review queue (Tier 3). Morning Brief phase 2B
// restyle of the design's §10 card: metadata line + ⚑ flag, Newsreader
// headline, Chinese original, a 2-up band bounded by --soft rules showing
// MODEL READ (the score, Newsreader 24px in --flag) beside the DESK
// controls, then the model's reasoning, then the translation fields, then
// ONE primary action. Behaviour is unchanged: translation edits are saved
// before any resolution; confirm / override auto-approve the article.

const SENTIMENT_OPTIONS = ["hostile", "cooperative", "neutral", "mixed"];
const TOPIC_OPTIONS = [
  "MIL_EXERCISE", "MIL_MOVEMENT", "MIL_HARDWARE", "MIL_POLICY",
  "DIP_STATEMENT", "DIP_VISIT", "DIP_SANCTIONS", "PARTY_VISIT",
  "ECON_TRADE", "ECON_INVEST", "ENERGY", "SCI_TECH", "POL_DOMESTIC_TW", "POL_DOMESTIC_PRC", "POL_TONGDU",
  "INFO_WARFARE", "CYBER", "LEGAL_GREY", "HUMANITARIAN", "TRANSPORT", "INT_ORG",
  "CULTURE", "SPORT", "ARMS_SALES", "US_PRC", "US_TAIWAN", "HK_MAC",
];

const SELECT = { ...FIELD, fontFamily: "var(--font-mono)", fontSize: "11px", letterSpacing: "0.04em", padding: "5px 6px" };

function fmtScore(v) {
  if (v == null) return "—";
  return `${v > 0 ? "+" : ""}${Number(v).toFixed(2)}`;
}

function fmtTime(ts) {
  if (!ts) return "—";
  return new Date(ts).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }).toUpperCase();
}

function Field({ label, children }) {
  return (
    <div style={{ minWidth: 0 }}>
      <label style={LABEL}>{label}</label>
      {children}
    </div>
  );
}

function ReviewCard({ item, onResolved }) {
  const modelDesk = {
    sentiment_override: item.sentiment,
    topic_override: item.topic_primary,
    escalation_override: !!item.is_escalation_signal,
  };
  const [desk, setDesk] = useState({ ...modelDesk, note: "" });
  const [translations, setTranslations] = useState({
    title_en_override: item.title_en_override || item.title_en || "",
    summary_en_override: item.summary_en_override || item.summary_en || "",
    key_quote_override: item.key_quote_override || item.key_quote_en || item.key_quote || "",
  });
  const [submitting, setSubmitting] = useState(false);

  const deskDiffers =
    desk.sentiment_override !== modelDesk.sentiment_override ||
    desk.topic_override !== modelDesk.topic_override ||
    desk.escalation_override !== modelDesk.escalation_override;

  // Save any changed translation fields, then resolve.
  async function handleResolve(resolution) {
    setSubmitting(true);
    try {
      const translationUpdates = {};
      if (translations.title_en_override !== (item.title_en || ""))
        translationUpdates.title_en_override = translations.title_en_override;
      if (translations.summary_en_override !== (item.summary_en || ""))
        translationUpdates.summary_en_override = translations.summary_en_override;
      if (translations.key_quote_override !== (item.key_quote_en || item.key_quote || ""))
        translationUpdates.key_quote_override = translations.key_quote_override;
      if (Object.keys(translationUpdates).length > 0) {
        await updateArticleTranslation(item.article_id, translationUpdates);
      }
      await resolveReview(item.analysis_id, {
        resolution,
        ...(resolution === "overridden" ? desk : { note: desk.note }),
      });
      onResolved(item.analysis_id);
    } catch (err) {
      // Re-enable the buttons and surface the failure instead of leaving the
      // card permanently stuck in the disabled "submitting" state.
      console.error("Failed to resolve review:", err);
      alert(`Could not save this review: ${err.message || err}`);
      setSubmitting(false);
    }
  }

  const scoreColour = bandColour(item.sentiment_score);

  return (
    <article style={{
      border: "1px solid var(--hair)",
      borderLeft: "3px solid var(--flag)",
      padding: "20px 22px",
      marginBottom: "18px",
      opacity: submitting ? 0.55 : 1,
    }}>
      {/* Metadata line + flag */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: "16px", marginBottom: "8px" }}>
        <div style={{ ...META_LINE, display: "flex", alignItems: "baseline", gap: "6px", flexWrap: "wrap", minWidth: 0 }}>
          <SourceBadge sourceName={item.source_name} bias={item.bias} place={item.source_place} full />
          <span>· {fmtTime(item.published_at)}</span>
          {item.urgency && item.urgency !== "routine" && <span>· {item.urgency.toUpperCase()}</span>}
        </div>
        <div style={{ ...MICRO, color: "var(--flag)", flexShrink: 0, textAlign: "right", maxWidth: "46%", whiteSpace: "normal", lineHeight: 1.5 }}>
          ⚑ {item.review_reason || "FLAGGED"}
        </div>
      </div>

      {/* Headline + original */}
      <h3 style={{
        fontFamily: "var(--font-headline)", fontSize: "20px", fontWeight: 500,
        lineHeight: 1.3, color: "var(--ink)", margin: "0 0 3px",
      }}>
        {item.title_en || item.title_original}
      </h3>
      {item.title_en && item.title_original !== item.title_en && (
        <div style={{ fontSize: "12.5px", color: "var(--pale)", marginBottom: "14px", lineHeight: 1.5 }}>
          {item.title_original}
        </div>
      )}

      {/* Model read | desk controls — the band bounded by --soft rules */}
      <div style={{
        display: "grid", gridTemplateColumns: "minmax(180px, 1fr) 2fr", gap: "0 24px",
        padding: "12px 0", borderTop: "1px solid var(--soft)", borderBottom: "1px solid var(--soft)",
        marginBottom: "14px",
      }}>
        <div>
          <div style={{ ...MICRO, marginBottom: "3px" }}>Model read</div>
          <div style={{ display: "flex", alignItems: "baseline", gap: "10px", flexWrap: "wrap" }}>
            <span style={{ fontFamily: "var(--font-headline)", fontSize: "24px", fontWeight: 500, lineHeight: 1, color: "var(--flag)" }}>
              {fmtScore(item.sentiment_score)}
            </span>
            <span style={{ ...MICRO, color: scoreColour, fontWeight: 600 }}>{item.sentiment}</span>
          </div>
          <div style={{ ...META_LINE, marginTop: "6px" }}>
            {item.topic_primary}
            {item.is_escalation_signal ? " · ESCALATION" : ""}
            {item.confidence != null ? ` · CONFIDENCE ${Math.round(item.confidence * 100)}%` : ""}
          </div>
        </div>
        <div>
          <div style={{ ...MICRO, marginBottom: "3px", color: deskDiffers ? "var(--ink)" : "var(--faint)" }}>
            Desk{deskDiffers ? " · overriding" : " · as model"}
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1.4fr 0.8fr", gap: "8px 10px" }}>
            <Field label="Sentiment">
              <select className="field" value={desk.sentiment_override} style={SELECT}
                      onChange={(e) => setDesk({ ...desk, sentiment_override: e.target.value })}>
                {SENTIMENT_OPTIONS.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </Field>
            <Field label="Topic">
              <select className="field" value={desk.topic_override} style={SELECT}
                      onChange={(e) => setDesk({ ...desk, topic_override: e.target.value })}>
                {!TOPIC_OPTIONS.includes(desk.topic_override) && desk.topic_override && (
                  <option value={desk.topic_override}>{desk.topic_override}</option>
                )}
                {TOPIC_OPTIONS.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </Field>
            <Field label="Escalation">
              <select className="field" value={desk.escalation_override ? "true" : "false"} style={SELECT}
                      onChange={(e) => setDesk({ ...desk, escalation_override: e.target.value === "true" })}>
                <option value="false">No</option>
                <option value="true">Yes</option>
              </select>
            </Field>
            <div style={{ gridColumn: "1 / -1" }}>
              <Field label="Desk note">
                <input className="field" type="text" value={desk.note} placeholder="Optional editorial note"
                       style={{ ...FIELD, fontSize: "12px", padding: "5px 8px" }}
                       onChange={(e) => setDesk({ ...desk, note: e.target.value })} />
              </Field>
            </div>
          </div>
        </div>
      </div>

      {/* The model's reasoning */}
      {item.summary_en && (
        <p style={{ fontSize: "13px", color: "var(--body)", lineHeight: 1.65, margin: "0 0 10px", textWrap: "pretty" }}>
          {item.summary_en}
        </p>
      )}
      {item.escalation_note && (
        <p style={{ fontSize: "12.5px", color: "var(--muted)", lineHeight: 1.6, margin: "0 0 10px", textWrap: "pretty" }}>
          <span style={{ ...MICRO, color: "var(--flag)" }}>Escalation note · </span>{item.escalation_note}
        </p>
      )}

      {/* Translation — always editable before any action */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: "10px", margin: "14px 0 16px" }}>
        <Field label="Headline">
          <input className="field" type="text" value={translations.title_en_override} style={FIELD}
                 onChange={(e) => setTranslations({ ...translations, title_en_override: e.target.value })} />
        </Field>
        <Field label="Summary">
          <textarea className="field" value={translations.summary_en_override} rows={3}
                    style={{ ...FIELD, resize: "vertical" }}
                    onChange={(e) => setTranslations({ ...translations, summary_en_override: e.target.value })} />
        </Field>
        <Field label="Key quote translation">
          <input className="field" type="text" value={translations.key_quote_override} style={FIELD}
                 onChange={(e) => setTranslations({ ...translations, key_quote_override: e.target.value })} />
        </Field>
      </div>

      {/* Action row — one primary */}
      <div style={{ display: "flex", gap: "8px", alignItems: "center", flexWrap: "wrap" }}>
        {deskDiffers ? (
          <Btn variant="primary" onClick={() => handleResolve("overridden")} disabled={submitting}>
            Save override
          </Btn>
        ) : (
          <Btn variant="primary" onClick={() => handleResolve("confirmed")} disabled={submitting}>
            Accept {fmtScore(item.sentiment_score)}
          </Btn>
        )}
        {deskDiffers && (
          <Btn variant="outline" onClick={() => setDesk({ ...modelDesk, note: desk.note })} disabled={submitting}>
            Keep model
          </Btn>
        )}
        <a href={item.url} target="_blank" rel="noreferrer" className="btn btn-outline" style={{ textDecoration: "none" }}>
          Source ↗
        </a>
        <span style={{ flex: 1 }} />
        <Btn variant="ghost" onClick={() => handleResolve("dismissed")} disabled={submitting}>
          Exclude
        </Btn>
      </div>
    </article>
  );
}

export default function ReviewQueue({ onClose }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchReviewQueue()
      .then((data) => setItems(Array.isArray(data) ? data : []))
      .catch((err) => {
        // Without this the loading state would persist on any fetch failure.
        console.error("Failed to load review queue:", err);
        setItems([]);
      })
      .finally(() => setLoading(false));
  }, []);

  function handleResolved(analysisId) {
    setItems((prev) => prev.filter((i) => i.analysis_id !== analysisId));
  }

  return (
    <div style={{ padding: "30px 48px 48px" }}>
      <DocumentHeader
        eyebrow="Admin · Review"
        eyebrowColour="var(--flag)"
        title="Review Queue"
        standfirst={
          <p style={STANDFIRST}>
            Articles where the two model tiers disagreed, or where a score failed the consistency
            checks. Nothing here reaches the public feed until the desk resolves it.
          </p>
        }
        meta={[loading ? "LOADING" : `${items.length} PENDING`, "TIER 3 · HUMAN GATE"]}
        actions={<Btn variant="outline" onClick={onClose}>← Feed</Btn>}
      />

      {loading ? (
        <Quiet>Loading the queue…</Quiet>
      ) : items.length === 0 ? (
        <Quiet>No articles pending review.</Quiet>
      ) : (
        items.map((item) => (
          <ReviewCard key={item.analysis_id} item={item} onResolved={handleResolved} />
        ))
      )}
    </div>
  );
}
