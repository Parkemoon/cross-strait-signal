import { useState } from "react";
import { READ_ONLY } from "./readOnly";
import { useWindowWidth } from "./hooks/useWindowWidth";
import { useDashboardData } from "./hooks/useDashboardData";
import ThemeToggle from "./components/ThemeToggle";
import MastheadCoasts from "./components/MastheadCoasts";
import AboutTab from "./components/AboutTab";
import FlashTraffic from "./components/FlashTraffic";
import KeyFigures from "./components/KeyFigures";
import SocialPulse from "./components/SocialPulse";
import ArticleCard from "./components/ArticleCard";
import StatsSidebar from "./components/StatsSidebar";
import FilterBar from "./components/FilterBar";
import ReviewQueue from "./components/ReviewQueue";
import EconomyTab from "./components/EconomyTab";
import TradeAccessTab from "./components/TradeAccessTab";
import PeopleTab from "./components/PeopleTab";
import MilitaryTab from "./components/MilitaryTab";
import MaritimeTab from "./components/MaritimeTab";
import PollsTab from "./components/PollsTab";
import DiplomacyTab from "./components/DiplomacyTab";
import VisitsTab from "./components/VisitsTab";
import PositionsTab from "./components/PositionsTab";
import AltModelsTab from "./components/AltModelsTab";
import AltModelLens from "./components/AltModelLens";
import NavMenu from "./components/NavMenu";
import { WIDE_VIEWS } from "./navGroups";
import { bandColour } from "./sentimentBand";

function fmtScore(score) {
  if (score == null) return "—";
  const v = score.toFixed(2).replace("-", "−");
  return score > 0 ? `+${v}` : v;
}

const TICKER_TEXT = {
  fontFamily: "var(--font-mono)",
  fontSize: "9.5px",
  letterSpacing: "0.08em",
  color: "var(--muted)",
};

