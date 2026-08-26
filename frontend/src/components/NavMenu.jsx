import { useEffect, useRef, useState } from "react";
import { NAV_GROUPS, groupForView, itemForView } from "../navGroups";

// Header navigation, rendered from NAV_GROUPS.
//   <NavMenu view=… onSelect={setView} badges={{review: n}} />            desktop
//   <NavMenu mobile tab=… onSelect={selectMobileTab} badges=… />          mobile
// Desktop: one button per group; groups with items open a dropdown on hover
// or click. Clicking the group label of the CURRENT view returns to the feed
// (the toggle behaviour the old flat buttons had). The active sub-view shows
// as a small caption under the group label so the header still says where
// you are. Mobile: a sticky bar of groups (+ Stats / Social, which only exist
// as tabs there); tapping a group swaps the bar for its items with a ‹ back.

const MONO = { fontFamily: "var(--font-mono)", textTransform: "uppercase", letterSpacing: "0.1em" };

function Badge({ n }) {
  if (!n) return null;
  return (
    <span style={{ position: "absolute", top: "-5px", right: "-5px", background: "#e67e22", color: "#fff",
                   borderRadius: "50%", width: "14px", height: "14px", fontSize: "9px", display: "flex",
                   alignItems: "center", justifyContent: "center", fontFamily: "var(--font-mono)" }}>{n}</span>
  );
}

function badgeFor(group, badges) {
  return (group.items || []).reduce((s, i) => s + (i.badge ? badges?.[i.badge] || 0 : 0), 0);
}

function DesktopGroup({ group, view, onSelect, badges }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const active = groupForView(view)?.id === group.id && view !== "feed";
  const activeItem = active ? itemForView(view) : null;
  const badge = badgeFor(group, badges);

  useEffect(() => {
    if (!open) return undefined;
    const close = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    const esc = (e) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", close); document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", esc); };
  }, [open]);

  const btnStyle = (isActive) => ({
    ...MONO, padding: "4px 12px", fontSize: "10px", cursor: "pointer", position: "relative", lineHeight: 1.3,
    background: isActive ? "rgba(255,255,255,0.12)" : "transparent",
    color: isActive ? "var(--header-text)" : "rgba(255,255,255,0.45)",
    border: "1px solid rgba(255,255,255,0.14)",
  });

  if (!group.items) {
    return <button onClick={() => onSelect(group.view)} style={btnStyle(view === group.view)}>{group.label}</button>;
  }
  return (
    <div ref={ref} style={{ position: "relative" }} onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
      <button onClick={() => { if (active) { onSelect("feed"); setOpen(false); } else setOpen((o) => !o); }}
              aria-haspopup="menu" aria-expanded={open} style={btnStyle(active)}>
        {group.label} <span style={{ opacity: 0.6, fontSize: "8px" }}>▾</span>
        {activeItem && (
          <span style={{ display: "block", fontSize: "8px", letterSpacing: "0.08em", opacity: 0.7, marginTop: "1px" }}>
            {activeItem.label}
          </span>
        )}
        <Badge n={badge} />
      </button>
      {open && (
        <div role="menu" style={{ position: "absolute", top: "100%", left: 0, zIndex: 300, minWidth: "150px", paddingTop: "4px" }}>
          <div style={{ background: "var(--header-bg)", border: "1px solid rgba(255,255,255,0.18)", boxShadow: "0 8px 20px rgba(0,0,0,0.35)" }}>
            {group.items.map((item) => {
              const isActive = view === item.view;
              const n = item.badge ? badges?.[item.badge] || 0 : 0;
              return (
                <button key={item.view} role="menuitem" onClick={() => { onSelect(item.view); setOpen(false); }}
                        style={{ ...MONO, display: "flex", justifyContent: "space-between", alignItems: "center", gap: "10px",
                                 width: "100%", textAlign: "left", padding: "8px 12px", fontSize: "10px", cursor: "pointer",
                                 background: isActive ? "rgba(255,255,255,0.12)" : "transparent",
                                 color: isActive ? "var(--header-text)" : "rgba(255,255,255,0.6)",
                                 border: "none", borderBottom: "1px solid rgba(255,255,255,0.07)" }}>
                  <span>{item.label}</span>
                  {n > 0 && <span style={{ color: "#e67e22" }}>{n}</span>}
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
    ...MONO, flex: "1 0 auto", padding: "14px 10px", whiteSpace: "nowrap", background: "transparent", cursor: "pointer", fontSize: "11px", letterSpacing: "1px",
    color: isActive ? "var(--header-text)" : "rgba(255,255,255,0.4)", border: "none", position: "relative",
    borderBottom: isActive ? "2px solid var(--accent)" : "2px solid transparent",
  });
  const g = openGroup ? NAV_GROUPS.find((x) => x.id === openGroup) : null;
  const currentGroup = groupForView(tab);
  return (
    <nav className="hide-scrollbar"
         style={{ position: "sticky", top: 0, background: "var(--header-bg)", borderBottom: "1px solid rgba(255,255,255,0.1)",
                  display: "flex", zIndex: 100, overflowX: "auto" }}>
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
            <Badge n={n} />
          </button>
        );
      })}
    </nav>
  );
}

export default function NavMenu({ mobile, view, tab, onSelect, badges }) {
  if (mobile) return <MobileBar tab={tab} onSelect={onSelect} badges={badges} />;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
      {NAV_GROUPS.map((g) => <DesktopGroup key={g.id} group={g} view={view} onSelect={onSelect} badges={badges} />)}
    </div>
  );
}
