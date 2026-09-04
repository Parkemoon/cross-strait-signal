import { useEffect, useState } from "react";
import { fetchCopy, patchCopy } from "./api";
import { READ_ONLY } from "./readOnly";
import { ModalFrame, Btn, ErrorLine, FIELD } from "./components/adminChrome";

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
    <ModalFrame
      title="Edit copy"
      accent="var(--flag)"
      width={720}
      onClose={onClose}
      busy={busy}
      meta={k}
      footer={
        <>
          <span style={{ fontFamily: "var(--font-body)", fontSize: "11px", color: "var(--faint)", flex: 1 }}>
            Writes data/site_copy.json on the server — commit it with the next deploy. Plain text; keep any {"{placeholders}"}.
          </span>
          <Btn variant="outline" onClick={onClose} disabled={busy}>Cancel</Btn>
          <Btn variant="primary" onClick={save} disabled={busy || draft === value || !draft.trim()}>{busy ? "Saving…" : "Save"}</Btn>
        </>
      }
    >
      <textarea className="field" value={draft} onChange={(e) => setDraft(e.target.value)} rows={8} autoFocus
                style={{ ...FIELD, lineHeight: 1.55, resize: "vertical" }} />
      <ErrorLine>{err}</ErrorLine>
    </ModalFrame>
  );
}

// `as` = wrapper element (default <p>); `style` applies to it. Renders nothing
// while loading only if there is no fallback.
// `lead` renders a bold label before the text ("What is an ADIZ?") — the one
// piece of inline markup prose blocks commonly need; `leadColor` overrides it.
export function Copy({ k, fallback = "", vars, as: Tag = "p", style, lead, leadColor }) {
  const data = useCopy();
  const [editing, setEditing] = useState(false);
  const raw = data?.[k] ?? fallback;
  if (!raw) return null;
  return (
    <Tag style={{ position: "relative", ...style }}>
      {lead && <><strong style={{ color: leadColor || "var(--text-primary)" }}>{lead}</strong>{" "}</>}
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
