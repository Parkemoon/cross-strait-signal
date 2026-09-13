import { useEffect, useState } from "react";
import {
  fetchNameCandidates, approveName, rejectName, fetchNames,
} from "../api";
import { Btn, ErrorLine, Quiet } from "./adminChrome";
import { DocumentHeader } from "./documentChrome";

// Admin ▾ Names — the name registry's review queue (api/routes/names.py).
// Each pending row is one Chinese personal name the Step-3f lookup worker
// could not settle on its own: a Wikidata hit that looked like a namesake or
// carried a Hanyu-shaped label, a search-sourced spelling awaiting sign-off,
// or a generated Wade-Giles fallback. Approving writes the English form the
// resolver and the prompt-time terminology block will use for every later
// article, which is why nothing here is automatic.

const MONO = { fontFamily: "var(--font-mono)", fontSize: "11px", letterSpacing: "0.04em" };
const CELL = { padding: "8px 10px", borderBottom: "1px solid var(--hair)", verticalAlign: "top", fontSize: "13px" };
const HEAD = { ...CELL, ...MONO, fontSize: "9.5px", textTransform: "uppercase", color: "var(--muted)", textAlign: "left" };
const INPUT = {
  ...MONO, fontSize: "12px", padding: "4px 6px", width: "100%", boxSizing: "border-box",
  border: "1px solid var(--border-color)", background: "var(--bg-primary)", color: "var(--text-primary)",
};
const SOURCE_LABEL = { wikidata: "Wikidata", search: "search", generated: "generated", survey: "survey", analyst: "analyst", glossary: "glossary", canonical: "canonical" };

function Candidates({ row, onPick }) {
  const seen = new Set();
  const items = (row.candidates || []).filter((c) => c.form && !seen.has(c.form) && seen.add(c.form));
  if (!items.length) return null;
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: "4px 8px", marginTop: "4px" }}>
      {items.map((c) => (
        <button key={c.form} type="button" onClick={() => onPick(c.form)} title={c.source}
                style={{ ...MONO, background: "transparent", border: "1px solid var(--hair)", padding: "1px 6px", cursor: "pointer", color: "var(--text-primary)" }}>
          {c.form}{c.n ? <span style={{ color: "var(--muted)" }}> ×{c.n}</span> : null}
          <span style={{ color: "var(--muted)" }}> · {c.source}</span>
        </button>
      ))}
    </div>
  );
}

function Row({ row, onDone }) {
  const [en, setEn] = useState(row.en || "");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const act = async (fn) => {
    setBusy(true); setErr(null);
    try { await fn(); onDone(row.id); } catch (e) { setErr(e.message); setBusy(false); }
  };
  return (
    <tr>
      <td style={{ ...CELL, whiteSpace: "nowrap", fontSize: "15px" }}>
        {row.zh_trad}
        {row.zh_simp && row.zh_simp !== row.zh_trad ? <div style={{ ...MONO, color: "var(--muted)" }}>{row.zh_simp}</div> : null}
        <div style={{ ...MONO, color: "var(--muted)" }}>{row.mentions} mention{row.mentions === 1 ? "" : "s"}</div>
      </td>
      <td style={{ ...CELL, maxWidth: "220px", color: "var(--text-muted)" }}>{row.role_hint || "—"}</td>
      <td style={{ ...CELL, minWidth: "260px" }}>
        <input id={`name-en-${row.id}`} value={en} onChange={(e) => setEn(e.target.value)} style={INPUT} placeholder="English form" />
        <Candidates row={row} onPick={setEn} />
      </td>
      <td style={{ ...CELL, maxWidth: "360px" }}>
        <span style={{ ...MONO, textTransform: "uppercase" }}>{SOURCE_LABEL[row.source] || row.source}</span>
        {row.qid ? <> · <a href={`https://www.wikidata.org/wiki/${row.qid}`} target="_blank" rel="noopener noreferrer">{row.qid}</a></> : null}
        {row.evidence_url ? <> · <a href={row.evidence_url} target="_blank" rel="noopener noreferrer">source page</a></> : null}
        <div style={{ color: "var(--text-muted)", fontSize: "12px", marginTop: "2px" }}>{row.evidence_note}</div>
        {err ? <ErrorLine>{err}</ErrorLine> : null}
      </td>
      <td style={{ ...CELL, whiteSpace: "nowrap" }}>
        <Btn variant="primary" disabled={busy || !en.trim()} onClick={() => act(() => approveName(row.id, en.trim()))}>Approve</Btn>{" "}
        <Btn disabled={busy} onClick={() => act(() => rejectName(row.id))}>Reject</Btn>
      </td>
    </tr>
  );
}

