import { useEffect, useState } from "react";
import { fetchOptionParties, setOptionParty } from "../api";
import { partyColour, PARTY_LABELS, PARTY_ORDER } from "../partyColours";
import { fieldStyle } from "./pollFormShared";
import { ModalFrame, Btn } from "./adminChrome";

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
    <ModalFrame
      title="Option colours"
      accent="var(--cyan)"
      width={620}
      onClose={onClose}
      busy={busy}
      meta={payload.question_text_en || payload.question_key}
      footer={
        <>
          <span style={{ flex: 1 }} />
          <Btn variant="outline" onClick={onClose} disabled={busy}>Cancel</Btn>
          <Btn variant="primary" onClick={save} disabled={busy || badHex || rows === null}>{busy ? "Saving…" : "Save colours"}</Btn>
        </>
      }
    >

        <div>
          <p style={{ fontFamily: "var(--font-body)", fontSize: "12.5px", lineHeight: 1.6,
                      color: "var(--muted)", margin: "0 0 12px 0" }}>
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
                        borderColor: r.colour && !HEX_RX.test(r.colour) ? "var(--red)" : undefined,
                      }}
                    />
                  </div>
                );
              })}
            </div>
          )}

          {err && (
            <div style={{ marginTop: "10px", padding: "8px 10px", border: "1px solid var(--red)",
                          background: "color-mix(in srgb, var(--red) 8%, transparent)", color: "var(--red)",
                          fontFamily: "var(--font-mono)", fontSize: "11px" }}>
              {err}
            </div>
          )}
        </div>
    </ModalFrame>
  );
}
