import { useEffect, useMemo, useState } from "react";
import { fetchCoastGuardVessels, updateCoastGuardVessel } from "../api";
import { FORCES, FORCE_COLOUR, Pill } from "./coastGuardShared";

// Analyst roster review for the Coast Guard tracker. The failure mode of a
// name-based classifier is a civilian hull named "COAST GUARD" (or a Taiwanese
// "HAI JING") counted as a coast-guard vessel, so every hull carries a status:
// auto (classifier) / confirmed / rejected. Rejected hulls drop out of every
// aggregate server-side. Identity anomalies (MID/flag mismatch, name change)
// are surfaced as chips — they are findings, not errors (spoofed MIDs are part
// of the behaviour), so the default action on an anomaly is "confirm", not
// "reject".
const FLAG_LABEL = {
  mid_mismatch: "MID ≠ force",
  flag_mismatch: "flag ≠ force",
  name_change: "name changed",
};

function StatusTag({ status }) {
  const c = status === "confirmed" ? "#16a34a" : status === "rejected" ? "#dc2626" : "var(--text-muted)";
  return <span style={{ fontFamily: "var(--font-mono)", fontSize: "9.5px", color: c, letterSpacing: "0.05em" }}>{status.toUpperCase()}</span>;
}

export default function CoastGuardRosterModal({ onClose, onChanged }) {
  const [vessels, setVessels] = useState(null);
  const [force, setForce] = useState("CCG");
  const [anomaliesOnly, setAnomaliesOnly] = useState(true);
  const [activeOnly, setActiveOnly] = useState(true);
  const [busy, setBusy] = useState(null);
  const [notesDraft, setNotesDraft] = useState({});

  const load = () => {
    setVessels(null);
    fetchCoastGuardVessels({ force, anomalies: anomaliesOnly ? "true" : "false", days: 365, limit: 800 })
      .then((r) => setVessels(r.vessels || []))
      .catch(() => setVessels([]));
  };
  useEffect(load, [force, anomaliesOnly]);   // eslint-disable-line react-hooks/exhaustive-deps

  const rows = useMemo(() => (vessels || []).filter((v) => !activeOnly || v.hull_days > 0), [vessels, activeOnly]);

  const patch = async (v, body) => {
    setBusy(v.mmsi);
    try {
      const updated = await updateCoastGuardVessel(v.mmsi, body);
      setVessels((prev) => (prev || []).map((x) => (x.mmsi === v.mmsi ? { ...x, ...updated?.vessel, ...body } : x)));
      onChanged?.();
    } catch (e) {
      window.alert(`Update failed: ${e.message || e}`);   // eslint-disable-line no-alert
    } finally {
      setBusy(null);
    }
  };

  return (
    <div onClick={(e) => e.target === e.currentTarget && onClose()}
         style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.55)", display: "flex",
                  alignItems: "center", justifyContent: "center", zIndex: 1000 }}>
      <div style={{ background: "var(--bg-card)", border: "1px solid var(--border-color)",
                    borderTop: "4px solid #7c3aed", borderRadius: "4px", width: 900, maxWidth: "94vw",
                    maxHeight: "86vh", display: "flex", flexDirection: "column" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between",
                      padding: "14px 16px", borderBottom: "1px solid var(--border-color)" }}>
          <div>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: "11px", fontWeight: 700,
                           letterSpacing: "0.07em", textTransform: "uppercase", color: "var(--text-primary)" }}>
              Coast guard roster
            </span>
            <span style={{ fontSize: "10px", color: "var(--text-muted)", marginLeft: "10px" }}>
              {vessels ? `${rows.length} hulls` : "…"}
            </span>
          </div>
          <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer",
                                             color: "var(--text-muted)", fontSize: "16px", padding: "2px 4px" }}>✕</button>
        </div>

        <div style={{ display: "flex", gap: "6px", flexWrap: "wrap", padding: "10px 16px",
                      borderBottom: "1px solid var(--border-color)", alignItems: "center" }}>
          {FORCES.map((f) => <Pill key={f} active={force === f} colour={FORCE_COLOUR[f]} onClick={() => setForce(f)}>{f}</Pill>)}
          <span style={{ width: 8 }} />
          <Pill active={anomaliesOnly} onClick={() => setAnomaliesOnly((x) => !x)}>anomalies only</Pill>
          <Pill active={activeOnly} onClick={() => setActiveOnly((x) => !x)}>seen in 365 d</Pill>
        </div>

        <div style={{ overflowY: "auto", padding: "4px 0" }}>
          {!vessels ? (
            <div style={{ padding: "24px 16px", color: "var(--text-muted)", fontFamily: "var(--font-mono)", fontSize: "12px" }}>Loading…</div>
          ) : rows.length === 0 ? (
            <div style={{ padding: "24px 16px", color: "var(--text-muted)", fontFamily: "var(--font-mono)", fontSize: "12px" }}>No hulls match.</div>
          ) : rows.map((v) => (
            <div key={v.mmsi} style={{ display: "grid", gridTemplateColumns: "minmax(0, 2fr) minmax(0, 2fr) auto",
                                       gap: "8px 14px", padding: "10px 16px", borderBottom: "1px solid var(--border-color)",
                                       alignItems: "start", opacity: v.status === "rejected" ? 0.55 : 1 }}>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontFamily: "var(--font-mono)", fontSize: "12px", color: "var(--text-primary)", fontWeight: 600 }}>
                  <span style={{ display: "inline-block", width: 8, height: 8, background: FORCE_COLOUR[v.force], marginRight: 6 }} />
                  {v.name || "(no name)"} {v.hull_no && <span style={{ color: "var(--text-muted)" }}>· #{v.hull_no}</span>}
                </div>
                <div style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--text-muted)", marginTop: 2 }}>
                  MMSI {v.mmsi} · flag {v.flag || "—"} · {v.first_seen || "?"} → {v.last_seen || "?"}
                </div>
                <div style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--text-secondary)", marginTop: 2 }}>
                  {v.hull_days} hull-days / 365 d{v.zones?.length ? ` · ${v.zones.join(", ")}` : ""}
                </div>
              </div>
              <div style={{ minWidth: 0 }}>
                <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginBottom: 6 }}>
                  {(v.anomaly_flags || []).map((f) => (
                    <span key={f} style={{ fontFamily: "var(--font-mono)", fontSize: "9.5px", padding: "1px 5px",
                                           border: "1px solid #b8860b88", color: "#b8860b", background: "rgba(184,134,11,0.12)" }}>
                      ⚑ {FLAG_LABEL[f] || f}
                    </span>
                  ))}
                  <StatusTag status={v.status} />
                </div>
                <textarea value={notesDraft[v.mmsi] ?? (v.notes || "")}
                          onChange={(e) => setNotesDraft((d) => ({ ...d, [v.mmsi]: e.target.value }))}
                          onBlur={() => { const n = notesDraft[v.mmsi]; if (n !== undefined && n !== (v.notes || "")) patch(v, { notes: n }); }}
                          placeholder="analyst note"
                          rows={2}
                          style={{ width: "100%", fontFamily: "var(--font-body)", fontSize: "11px", background: "var(--bg-primary)",
                                   color: "var(--text-primary)", border: "1px solid var(--border-color)", padding: "4px 6px", resize: "vertical" }} />
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 4, alignItems: "stretch" }}>
                <Pill active={v.status === "confirmed"} colour="#16a34a" onClick={() => busy !== v.mmsi && patch(v, { status: "confirmed" })}>✓ confirm</Pill>
                <Pill active={v.status === "rejected"} colour="#dc2626" onClick={() => busy !== v.mmsi && patch(v, { status: "rejected" })}>✕ reject</Pill>
                <select value={v.force} onChange={(e) => patch(v, { force: e.target.value })}
                        style={{ fontFamily: "var(--font-mono)", fontSize: "10px", background: "var(--bg-primary)",
                                 color: "var(--text-secondary)", border: "1px solid var(--border-color)", padding: "2px 4px" }}>
                  {FORCES.map((f) => <option key={f} value={f}>{f}</option>)}
                </select>
              </div>
            </div>
          ))}
        </div>
        <div style={{ padding: "8px 16px", borderTop: "1px solid var(--border-color)", fontFamily: "var(--font-mono)",
                      fontSize: "10px", color: "var(--text-muted)", lineHeight: 1.5 }}>
          Reject removes the hull from every aggregate. Changing force rewrites its presence rows. Anomalies are findings
          (spoofed MIDs, name switches) — confirm them unless the hull is plainly civilian.
        </div>
      </div>
    </div>
  );
}
