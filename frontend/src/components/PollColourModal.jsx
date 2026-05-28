import { useEffect, useState } from "react";
import { fetchOptionParties, setOptionParty } from "../api";
import { partyColour, PARTY_LABELS, PARTY_ORDER } from "../partyColours";
import { fieldStyle } from "./pollFormShared";

const HEX_RX = /^#[0-9a-fA-F]{6}$/;

// Resolve the preview swatch for a row: explicit hex wins, then the selected
// party, then the auto (key_figures-derived) party.
function rowColour(r) {
  return r.colour || partyColour(r.party) || partyColour(r.autoParty);
}

export default function PollColourModal({ payload, onClose, onSaved }) {
  const [rows, setRows] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  // Build the distinct-option list from the payload, then overlay the
  // explicit assignments so the form shows what's pinned (vs auto-resolved).
  useEffect(() => {
    let cancelled = false;
    const distinct = new Map();
    for (const w of payload.waves || []) {
      for (const o of w.options || []) {
        const zh = o.label_zh;
        if (!zh) continue;
        if (!distinct.has(zh)) {
          distinct.set(zh, { label_zh: zh, label_en: o.label_en || null, payloadParty: o.party || null });
        } else if (!distinct.get(zh).label_en && o.label_en) {
          distinct.get(zh).label_en = o.label_en;
        }
      }
    }
    fetchOptionParties()
      .then((res) => {
        if (cancelled) return;
        const explicit = {};
        for (const a of res.assignments || []) explicit[a.option_label_zh] = a;
        setRows(Array.from(distinct.values()).map((d) => {
          const ex = explicit[d.label_zh];
          return {
            label_zh:   d.label_zh,
            label_en:   d.label_en,
            // When no explicit row, the payload party IS the auto (key_figures) value.
            autoParty:  ex ? null : d.payloadParty,
            party:      ex?.party || "",
            colour:     ex?.colour_override || "",
            initParty:  ex?.party || "",
            initColour: ex?.colour_override || "",
          };
        }));
      })
      .catch((e) => { if (!cancelled) setErr(e.message || String(e)); });
    return () => { cancelled = true; };
  }, [payload]);

  const setRow = (i, next) => setRows((rs) => rs.map((r, j) => (i === j ? { ...r, ...next } : r)));

  const badHex = rows?.some((r) => r.colour && !HEX_RX.test(r.colour));

  const save = async () => {
    setBusy(true);
    setErr(null);
    try {
      const changed = rows.filter((r) => r.party !== r.initParty || r.colour !== r.initColour);
      for (const r of changed) {
        await setOptionParty({
          option_label_zh: r.label_zh,
          party: r.party || null,
          colour_override: r.colour || null,
          reviewed_by: "analyst",
        });
      }
      onSaved();
    } catch (e) {
      setErr(e.message || String(e));
      setBusy(false);
    }
  };

  return (
    <div
      onClick={(e) => e.target === e.currentTarget && !busy && onClose()}
      style={{
        position: "fixed", inset: 0, background: "rgba(0,0,0,0.55)",
        display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000,
      }}
    >
      <div style={{
        background: "var(--bg-card)", border: "1px solid var(--border-color)",
        borderTop: "4px solid #0f766e", borderRadius: "4px",
        width: 620, maxWidth: "94vw", maxHeight: "88vh",
        display: "flex", flexDirection: "column",
      }}>
        <div style={{
          display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "14px 16px", borderBottom: "1px solid var(--border-color)",
        }}>
          <div>
            <span style={{
              fontFamily: "var(--font-mono)", fontSize: "11px", fontWeight: 700,
              letterSpacing: "0.07em", textTransform: "uppercase", color: "var(--text-primary)",
            }}>
              Option colours
            </span>
            <span style={{ fontSize: "10px", color: "var(--text-muted)", marginLeft: "10px" }}>
              {payload.question_text_en || payload.question_key}
            </span>
          </div>
          <button onClick={onClose} disabled={busy}
                  style={{ background: "none", border: "none", cursor: busy ? "default" : "pointer",
                           color: "var(--text-muted)", fontSize: "16px", padding: "2px 4px" }}>
            ✕
          </button>
        </div>

        <div style={{ overflowY: "auto", padding: "14px 16px", opacity: busy ? 0.55 : 1 }}>
          <p style={{ fontFamily: "var(--font-mono)", fontSize: "10px", lineHeight: 1.5,
                      color: "var(--text-muted)", margin: "0 0 12px 0" }}>
            Party drives the line colour. <strong>Auto</strong> resolves from the key-figure
            roster (e.g. Lai → DPP) and falls back to the default palette. A custom hex
            (<code>#RRGGBB</code>) overrides the party — use it for independents or palette clashes.
          </p>

          {rows === null ? (
            <div style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--text-muted)" }}>
              Loading…
            </div>
          ) : rows.length === 0 ? (
            <div style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--text-muted)" }}>
              No options on this chart yet.
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
              {rows.map((r, i) => {
                const swatch = rowColour(r);
                return (
                  <div key={r.label_zh} style={{
                    display: "grid",
                    gridTemplateColumns: "16px 1fr 150px 110px",
                    gap: "8px", alignItems: "center",
                  }}>
                    <span style={{
                      width: 14, height: 14, borderRadius: "50%",
                      background: swatch || "transparent",
                      border: swatch ? "none" : "1px dashed var(--border-color)",
                    }} title={swatch || "auto / unset"} />
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontSize: "12px", color: "var(--text-primary)" }}>{r.label_zh}</div>
                      {r.label_en && (
                        <div style={{ fontSize: "10px", color: "var(--text-muted)" }}>{r.label_en}</div>
                      )}
                    </div>
                    <select
                      style={fieldStyle()}
                      value={r.party}
                      onChange={(e) => setRow(i, { party: e.target.value })}
                    >
                      <option value="">
                        Auto{r.autoParty ? ` (${r.autoParty})` : ""}
                      </option>
                      {PARTY_ORDER.map((p) => (
                        <option key={p} value={p}>{PARTY_LABELS[p]}</option>
                      ))}
                    </select>
                    <input
                      type="text"
                      placeholder="#RRGGBB"
                      value={r.colour}
                      onChange={(e) => setRow(i, { colour: e.target.value.trim() })}
                      style={{
                        ...fieldStyle(),
                        borderColor: r.colour && !HEX_RX.test(r.colour) ? "#dc2626" : undefined,
                      }}
                    />
                  </div>
                );
              })}
            </div>
          )}

          {err && (
            <div style={{ marginTop: "10px", padding: "8px 10px", border: "1px solid #dc2626",
                          background: "rgba(220,38,38,0.08)", color: "#dc2626",
                          fontFamily: "var(--font-mono)", fontSize: "11px" }}>
              {err}
            </div>
          )}
        </div>

        <div style={{
          display: "flex", justifyContent: "flex-end", gap: "8px",
          padding: "12px 16px", borderTop: "1px solid var(--border-color)",
        }}>
          <button onClick={onClose} disabled={busy} style={{
            padding: "6px 14px", fontFamily: "var(--font-mono)", fontSize: "10px",
            letterSpacing: "0.06em", textTransform: "uppercase",
            border: "1px solid var(--border-color)", background: "transparent",
            color: "var(--text-secondary)", cursor: busy ? "default" : "pointer",
          }}>
            Cancel
          </button>
          <button onClick={save} disabled={busy || badHex || rows === null} style={{
            padding: "6px 14px", fontFamily: "var(--font-mono)", fontSize: "10px",
            letterSpacing: "0.06em", textTransform: "uppercase",
            border: "1px solid #0f766e",
            background: busy || badHex ? "transparent" : "#0f766e",
            color: busy || badHex ? "var(--text-muted)" : "#fff",
            cursor: busy || badHex ? "default" : "pointer",
          }}>
            {busy ? "Saving…" : "Save colours"}
          </button>
        </div>
      </div>
    </div>
  );
}
