import { useEffect, useRef, useState } from "react";
import {
  fetchEconomySeries,
  fetchTradeAccessSummary,
  fetchPeopleRecords,
  fetchMilitarySummary,
  fetchPollsByQuestion,
} from "../api";

// Rotating "stat spotlight" in the left sidebar. One slot cycles through a
// headline figure from each top-level section: Economy (trade balance) →
// Military (30-day ADIZ avg) → Polls (Taiwanese identity %) → Trade (PRC ECFA
// suspensions) → People (monthly visitor flow). Replaces the old static
// EconomyMini — the economy trade balance is still slide 0 so first paint is
// unchanged. Each slide picks the freshest meaningful figure its section has.
//
// Auto-advances slowly (AUTO_MS) with pause-on-hover/focus and pause-when-
// offscreen (handles the mobile display:none collapse). Honours
// prefers-reduced-motion (no auto-advance). Dots below allow manual stepping;
// the whole card is a click-through to that section's tab.

const AUTO_MS = 7000;
const HEADLINE_SERIES = "trade_balance_usd_b";
const TOTAL_SERIES = "trade_total_usd_b";

function formatUsdB(value) {
  if (value === null || value === undefined) return "—";
  const sign = value < 0 ? "−" : "";
  return `${sign}US$${Math.abs(value).toFixed(1)}B`;
}