export default function NamesReviewQueue() {
  const [rows, setRows] = useState(null);
  const [total, setTotal] = useState(0);
  const [approved, setApproved] = useState(null);
  const [q, setQ] = useState("");
  const [error, setError] = useState(null);

  const load = async () => {
    try {
      const d = await fetchNameCandidates();
      setRows(d.candidates); setTotal(d.total);
    } catch (e) { setError(e.message); }
  };
  useEffect(() => { load(); }, []);
  useEffect(() => {
    let live = true;
    fetchNames({ status: "approved", q, limit: 50 }).then((d) => { if (live) setApproved(d.names); }).catch(() => {});
    return () => { live = false; };
  }, [q]);

  const done = (id) => { setRows((r) => r.filter((x) => x.id !== id)); setTotal((t) => Math.max(0, t - 1)); };

  return (
    <div>
      <DocumentHeader eyebrow="Admin · Names" eyebrowColour="var(--flag)" title="Name registry"
        standfirst="Chinese personal names the lookup worker could not settle: a Wikidata namesake, a Hanyu-shaped label, a search result awaiting sign-off, or a generated fallback. The form approved here is what every later article uses."
        meta={`${total} pending`} />
      {error ? <ErrorLine>{error}</ErrorLine> : null}
      {rows === null ? <Quiet>Loading…</Quiet> : rows.length === 0 ? <Quiet>Nothing pending.</Quiet> : (
        <div style={{ overflowX: "auto", border: "1px solid var(--hair)", background: "var(--bg-card)" }}>
          <table style={{ borderCollapse: "collapse", width: "100%", minWidth: "900px" }}>
            <thead><tr>
              <th style={HEAD}>Name</th><th style={HEAD}>Role (model)</th><th style={HEAD}>English form</th>
              <th style={HEAD}>Where it came from</th><th style={HEAD}></th>
            </tr></thead>
            <tbody>{rows.map((r) => <Row key={r.id} row={r} onDone={done} />)}</tbody>
          </table>
        </div>
      )}

      <div style={{ marginTop: "32px" }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: "12px", flexWrap: "wrap" }}>
          <h3 style={{ margin: 0, fontSize: "15px" }}>Approved names</h3>
          <input id="names-search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="search either script or the English form" style={{ ...INPUT, width: "320px", maxWidth: "100%" }} />
        </div>
        {approved === null ? <Quiet>Loading…</Quiet> : (
          <div style={{ overflowX: "auto", marginTop: "8px" }}>
            <table style={{ borderCollapse: "collapse", width: "100%", minWidth: "600px" }}>
              <tbody>{approved.map((r) => (
                <tr key={r.id}>
                  <td style={{ ...CELL, whiteSpace: "nowrap" }}>{r.zh_trad}{r.zh_simp && r.zh_simp !== r.zh_trad ? <span style={{ color: "var(--muted)" }}> / {r.zh_simp}</span> : null}</td>
                  <td style={{ ...CELL, fontWeight: 600 }}>{r.en}</td>
                  <td style={{ ...CELL, ...MONO, color: "var(--muted)" }}>{SOURCE_LABEL[r.source] || r.source}{r.reviewed_by ? ` · ${r.reviewed_by}` : ""}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
