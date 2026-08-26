import { useEffect, useState } from "react";
import { fetchCopy, patchCopy } from "./api";
import { READ_ONLY } from "./readOnly";

// Editable site prose. `<Copy k="maritime.intro" />` renders the string from
// data/site_copy.json (via GET /api/copy/) and, in the admin build, a ✎ that
// rewrites it in place through PATCH /api/copy/{key} — the Positions inline-
// editing flow generalised to every prose block. Missing key → the fallback,
// so a stale bundle never blanks a paragraph. {placeholders} are filled from
// `vars`. Plain text only; blocks with links stay in JSX.
//
// One fetch per page load, shared by every <Copy> via a module-level store.
const store = { data: null, promise: null, listeners: new Set() };

function load() {
  if (!store.promise) {
    store.promise = fetchCopy()
      .then((r) => { store.data = r?.copy || {}; })
      .catch(() => { store.data = {}; })
      .finally(() => store.listeners.forEach((fn) => fn()));
  }
  return store.promise;
}

export function useCopy() {
  const [, tick] = useState(0);
  useEffect(() => {
    const fn = () => tick((n) => n + 1);
    store.listeners.add(fn);
    load();
    return () => store.listeners.delete(fn);
  }, []);
  return store.data;
}

export function fill(text, vars) {
  if (!vars) return text;
  return text.replace(/\{(\w+)\}/g, (m, k) => (vars[k] === undefined || vars[k] === null ? m : String(vars[k])));
}

function CopyEditModal({ k, value, onClose, onSaved }) {
  const [draft, setDraft] = useState(value);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const save = async () => {
    setBusy(true); setErr(null);
    try {
      await patchCopy(k, draft);
      store.data = { ...store.data, [k]: draft };
      store.listeners.forEach((fn) => fn());
      onSaved?.();
      onClose();
    } catch (e) {
      setErr(e.message || String(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div onClick={(e) => e.target === e.currentTarget && onClose()}
         style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.55)", display: "flex",
                  alignItems: "center", justifyContent: "center", zIndex: 1000 }}>
      <div style={{ background: "var(--bg-card)", border: "1px solid var(--border-color)", borderTop: "4px solid #b8860b",
                    borderRadius: "4px", width: 720, maxWidth: "94vw", display: "flex", flexDirection: "column" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "12px 16px",
                      borderBottom: "1px solid var(--border-color)" }}>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: "11px", fontWeight: 700, letterSpacing: "0.07em",
                         textTransform: "uppercase", color: "var(--text-primary)" }}>Edit copy</span>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--text-muted)" }}>{k}</span>
        </div>
        <textarea value={draft} onChange={(e) => setDraft(e.target.value)} rows={8} autoFocus
                  style={{ margin: "12px 16px", fontFamily: "var(--font-body)", fontSize: "13px", lineHeight: 1.5,
                           background: "var(--bg-primary)", color: "var(--text-primary)",
                           border: "1px solid var(--border-color)", padding: "8px 10px", resize: "vertical" }} />
        {err && <div style={{ margin: "0 16px 8px", fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--accent-red)" }}>{err}</div>}
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, padding: "0 16px 12px" }}>
          <button onClick={onClose} style={{ fontFamily: "var(--font-mono)", fontSize: "10px", padding: "5px 12px", cursor: "pointer",
                                             background: "transparent", color: "var(--text-secondary)", border: "1px solid var(--border-color)" }}>Cancel</button>
          <button onClick={save} disabled={busy || draft === value || !draft.trim()}
                  style={{ fontFamily: "var(--font-mono)", fontSize: "10px", padding: "5px 12px", cursor: "pointer",
                           background: "var(--text-primary)", color: "var(--bg-primary)", border: "1px solid var(--text-primary)",
                           opacity: busy || draft === value || !draft.trim() ? 0.5 : 1 }}>{busy ? "Saving…" : "Save"}</button>
        </div>
        <div style={{ padding: "0 16px 10px", fontFamily: "var(--font-mono)", fontSize: "9.5px", color: "var(--text-muted)" }}>
          Writes data/site_copy.json on the server — commit it with the next deploy. Plain text; keep any {"{placeholders}"}.
        </div>
      </div>
    </div>
  );
}

// `as` = wrapper element (default <p>); `style` applies to it. Renders nothing
// while loading only if there is no fallback.
export function Copy({ k, fallback = "", vars, as: Tag = "p", style }) {
  const data = useCopy();
  const [editing, setEditing] = useState(false);
  const raw = data?.[k] ?? fallback;
  if (!raw) return null;
  return (
    <Tag style={{ position: "relative", ...style }}>
      {fill(raw, vars)}
      {!READ_ONLY && data && (
        <button onClick={() => setEditing(true)} title={`Edit copy · ${k}`}
                style={{ marginLeft: 6, background: "none", border: "none", cursor: "pointer", padding: 0,
                         color: "#b8860b", fontSize: "11px", verticalAlign: "baseline", opacity: 0.7 }}>✎</button>
      )}
      {editing && <CopyEditModal k={k} value={raw} onClose={() => setEditing(false)} />}
    </Tag>
  );
}
