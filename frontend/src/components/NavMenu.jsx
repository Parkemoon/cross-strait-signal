import { useEffect, useRef, useState } from "react";
import { NAV_GROUPS, groupForView } from "../navGroups";

// Masthead navigation, rendered from NAV_GROUPS (Morning Brief restyle).
//   <NavMenu view=… onSelect={setView} badges={{review: n}} />              desktop
//   <NavMenu mobile tab=… onSelect={selectMobileTab} badges=… />            mobile
// Desktop: centred text row; groups with items open a dropdown on hover
// (an 8px transparent bridge under the label lets the pointer cross the gap)
// or click. Clicking the group label of the CURRENT view returns to the feed.
// Active item/group carries a 2px ink underline; the 2px is always reserved
// so nothing shifts. Mobile: the sticky two-level bar (groups → items with ‹ back), retoned.

const NAVTEXT = {
  fontFamily: "var(--font-mono)",
  textTransform: "uppercase",
  letterSpacing: "0.16em",
  fontSize: "10.5px",
  fontWeight: 600,
};

function Sup({ n }) {
  if (!n) return null;
  return (
    <span style={{ fontFamily: "var(--font-mono)", fontSize: "8px", color: "var(--flag)",
                   verticalAlign: "super", letterSpacing: 0, marginLeft: "2px" }}>{n}</span>
  );
}

function badgeFor(group, badges) {
  return (group.items || []).reduce((s, i) => s + (i.badge ? badges?.[i.badge] || 0 : 0), 0);
}

function navItemStyle(isActive) {
  return {
    ...NAVTEXT,
    background: "none",
    border: "none",
    cursor: "pointer",
    padding: "0 0 3px",
    lineHeight: 1.3,
    color: isActive ? "var(--ink)" : "var(--faint)",
    borderBottom: isActive ? "2px solid var(--ink)" : "2px solid transparent",
  };
}

function DesktopGroup({ group, view, onSelect, badges }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const active = groupForView(view)?.id === group.id && view !== "feed";
  const badge = badgeFor(group, badges);

  useEffect(() => {
    if (!open) return undefined;
    const close = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    const esc = (e) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", close); document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", esc); };
  }, [open]);

  if (!group.items) {
    return <button onClick={() => onSelect(group.view)} style={navItemStyle(view === group.view)}>{group.label}</button>;
  }
  return (
    <div ref={ref} style={{ position: "relative", display: "inline-block" }}
         onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
      <button onClick={() => { if (active) { onSelect("feed"); setOpen(false); } else setOpen((o) => !o); }}
              aria-haspopup="menu" aria-expanded={open} style={navItemStyle(active)}>
        {group.label} <span style={{ fontSize: "8px", opacity: 0.7 }}>▾</span>
        <Sup n={badge} />
      </button>
      {open && (
        <div role="menu" style={{ position: "absolute", top: "100%", left: "50%", transform: "translateX(-50%)",
                                  zIndex: 300, paddingTop: "8px", textAlign: "left" }}>
          <div style={{ background: "var(--bg)", border: "1px solid var(--hair)", minWidth: "158px",
                        boxShadow: "0 10px 24px rgba(28,26,22,0.13)", animation: "fadeup 0.16s ease-out" }}>
            {group.items.map((item, idx) => {
              const isActive = view === item.view;
              const n = item.badge ? badges?.[item.badge] || 0 : 0;
              return (
                <button key={item.view} role="menuitem" onClick={() => { onSelect(item.view); setOpen(false); }}
                        onMouseEnter={(e) => { e.currentTarget.style.background = "var(--soft)"; e.currentTarget.style.color = "var(--ink)"; }}
                        onMouseLeave={(e) => { e.currentTarget.style.background = isActive ? "var(--soft)" : "transparent"; e.currentTarget.style.color = isActive ? "var(--ink)" : "var(--muted)"; }}
                        style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "12px",
                                 width: "100%", textAlign: "left", padding: "9px 14px", cursor: "pointer",
                                 fontFamily: "var(--font-mono)", fontSize: "10px", letterSpacing: "0.12em",
                                 textTransform: "uppercase",
                                 background: isActive ? "var(--soft)" : "transparent",
                                 color: isActive ? "var(--ink)" : "var(--muted)",
                                 border: "none",
                                 borderBottom: idx < group.items.length - 1 ? "1px solid var(--soft)" : "none" }}>
                  <span>{item.label}</span>
                  {n > 0 && <span style={{ color: "var(--flag)", fontFamily: "var(--font-mono)" }}>{n}</span>}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

// Mobile tabs = the desktop groups plus the two feed-only panels.
const MOBILE_EXTRA = [{ id: "stats", label: "Stats", after: "feed" }, { id: "social", label: "Social", after: "politics" }];

function mobileTopLevel() {
  const out = [];
  for (const g of NAV_GROUPS) {
    out.push({ id: g.id, label: g.label, group: g });
    for (const x of MOBILE_EXTRA) if (x.after === g.id) out.push({ id: x.id, label: x.label });
  }
  return out;
}

function MobileBar({ tab, onSelect, badges }) {
  const [openGroup, setOpenGroup] = useState(null);
  const tabStyle = (isActive) => ({
    ...NAVTEXT, flex: "1 0 auto", padding: "13px 10px", whiteSpace: "nowrap", background: "transparent",
    cursor: "pointer", fontSize: "10.5px", position: "relative",
    color: isActive ? "var(--ink)" : "var(--faint)", border: "none",
    borderBottom: isActive ? "2px solid var(--ink)" : "2px solid transparent",
  });
  const g = openGroup ? NAV_GROUPS.find((x) => x.id === openGroup) : null;
  const currentGroup = groupForView(tab);
  return (
    <nav className="hide-scrollbar"
         style={{ position: "sticky", top: 0, background: "var(--bg)", borderBottom: "1px solid var(--hair)",
                  borderTop: "3px double var(--ink)", display: "flex", zIndex: 100, overflowX: "auto" }}>
      {g ? (
        <>
          <button onClick={() => setOpenGroup(null)} style={{ ...tabStyle(false), flex: "0 0 44px" }} aria-label="Back">‹</button>
          {g.items.map((item) => (
            <button key={item.view} onClick={() => { onSelect(item.view); setOpenGroup(null); }} style={tabStyle(tab === item.view)}>
              {item.label}{item.badge && badges?.[item.badge] > 0 ? ` (${badges[item.badge]})` : ""}
            </button>
          ))}
        </>
      ) : mobileTopLevel().map((t) => {
        const isActive = t.group ? (t.group.view ? tab === t.group.view : currentGroup?.id === t.group.id) : tab === t.id;
        const n = t.group ? badgeFor(t.group, badges) : 0;
        return (
          <button key={t.id} style={tabStyle(isActive)}
                  onClick={() => { if (t.group?.items) setOpenGroup(t.id); else onSelect(t.group ? t.group.view : t.id); }}>
            {t.label}{t.group?.items ? " ▾" : ""}
            <Sup n={n} />
          </button>
        );
      })}
    </nav>
  );
}

export default function NavMenu({ mobile, view, tab, onSelect, badges }) {
  if (mobile) return <MobileBar tab={tab} onSelect={onSelect} badges={badges} />;
  return (
    <div style={{ display: "flex", alignItems: "baseline", justifyContent: "center", gap: "22px" }}>
      {NAV_GROUPS.map((g) => <DesktopGroup key={g.id} group={g} view={view} onSelect={onSelect} badges={badges} />)}
    </div>
  );
}
