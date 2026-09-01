// Single source of truth for the app's navigation. Desktop dropdowns and the
// mobile two-level tab bar both render from this (NavMenu.jsx); App.js uses
// WIDE_VIEWS for the layout collapse. Adding a tab = one entry here plus its
// render branch in App.js.
//
// Groups carry the framing: "Maritime" sits BESIDE "Military" under Security
// because coast guards are law-enforcement hulls, not warships — the coercion
// works precisely because it is below the military threshold (Ed, 2026-08-26).
import { READ_ONLY } from "./readOnly";

const ALL_GROUPS = [
  { id: "feed", label: "Feed", view: "feed" },
  { id: "security", label: "Security", items: [
    { view: "military", label: "Military" },
    { view: "maritime", label: "Maritime" },
  ] },
  { id: "economy", label: "Economy", items: [
    { view: "economy", label: "Indicators" },
    { view: "trade", label: "Trade Access" },
    { view: "people", label: "People" },
  ] },
  { id: "politics", label: "Politics", items: [
    { view: "polls", label: "Polls" },
    { view: "diplomacy", label: "Diplomacy" },
    { view: "visits", label: "Visits" },
    { view: "positions", label: "Positions", adminOnly: true },   // gated until the curated content is reviewed
  ] },
  { id: "admin", label: "Admin", adminOnly: true, items: [
    { view: "review", label: "Review", badge: "review" },
    { view: "altmodels", label: "Alt Models" },
  ] },
  { id: "about", label: "About", view: "about" },   // full page since the Morning Brief redesign (was a modal)
];

export const NAV_GROUPS = ALL_GROUPS
  .filter((g) => !g.adminOnly || !READ_ONLY)
  .map((g) => (g.items ? { ...g, items: g.items.filter((i) => !i.adminOnly || !READ_ONLY) } : g));

// Every non-feed view gets the single-column "document" layout (rails hidden).
export const WIDE_VIEWS = NAV_GROUPS.flatMap((g) =>
  g.items ? g.items.map((i) => i.view) : (g.view && g.view !== "feed" ? [g.view] : []));

export function groupForView(view) {
  return NAV_GROUPS.find((g) => g.view === view || g.items?.some((i) => i.view === view)) || null;
}

export function itemForView(view) {
  for (const g of NAV_GROUPS) {
    const hit = g.items?.find((i) => i.view === view);
    if (hit) return hit;
  }
  return null;
}