export default function App() {
  const [filters, setFilters] = useState({});
  const [page, setPage] = useState(1);
  // Admin-only feed lens: null = production Gemini, {model, arm} = view the
  // feed through that alt-model sweep (swept articles only).
  const [altLens, setAltLens] = useState(null);
  // Lens display mode: false = alt output replaces production, true = dual
  // (both side by side). Display-only — same fetch either way, so it lives
  // outside altLens to avoid a pointless refetch on toggle.
  const [altDual, setAltDual] = useState(false);
  const [view, setView] = useState("feed"); // "feed" | any view in navGroups.js (WIDE_VIEWS)
  const [mobileTab, setMobileTab] = useState("feed"); // "feed" | "stats" | "social" | any view in navGroups.js
  const windowWidth = useWindowWidth();
  const isMobile = windowWidth < 768;
  const showCoasts = windowWidth >= 1000;  // masthead coast flanks need room beside the corner stamps

  const {
    articles, total, loading, stats,
    reviewPending, pendingApproval, setPendingApproval,
  } = useDashboardData(filters, page, READ_ONLY ? null : altLens);

  const isSection = WIDE_VIEWS.includes(view);
  const byPlace = {};
  (stats?.sentiment_by_place ?? []).forEach((r) => { byPlace[r.place] = r.avg_score; });

  const dateStr = new Date().toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" }).toUpperCase();

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg)" }}>
      {/* ============ Masthead — centred nameplate, briefing-document ============ */}
      {!isMobile ? (
        <header>
          <div style={{ textAlign: "center", padding: "26px 24px 0", position: "relative", maxWidth: "1440px", margin: "0 auto" }}>
            {/* abs left: date stamp */}
            <div style={{ position: "absolute", left: "24px", top: "26px", textAlign: "left",
                          fontFamily: "var(--font-mono)", fontSize: "9px", color: "var(--faint)",
                          letterSpacing: "0.12em", lineHeight: 1.6 }}>
              {dateStr}
            </div>
            {/* abs right: live dot · pending (admin) · theme */}
            <div style={{ position: "absolute", right: "24px", top: "26px", display: "flex", gap: "10px",
                          alignItems: "center", fontFamily: "var(--font-mono)", fontSize: "9px",
                          color: "var(--faint)", letterSpacing: "0.12em" }}>
              {!READ_ONLY && pendingApproval > 0 && (
                <span style={{ color: "var(--flag)" }}>{pendingApproval} PENDING</span>
              )}
              <span style={{ display: "flex", alignItems: "center", gap: "4px" }}>
                <span style={{ width: "5px", height: "5px", borderRadius: "50%", background: "var(--cyan)",
                               animation: "csspulse 2.4s infinite" }} />
                MONITORING
              </span>
              <ThemeToggle />
            </div>
            {/* eyebrow — margins guard collision with the absolute corners */}
            <div style={{ fontFamily: "var(--font-mono)", fontSize: "8.5px", letterSpacing: "0.22em",
                          color: "var(--faint)", margin: "0 170px 8px" }}>
              BILINGUAL · ANALYST-GATED · OPEN SOURCE
            </div>
            {/* nameplate — flanked by the two sides of the strait (west coast +
                Kinmen/Matsu left, Taiwan + Penghu right; the nameplate is the
                strait). Flanks hide below 1000px so they never meet the corner
                stamps. */}
            <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: "26px", margin: "0 160px" }}>
              {showCoasts && <MastheadCoasts side="west" height={92} />}
              <h1 onClick={() => setView("feed")}
                  style={{ fontFamily: "var(--font-headline)", fontSize: "40px", fontWeight: 500,
                           lineHeight: 1, letterSpacing: "0.01em", cursor: "pointer", margin: 0,
                           color: "var(--ink)" }}>
                Cross-Strait Signal
              </h1>
              {showCoasts && <MastheadCoasts side="east" height={92} />}
            </div>
            <div style={{ width: "64px", height: "1px", background: "var(--ink)", margin: "14px auto 10px" }} />
            {/* nav row */}
            <div style={{ paddingBottom: "12px" }}>
              <NavMenu view={view} onSelect={setView} badges={{ review: reviewPending }} />
            </div>
            {/* double rule — the signature; used only here and above the footer */}
            <div style={{ borderTop: "3px double var(--ink)", margin: "0 -24px" }} />
            {/* ticker */}
            <div style={{ display: "flex", justifyContent: "center", flexWrap: "wrap", gap: "8px 26px",
                          padding: "7px 0", borderBottom: "1px solid var(--hair)", margin: "0 -24px", ...TICKER_TEXT }}>
              <span>CONTINUOUS MONITOR · {(stats?.total_articles ?? total ?? 0).toLocaleString()} ARTICLES REVIEWED</span>
              <span>·</span>
              <span>{stats?.escalation_signals?.length || 0} ACTIVE SIGNALS</span>
              <span>·</span>
              <span>OVERALL <b style={{ color: bandColour(stats?.avg_sentiment_score), fontWeight: 600 }}>{fmtScore(stats?.avg_sentiment_score)}</b></span>
              <span>·</span>
              <span>
                PRC <b style={{ color: bandColour(byPlace.PRC), fontWeight: 600 }}>{fmtScore(byPlace.PRC)}</b>
                {" / "}
                TW <b style={{ color: bandColour(byPlace.TW), fontWeight: 600 }}>{fmtScore(byPlace.TW)}</b>
              </span>
            </div>
          </div>
        </header>
      ) : (
        /* ============ Mobile header — compact nameplate ============ */
        <header style={{ textAlign: "center", padding: "14px 16px 10px", position: "relative" }}>
          <div style={{ position: "absolute", right: "12px", top: "12px", display: "flex", gap: "6px", alignItems: "center" }}>
            <button onClick={() => { setView("about"); setMobileTab("about"); }}
                    style={{ background: "none", border: "1px solid var(--hair)", width: "24px", height: "24px",
                             cursor: "pointer", fontSize: "12px", color: "var(--faint)", padding: 0 }}
                    title="About">i</button>
            <ThemeToggle />
          </div>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: "7.5px", letterSpacing: "0.2em",
                        color: "var(--faint)", marginBottom: "4px" }}>
            BILINGUAL · ANALYST-GATED · OPEN SOURCE
          </div>
          <h1 onClick={() => { setView("feed"); setMobileTab("feed"); }}
              style={{ fontFamily: "var(--font-headline)", fontSize: "24px", fontWeight: 500, lineHeight: 1,
                       letterSpacing: "0.01em", color: "var(--ink)", margin: "0 40px" }}>
            Cross-Strait Signal
          </h1>
        </header>
      )}

      {/* Tab bar — mobile only (groups from navGroups.js; Stats/Social are mobile-only panels) */}
      {isMobile && (
        <NavMenu mobile tab={mobileTab} badges={{ review: reviewPending }}
                 onSelect={(id) => {
                   setMobileTab(id);
                   // feed/stats/social all share the "feed" view on mobile; every other tab is a view id.
                   setView(["feed", "stats", "social"].includes(id) ? "feed" : id);
                 }} />
      )}

      {/* ============ Main layout ============
          Feed: twin 280px rails around a centred reading column (the
          "monitor"). Section views: single column, no rails (the
          "document") — the monitor/document contrast is deliberate.
          Mobile keeps the tab-controlled single column.
          NB: do NOT add `overflow: hidden` to the grid — it breaks
          `position: sticky` on the rail children. */}
      <div style={{
        display: isMobile ? "block" : (isSection ? "block" : "grid"),
        gridTemplateColumns: isSection ? undefined : "280px minmax(0, 1fr) 280px",
        maxWidth: "1440px",
        margin: "0 auto",
        minHeight: "calc(100vh - 160px)",
        alignItems: "start",
      }}>
        {/* Left rail — alignment legend, gauges, trend, topics, sources,
            entities. Hidden on section views (desktop); mobile Stats tab. */}
        <aside
          className={isMobile ? "" : "hide-scrollbar"}
          style={{
            background: "var(--bg)",
            borderRight: isMobile ? "none" : "1px solid var(--hair)",
            padding: "20px 18px",
            position: isMobile ? "static" : "sticky",
            top: 0,
            alignSelf: "start",
            maxHeight: isMobile ? "none" : "100vh",
            overflowY: isMobile ? "visible" : "auto",
            minWidth: 0,
            display: isMobile
              ? (mobileTab === "stats" ? "block" : "none")
              : (isSection ? "none" : "block"),
          }}
        >
          <StatsSidebar
            stats={stats}
            filters={filters}
            altDual={altDual}
            onTopicClick={(topic) => { setFilters((f) => ({ ...f, topic })); setPage(1); }}
            onPlaceClick={(place) => {
              setFilters((f) => {
                const next = { ...f };
                if (place) { next.source_place = place; } else { delete next.source_place; }
                return next;
              });
              setPage(1);
            }}
            onSourceClick={(dbPrefix) => { setFilters((f) => ({ ...f, source_name: dbPrefix })); setPage(1); }}
            onEntityClick={(entityName) => { setFilters((f) => ({ ...f, entity: entityName, search: undefined })); setPage(1); }}
            onBiasClick={(bias) => { setFilters((f) => ({ ...f, bias })); setPage(1); }}
            onOpenTab={(nextView) => {
              setView(nextView);
              if (isMobile) setMobileTab(nextView);
            }}
            onClearScopingFilters={() => {
              setFilters((f) => {
                const next = { ...f };
                delete next.topic;
                delete next.source_place;
                delete next.source_name;
                delete next.bias;
                delete next.urgency;
                delete next.escalation_only;
                delete next.entity;
                return next;
              });
              setPage(1);
            }}
          />
        </aside>

        {/* Feed / Review / section tabs — center column */}
        <div style={{ display: isMobile ? ((mobileTab === "feed" || WIDE_VIEWS.includes(mobileTab)) ? "block" : "none") : "block", minWidth: 0 }}>
          {!READ_ONLY && view === "review" ? (
            <div style={{ maxWidth: "960px", margin: "0 auto", minWidth: 0 }}>
              <ReviewQueue onClose={() => setView("feed")} />
            </div>
          ) : isSection && view !== "review" ? (
            <div style={{ maxWidth: "1100px", margin: "0 auto", minWidth: 0 }}>
              {view === "economy" ? <EconomyTab />
                : view === "trade" ? <TradeAccessTab />
                : view === "people" ? <PeopleTab />
                : view === "military" ? <MilitaryTab />
                : view === "maritime" ? <MaritimeTab />
                : view === "polls" ? <PollsTab />
                : view === "diplomacy" ? <DiplomacyTab />
                : view === "visits" ? <VisitsTab />
                : !READ_ONLY && view === "positions" ? <PositionsTab onOpenTab={setView} />
                : view === "about" ? <AboutTab />
                : !READ_ONLY && view === "altmodels" ? (
                  <main style={{ padding: isMobile ? "16px" : "28px 32px", minWidth: 0 }}>
                    <AltModelsTab />
                  </main>
                ) : null}
            </div>
          ) : (
            <main style={{
              padding: isMobile ? "16px" : "24px 48px 40px",
              minWidth: 0,
              maxWidth: isMobile ? "none" : "820px",
              margin: "0 auto",
              overflow: "hidden",
            }}>
                {/* Priority Signals */}
                <FlashTraffic
                  escalations={stats?.escalation_signals}
                  onTopicClick={(topic) => { setFilters((f) => ({ ...f, topic })); setPage(1); }}
                  onEntityClick={(entityName) => { setFilters((f) => ({ ...f, entity: entityName, search: undefined })); setPage(1); }}
                  onApprove={() => setPendingApproval((n) => Math.max(0, n - 1))}
                />

                <KeyFigures />

                {/* Section rule — THE FEED */}
                <div style={{ display: "flex", alignItems: "baseline", gap: "10px", marginBottom: "6px" }}>
                  <span style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: "9.5px",
                    fontWeight: 600,
                    letterSpacing: "0.24em",
                    textTransform: "uppercase",
                    color: "var(--ink)",
                  }}>
                    The Feed
                  </span>
                  <span style={{ flex: 1, borderBottom: "1px solid var(--hair)" }} />
                  <span style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: "9px",
                    color: "var(--pale)",
                    letterSpacing: "0.08em",
                  }}>
                    {total} RESULTS
                  </span>
                </div>

                {/* Model lens — admin-only feed re-render through an alt-model sweep */}
                {!READ_ONLY && (
                  <AltModelLens
                    lens={altLens}
                    onChange={(l) => { setAltLens(l); setPage(1); }}
                    dual={altDual}
                    onDualChange={setAltDual}
                  />
                )}

                {/* Filters */}
                <FilterBar
                  filters={filters}
                  // Reset to page 1 on any filter change — otherwise a filter
                  // applied while on page N requests page N of the new (smaller)
                  // result set and shows "no results" despite matches. Mirrors
                  // what every sidebar filter callback already does.
                  setFilters={(updater) => {
                    setFilters(updater);
                    setPage(1);
                  }}
                  topEntities={stats?.top_entities}
                />

                {/* Article feed */}
                {loading ? (
                  <p
                    style={{
                      color: "var(--muted)",
                      fontFamily: "var(--font-mono)",
                      fontSize: "11px",
                      letterSpacing: "0.08em",
                      padding: "40px 0",
                    }}
                  >
                    LOADING…
                  </p>
                ) : articles.length === 0 ? (
                  <p
                    style={{
                      color: "var(--muted)",
                      fontFamily: "var(--font-body)",
                      fontSize: "13px",
                      padding: "40px 0",
                    }}
                  >
                    {altLens && !READ_ONLY
                      ? "No swept articles match these filters — the model lens only shows articles the sweep covered."
                      : "No articles match these filters."}
                  </p>
                ) : (
                  <>
                    {articles.map((article) => (
                      <ArticleCard
                        key={article.id}
                        article={article}
                        altLens={READ_ONLY ? null : altLens}
                        altDual={altDual}
                        onTopicClick={(topic) => {
                          setFilters((f) => ({ ...f, topic }));
                          setPage(1);
                        }}
                        onEntityClick={(entityName) => {
                          setFilters((f) => ({ ...f, entity: entityName, search: undefined }));
                          setPage(1);
                        }}
                        onApprove={() => setPendingApproval((n) => Math.max(0, n - 1))}
                      />
                    ))}

                    {/* Pagination — typographic, no buttons-as-boxes */}
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "center",
                        alignItems: "baseline",
                        gap: "10px",
                        marginTop: "24px",
                        paddingBottom: isMobile ? "24px" : "40px",
                        fontFamily: "var(--font-mono)",
                        fontSize: "10px",
                        letterSpacing: "0.1em",
                      }}
                    >
                      <button
                        onClick={() => setPage((p) => Math.max(1, p - 1))}
                        disabled={page <= 1}
                        style={{
                          background: "none",
                          border: "none",
                          fontFamily: "inherit",
                          fontSize: "inherit",
                          letterSpacing: "inherit",
                          color: page <= 1 ? "var(--pale)" : "var(--muted)",
                          cursor: page <= 1 ? "default" : "pointer",
                        }}
                      >
                        ← PREVIOUS
                      </button>
                      <span style={{ color: "var(--pale)" }}>·</span>
                      <span style={{ color: "var(--faint)" }}>PAGE {page}</span>
                      <span style={{ color: "var(--pale)" }}>·</span>
                      <button
                        onClick={() => setPage((p) => p + 1)}
                        disabled={articles.length < 20}
                        style={{
                          background: "none",
                          border: "none",
                          fontFamily: "inherit",
                          fontSize: "inherit",
                          letterSpacing: "inherit",
                          color: articles.length < 20 ? "var(--pale)" : "var(--muted)",
                          cursor: articles.length < 20 ? "default" : "pointer",
                        }}
                      >
                        NEXT →
                      </button>
                    </div>
                  </>
                )}

                {/* Social Pulse — mobile only, below articles */}
                {isMobile && (
                  <div style={{
                    borderTop: "1px solid var(--hair)",
                    paddingTop: "16px",
                    marginTop: "8px",
                    paddingBottom: "40px",
                  }}>
                    <SocialPulse />
                  </div>
                )}
              </main>
          )}
        </div>

        {/* Social Pulse — right rail, desktop feed only. Same sticky-top +
            internal-scroll pattern as the left rail. */}
        <aside
          className="hide-scrollbar"
          style={{
            background: "var(--bg)",
            borderLeft: "1px solid var(--hair)",
            padding: "20px 18px",
            position: "sticky",
            top: 0,
            alignSelf: "start",
            maxHeight: "100vh",
            overflowY: "auto",
            minWidth: 0,
            display: isSection
              ? "none"
              : (isMobile ? (mobileTab === "social" ? "block" : "none") : "block"),
          }}
        >
          <SocialPulse column />
        </aside>
      </div>


      {/* Footer — desktop only; the second and last permitted double rule */}
      <footer
        style={{
          borderTop: "3px double var(--ink)",
          padding: "10px 24px",
          display: isMobile ? "none" : "flex",
          justifyContent: "space-between",
          fontFamily: "var(--font-mono)",
          fontSize: "9px",
          letterSpacing: "0.1em",
          color: "var(--faint)",
          background: "var(--bg)",
          maxWidth: "1440px",
          margin: "0 auto",
        }}
      >
        <span>CROSS-STRAIT SIGNAL · ED MOON</span>
        <span>{(stats?.total_articles || 0).toLocaleString()} ARTICLES PROCESSED</span>
      </footer>
    </div>
  );
}
