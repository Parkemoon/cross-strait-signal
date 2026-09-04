import { useEffect, useMemo, useState } from "react";
import { fetchCoastGuardVessels, updateCoastGuardVessel } from "../api";
import { FORCES, FORCE_COLOUR, Pill } from "./coastGuardShared";
import { ModalFrame } from "./adminChrome";

// Analyst roster review for the Coast Guard tracker. There is exactly ONE
// question here — "is this hull a coast-guard vessel?" — because that's the
// only thing answerable from a desk (name, hull number, where it's been
// seen). A deterministic triage (scripts/triage_coast_guard_roster.py) settles
// it for almost every hull; what's left is 'auto'. Anomaly flags (MID/flag
// mismatch, name change) are recorded facts about the AIS stream — nobody can
// verify from here whether a spoofed MID was deliberate — so they render as
// read-only attributes and are never something the analyst signs off.
// Rejected hulls drop out of every aggregate server-side.
const STATUSES = [
  { id: "auto", label: "unreviewed" },
  { id: "confirmed", label: "coast guard" },
  { id: "rejected", label: "not coast guard" },
];
const FLAG_INFO = {
  mid_mismatch:  ["MID ≠ force", "The MMSI's first three digits are allocated to a different country than the force's — a spoofed or mis-set transponder. Recorded fact; not verifiable further."],
  flag_mismatch: ["flag ≠ force", "GFW resolved a different flag state for this identity than the force's country. Recorded fact; not verifiable further."],
  name_change:   ["name changed", "This MMSI has broadcast more than one ship name over time (renumbering, or a switch such as 5901 → 'CAPTAIN ASLEEP'). Recorded fact."],
};

function StatusTag({ status }) {
  const c = status === "confirmed" ? "var(--green)" : status === "rejected" ? "var(--red)" : "var(--flag)";
  const label = STATUSES.find((s) => s.id === status)?.label || status;
  return <span style={{ fontFamily: "var(--font-mono)", fontSize: "9.5px", color: c, letterSpacing: "0.05em" }}>{label.toUpperCase()}</span>;
}

export default function CoastGuardRosterModal({ onClose, onChanged }) {
  const [vessels, setVessels] = useState(null);
  const [force, setForce] = useState("CCG");
  const [status, setStatus] = useState("auto");
  const [activeOnly, setActiveOnly] = useState(true);
  const [busy, setBusy] = useState(null);
  const [notesDraft, setNotesDraft] = useState({});

  const load = () => {
    setVessels(null);
    fetchCoastGuardVessels({ force, status, days: 365, limit: 800 })
      .then((r) => setVessels(r.vessels || []))
      .catch(() => setVessels([]));
  };
  useEffect(load, [force, status]);   // eslint-disable-line react-hooks/exhaustive-deps

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
    <ModalFrame
      title="Coast guard roster"
      accent="var(--hostile)"
      width={900}
      onClose={onClose}
      meta={vessels ? `${rows.length} hulls` : "…"}
      bodyStyle={{ padding: 0 }}
      footer={
        <span style={{ fontFamily: "var(--font-body)", fontSize: "11.5px", color: "var(--muted)", lineHeight: 1.5 }}>
          "Not coast guard" removes the hull from every chart. Anomaly flags stay on the record either way — they are what the
          hull broadcast, not what it did.
        </span>
      }
    >

        <div style={{ padding: "12px 18px 0", fontFamily: "var(--font-body)", fontSize: "12.5px", color: "var(--body)", lineHeight: 1.6 }}>
          One question per hull: <strong>is it a coast-guard vessel?</strong> A deterministic triage already settled every hull with an
          explicit force name or a matching MID prefix; <em>unreviewed</em> lists what it couldn't. Anomaly chips are recorded facts about
          the AIS broadcast, shown for context — they are not verifiable from here and not what you're confirming.
        </div>
        <div style={{ display: "flex", gap: "6px", flexWrap: "wrap", padding: "10px 16px",
                      borderBottom: "1px solid var(--border-color)", alignItems: "center" }}>
          {FORCES.map((f) => <Pill key={f} active={force === f} colour={FORCE_COLOUR[f]} onClick={() => setForce(f)}>{f}</Pill>)}
          <span style={{ width: 8 }} />
          {STATUSES.map((s) => <Pill key={s.id} active={status === s.id} onClick={() => setStatus(s.id)}>{s.label}</Pill>)}
          <span style={{ width: 8 }} />
          <Pill active={activeOnly} onClick={() => setActiveOnly((x) => !x)}>seen in 365 d</Pill>
        </div>

        <div style={{ overflowY: "auto", padding: "4px 0" }}>
          {!vessels ? (
            <div style={{ padding: "24px 16px", color: "var(--text-muted)", fontFamily: "var(--font-mono)", fontSize: "12px" }}>Loading…</div>
          ) : rows.length === 0 ? (
            <div style={{ padding: "24px 16px", color: "var(--text-muted)", fontFamily: "var(--font-mono)", fontSize: "12px" }}>
              {status === "auto" ? "Nothing unreviewed — every seen hull is settled." : "No hulls match."}
            </div>
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
                <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginBottom: 6, alignItems: "center" }}>
                  <StatusTag status={v.status} />
                  {(v.anomaly_flags || []).map((f) => (
                    <span key={f} title={FLAG_INFO[f]?.[1] || f}
                          style={{ fontFamily: "var(--font-mono)", fontSize: "9.5px", padding: "1px 5px", cursor: "help",
                                   border: "1px solid var(--border-color)", color: "var(--text-muted)" }}>
                      ⚑ {FLAG_INFO[f]?.[0] || f}
                    </span>
                  ))}
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
                <Pill active={v.status === "confirmed"} colour="var(--green)" onClick={() => busy !== v.mmsi && patch(v, { status: "confirmed" })}>✓ coast guard</Pill>
                <Pill active={v.status === "rejected"} colour="var(--red)" onClick={() => busy !== v.mmsi && patch(v, { status: "rejected" })}>✕ not coast guard</Pill>
                <select value={v.force} onChange={(e) => patch(v, { force: e.target.value })}
                        title="Re-assign force (rewrites the hull's presence rows)"
                        style={{ fontFamily: "var(--font-mono)", fontSize: "10px", background: "var(--bg-primary)",
                                 color: "var(--text-secondary)", border: "1px solid var(--border-color)", padding: "2px 4px" }}>
                  {FORCES.map((f) => <option key={f} value={f}>{f}</option>)}
                </select>
              </div>
            </div>
          ))}
        </div>
    </ModalFrame>
  );
}