function formatCount(value) {
  if (value === null || value === undefined) return "—";
  const n = Math.abs(value);
  if (n >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(value / 1_000).toFixed(0)}K`;
  return Math.round(value).toLocaleString("en-US");
}

function formatPeriodLabel(period) {
  // 'YYYY-MM' → 'MMM YY'; pass through anything else (e.g. 'YYYY').
  if (!period) return "";
  const parts = String(period).split("-");
  if (parts.length < 2) return period;
  const monthNames = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  const [y, m] = parts;
  return `${monthNames[Number(m) - 1]} ${y.slice(2)}`;
}

function DeltaChip({ pct }) {
  if (pct === null || pct === undefined) return null;
  const isPositive = pct > 0;
  const color = isPositive ? "var(--accent-green)" : "var(--accent-red)";
  const arrow = isPositive ? "▲" : "▼";
  const sign = isPositive ? "+" : "";
  return (
    <span style={{
      fontFamily: "var(--font-mono)",
      fontSize: "10px",
      color,
      letterSpacing: "0.04em",
    }}>
      {arrow} {sign}{pct.toFixed(1)}%
    </span>
  );
}

// ── Per-section slide builders. Each returns a slide object or null when its
//    data isn't ready, so a slow/empty section simply drops out of the rotation.

function economySlide(data) {
  if (!data?.series?.length) return null;
  const balance = data.series.find((s) => s.id === HEADLINE_SERIES);
  const total = data.series.find((s) => s.id === TOTAL_SERIES);
  if (!balance?.points?.length) return null;
  const latest = balance.points[balance.points.length - 1];
  const totalLatest = total?.points?.length ? total.points[total.points.length - 1] : null;
  return {
    key: "economy",
    view: "economy",
    eyebrow: "Cross-Strait Economy",
    label: `TW–PRC trade balance · ${formatPeriodLabel(latest.period)}`,
    value: formatUsdB(latest.value),
    deltaPct: latest.yoy_pct,
    subline: latest.value >= 0 ? "TW surplus with mainland China" : "TW deficit with mainland China",
    extra: totalLatest ? `Bilateral trade ${formatUsdB(totalLatest.value)}` : null,
  };
}

function militarySlide(summary) {
  if (!summary) return null;
  const avg = summary.avg_30d_intruded;
  if (avg === null || avg === undefined) return null;
  return {
    key: "military",
    view: "military",
    eyebrow: "PLA Activity",
    label: "PLA aircraft into ADIZ · 30-day daily avg",
    value: `${avg.toFixed(1)}/day`,
    deltaPct: summary.yoy_delta_pct,
    subline: `${summary.days_with_intrusions_mtd ?? 0} of ${summary.mtd_days_observed ?? 0} days this month saw incursions`,
    extra: null,
  };
}

function pollsSlide(byQuestion) {
  const waves = byQuestion?.waves;
  if (!waves?.length) return null;
  const latest = waves[waves.length - 1];
  const opts = latest?.options || [];
  // Match the "Taiwanese" identity bucket by label, not position.
  const tw = opts.find((o) => o.label_en === "Taiwanese")
          || opts.find((o) => (o.label_zh || "").includes("臺灣人") || (o.label_zh || "").includes("台灣人"));
  if (!tw || tw.percentage === null || tw.percentage === undefined) return null;
  return {
    key: "polls",
    view: "polls",
    eyebrow: "Cross-Strait Polls",
    label: `Taiwanese identity · ${formatPeriodLabel(latest.fielded_end || latest.fielded_start)}`,
    value: `${Number(tw.percentage).toFixed(1)}%`,
    deltaPct: null,
    subline: "identify as Taiwanese (not Chinese) · NCCU ESC",
    extra: null,
  };
}

function tradeSlide(summary) {
  // PRC's active economic lever on Taiwan is ECFA tariff-preference
  // suspension (a far larger count than outright bans), so headline that.
  const dir = summary?.by_direction?.prc_imports_from_tw;
  const suspended = dir?.ecfa_suspended;
  if (suspended === null || suspended === undefined) return null;
  return {
    key: "trade",
    view: "trade",
    eyebrow: "Trade Barriers",
    label: "TW export lines stripped of ECFA preference",
    value: formatCount(suspended),
    deltaPct: null,
    subline: "PRC tariff-preference suspensions on TW goods",
    extra: null,
  };
}

function peopleSlide(data) {
  // Visitor flow is the freshest people-side metric (monthly, with YoY) — the
  // spouse/permit stocks lag years behind. Lead with the dominant TW→PRC
  // direction; carry PRC→TW (with its own delta) in the subline so the paired
  // flow stays symmetric rather than cherry-picked.
  const out = data?.flows?.tw_visitors_to_prc?.latest;
  const inb = data?.flows?.prc_visitors_to_tw?.latest;
  if (!out || out.value === null || out.value === undefined) return null;
  const toPersons = (v) => formatCount(v * 10000); // unit is '10k persons'
  // Mirror the economy slide's grammar: subline = descriptor, extra = the
  // paired secondary figure (here the opposite-direction flow + its delta).
  let extra = null;
  if (inb && inb.value !== null && inb.value !== undefined) {
    const yoy = (inb.yoy_pct !== null && inb.yoy_pct !== undefined)
      ? ` (${inb.yoy_pct > 0 ? "+" : ""}${inb.yoy_pct.toFixed(1)}%)`
      : "";
    extra = `PRC→TW ${toPersons(inb.value)}/mo${yoy}`;
  }
  return {
    key: "people",
    view: "people",
    eyebrow: "Cross-Strait People",
    label: `TW visitors to the mainland · ${formatPeriodLabel(out.period)}`,
    value: `${toPersons(out.value)}/mo`,
    deltaPct: out.yoy_pct,
    subline: "monthly cross-strait visitor flow",
    extra,
  };
}

export default function StatSpotlight({ onOpen }) {
  const [slides, setSlides] = useState([]);
  const [active, setActive] = useState(0);
  const [paused, setPaused] = useState(false);
  const [visible, setVisible] = useState(true);
  const [cycleNonce, setCycleNonce] = useState(0); // bump to re-arm the timer
  const rootRef = useRef(null);

  // Fetch each section's headline data in parallel, assemble the ordered
  // slide list, drop any that aren't ready. Economy stays first.
  useEffect(() => {
    let cancelled = false;
    Promise.allSettled([
      fetchEconomySeries({ ids: [HEADLINE_SERIES, TOTAL_SERIES].join(","), months: 13 }),
      fetchMilitarySummary(),
      fetchPollsByQuestion("identity_nccu_3pt"),
      fetchTradeAccessSummary(),
      fetchPeopleRecords(),
    ]).then((res) => {
      if (cancelled) return;
      const val = (i) => (res[i].status === "fulfilled" ? res[i].value : null);
      const built = [
        economySlide(val(0)),
        militarySlide(val(1)),
        pollsSlide(val(2)),
        tradeSlide(val(3)),
        peopleSlide(val(4)),
      ].filter(Boolean);
      setSlides(built);
    });
    return () => { cancelled = true; };
  }, []);

  // Pause auto-rotation when the card is scrolled offscreen or collapsed
  // (mobile display:none → not intersecting).
  useEffect(() => {
    const el = rootRef.current;
    if (!el || typeof IntersectionObserver === "undefined") return;
    const io = new IntersectionObserver(
      ([entry]) => setVisible(entry.isIntersecting),
      { threshold: 0.1 }
    );
    io.observe(el);
    return () => io.disconnect();
  }, [slides.length]);

  // Auto-advance. Disabled for reduced-motion users and while paused/offscreen.
  useEffect(() => {
    if (slides.length <= 1) return;
    const reduced = typeof window !== "undefined"
      && window.matchMedia
      && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced || paused || !visible) return;
    const id = setInterval(() => {
      setActive((i) => (i + 1) % slides.length);
    }, AUTO_MS);
    return () => clearInterval(id);
  }, [slides.length, paused, visible, cycleNonce]);

  if (!slides.length) return null;
  const idx = Math.min(active, slides.length - 1);
  const slide = slides[idx];

  return (
    <div ref={rootRef} style={{ marginBottom: "28px" }}>
      <div style={{ marginBottom: "12px" }}>
        <div style={{ height: "2px", background: "var(--border-color)", marginBottom: "8px" }} />
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
          <span style={{
            fontFamily: "var(--font-mono)",
            fontSize: "10px",
            fontWeight: 600,
            letterSpacing: "0.14em",
            textTransform: "uppercase",
            color: "var(--text-primary)",
          }}>
            {slide.eyebrow}
          </span>
          <button
            onClick={() => onOpen(slide.view)}
            style={{
              background: "transparent",
              border: "none",
              fontFamily: "var(--font-mono)",
              fontSize: "9px",
              color: "var(--text-muted)",
              letterSpacing: "0.08em",
              textTransform: "uppercase",
              cursor: "pointer",
              padding: 0,
            }}
            title="Open section"
          >
            More →
          </button>
        </div>
      </div>

      <button
        onClick={() => onOpen(slide.view)}
        onMouseEnter={() => setPaused(true)}
        onMouseLeave={() => setPaused(false)}
        onFocus={() => setPaused(true)}
        onBlur={() => setPaused(false)}
        style={{
          width: "100%",
          background: "var(--bg-card)",
          border: "1px solid var(--border-color)",
          padding: "12px 14px",
          cursor: "pointer",
          textAlign: "left",
          display: "flex",
          flexDirection: "column",
          gap: "10px",
        }}
      >
        <div>
          <div style={{
            fontFamily: "var(--font-mono)",
            fontSize: "9px",
            letterSpacing: "0.1em",
            textTransform: "uppercase",
            color: "var(--text-muted)",
          }}>
            {slide.label}
          </div>
          <div style={{
            display: "flex",
            alignItems: "baseline",
            justifyContent: "space-between",
            marginTop: "2px",
          }}>
            <span style={{
              fontFamily: "var(--font-headline)",
              fontSize: "22px",
              color: "var(--text-primary)",
              lineHeight: 1,
            }}>
              {slide.value}
            </span>
            <DeltaChip pct={slide.deltaPct} />
          </div>
          <div style={{
            fontFamily: "var(--font-mono)",
            fontSize: "9px",
            color: "var(--text-muted)",
            marginTop: "3px",
            fontStyle: "italic",
          }}>
            {slide.subline}
          </div>
        </div>

        {slide.extra && (
          <div style={{
            fontFamily: "var(--font-mono)",
            fontSize: "10px",
            color: "var(--text-secondary)",
          }}>
            {slide.extra}
          </div>
        )}
      </button>

      {/* Dot nav — manual step; re-arms the auto timer. */}
      {slides.length > 1 && (
        <div style={{
          display: "flex",
          gap: "6px",
          justifyContent: "center",
          marginTop: "10px",
        }}>
          {slides.map((s, i) => (
            <button
              key={s.key}
              onClick={() => { setActive(i); setCycleNonce((n) => n + 1); }}
              aria-label={`Show ${s.eyebrow}`}
              title={s.eyebrow}
              style={{
                width: i === idx ? "18px" : "6px",
                height: "6px",
                borderRadius: "3px",
                border: "none",
                padding: 0,
                cursor: "pointer",
                background: i === idx ? "var(--text-secondary)" : "var(--border-color)",
                transition: "width 0.2s ease",
              }}
            />
          ))}
        </div>
      )}
    </div>
  );
}
