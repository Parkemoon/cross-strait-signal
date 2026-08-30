import { useState } from "react";
import { READ_ONLY } from "./readOnly";
import { useWindowWidth } from "./hooks/useWindowWidth";
import { useDashboardData } from "./hooks/useDashboardData";
import ThemeToggle from "./components/ThemeToggle";
import AboutModal from "./components/AboutModal";
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
  const [showAbout, setShowAbout] = useState(false);
  const [mobileTab, setMobileTab] = useState("feed"); // "feed" | "stats" | "social" | any view in navGroups.js
  const windowWidth = useWindowWidth();
  const isMobile = windowWidth < 768;

  const {
    articles, total, loading, stats,
    reviewPending, pendingApproval, setPendingApproval,
  } = useDashboardData(filters, page, READ_ONLY ? null : altLens);

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg-primary)" }}>
      {/* Header — masthead layout */}
      <header
        style={{
          background: "var(--header-bg)",
          color: "var(--header-text)",
          display: "flex",
          alignItems: "stretch",
          borderBottom: "1px solid rgba(255,255,255,0.07)",
        }}
      >
        {/* Masthead block */}
        <div style={{
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          padding: isMobile ? "12px 16px" : "12px 28px",
          borderRight: isMobile ? "none" : "1px solid rgba(255,255,255,0.08)",
        }}>
          <h1 style={{
            fontFamily: "var(--font-headline)",
            fontSize: isMobile ? "18px" : "20px",
            fontWeight: 400,
            letterSpacing: "0.01em",
            lineHeight: 1,
          }}>
            Cross-Strait Signal
          </h1>
          {!isMobile && (
            <span style={{
              fontFamily: "var(--font-mono)",
              fontSize: "9px",
              letterSpacing: "0.18em",
              textTransform: "uppercase",
              opacity: 0.35,
              marginTop: "5px",
            }}>
              PRC · Taiwan · Open-Source Intelligence
            </span>
          )}
        </div>

        {/* Centre strip — stats + pending */}
        {!isMobile && (
          <div style={{
            flex: 1,
            display: "flex",
            alignItems: "center",
            padding: "0 24px",
            gap: "20px",
          }}>
            <span style={{
              fontFamily: "var(--font-mono)",
              fontSize: "10px",
              opacity: 0.38,
              letterSpacing: "0.06em",
            }}>
              {total} articles · {stats?.escalation_signals?.length || 0} signals
            </span>
            {!READ_ONLY && pendingApproval > 0 && (
              <span style={{
                fontSize: "10px",
                fontFamily: "var(--font-mono)",
                color: "#f59e0b",
                background: "rgba(245,158,11,0.1)",
                border: "1px solid rgba(245,158,11,0.25)",
                padding: "3px 8px",
                letterSpacing: "0.06em",
              }}>
                {pendingApproval} pending
              </span>
            )}
          </div>
        )}

        {/* Controls */}
        <div style={{ display: "flex", alignItems: "center", gap: "8px", padding: isMobile ? "0 16px" : "0 20px" }}>
          {!isMobile && <NavMenu view={view} onSelect={setView} badges={{ review: reviewPending }} />}
          {!isMobile && (
            <button
              onClick={() => setShowAbout(true)}
              style={{
                background: "none",
                border: "none",
                cursor: "pointer",
                fontSize: "10px",
                fontFamily: "var(--font-mono)",
                color: "rgba(255,255,255,0.35)",
                textTransform: "uppercase",
                letterSpacing: "0.1em",
                padding: "5px 8px",
              }}
            >
              About
            </button>
          )}
          {isMobile && (
            <button
              onClick={() => setShowAbout(true)}
              style={{
                background: "none",
                border: "1px solid rgba(255,255,255,0.2)",
                borderRadius: "50%",
                width: "28px",
                height: "28px",
                cursor: "pointer",
                fontSize: "13px",
                color: "var(--header-text)",
                opacity: 0.7,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                padding: 0,
                flexShrink: 0,
              }}
              title="About"
            >
              i
            </button>
          )}
          <ThemeToggle />
        </div>
      </header>

      {/* Tab bar — mobile only (groups from navGroups.js; Stats/Social are mobile-only panels) */}
      {isMobile && (
        <NavMenu mobile tab={mobileTab} badges={{ review: reviewPending }}
                 onSelect={(id) => {
                   setMobileTab(id);
                   // feed/stats/social all share the "feed" view on mobile; every other tab is a view id.
                   setView(["feed", "stats", "social"].includes(id) ? "feed" : id);
                 }} />
      )}

      {/* Main layout — collapses to 2 columns on every section tab
          (WIDE_VIEWS) so the wide tables and charts get the full width.
          NB: do NOT add `overflow: hidden` here — it breaks
          `position: sticky` on the sidebar children. */}
      <div style={{
        display: isMobile ? "block" : "grid",
        gridTemplateColumns: WIDE_VIEWS.includes(view)
          ? "clamp(300px, 20vw, 420px) 1fr"
          : "clamp(300px, 20vw, 420px) 1fr 300px",
        minHeight: "calc(100vh - 52px)",
        alignItems: "start",
      }}>
        {/* Stats sidebar — always visible on desktop, tab-controlled on
            mobile. Sticky-top so it stays at viewport top throughout the
            feed scroll; max-height + overflow-y:auto give it independent
            scroll when the user hovers and wheels. hide-scrollbar keeps
            the visible track suppressed. */}
        <aside
          className={isMobile ? "" : "hide-scrollbar"}
          style={{
            background: "var(--sidebar-bg)",
            borderRight: isMobile ? "none" : "1px solid var(--border-color)",
            padding: "24px 20px",
            position: isMobile ? "static" : "sticky",
            top: 0,
            alignSelf: "start",
            maxHeight: isMobile ? "none" : "calc(100vh - 52px)",
            overflowY: isMobile ? "visible" : "auto",
            minWidth: 0,
            display: isMobile ? (mobileTab === "stats" ? "block" : "none") : "block",
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
            <ReviewQueue onClose={() => setView("feed")} />
          ) : view === "economy" ? (
            <EconomyTab />
          ) : view === "trade" ? (
            <TradeAccessTab />
          ) : view === "people" ? (
            <PeopleTab />
          ) : view === "military" ? (
            <MilitaryTab />
          ) : view === "maritime" ? (
            <MaritimeTab />
          ) : view === "polls" ? (
            <PollsTab />
          ) : view === "diplomacy" ? (
            <DiplomacyTab />
          ) : view === "visits" ? (
            <VisitsTab />
          ) : !READ_ONLY && view === "positions" ? (
            <PositionsTab onOpenTab={setView} />
          ) : !READ_ONLY && view === "altmodels" ? (
            <main style={{ padding: isMobile ? "16px" : "28px 32px", minWidth: 0 }}>
              <AltModelsTab />
            </main>
          ) : (
            <main style={{
              padding: isMobile ? "16px" : "28px 32px",
              minWidth: 0,
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

                {/* Section header */}
                <div style={{ marginBottom: "20px" }}>
                  <div style={{ height: "2px", background: "var(--border-color)", marginBottom: "9px" }} />
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                    <span style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: "11px",
                      fontWeight: 600,
                      letterSpacing: "0.14em",
                      textTransform: "uppercase",
                      color: "var(--text-primary)",
                    }}>
                      Signal Feed
                    </span>
                    <span style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: "10px",
                      color: "var(--text-muted)",
                    }}>
                      {total} results
                    </span>
                  </div>
                  <div style={{ height: "1px", background: "var(--border-color)", marginTop: "9px" }} />
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
                      color: "var(--text-muted)",
                      fontFamily: "var(--font-mono)",
                      fontSize: "13px",
                      padding: "40px 0",
                    }}
                  >
                    Loading...
                  </p>
                ) : articles.length === 0 ? (
                  <p
                    style={{
                      color: "var(--text-muted)",
                      fontFamily: "var(--font-mono)",
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

                    {/* Pagination */}
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "center",
                        gap: "12px",
                        marginTop: "24px",
                        paddingBottom: isMobile ? "24px" : "40px",
                      }}
                    >
                      <button
                        onClick={() => setPage((p) => Math.max(1, p - 1))}
                        disabled={page <= 1}
                        style={{
                          padding: "8px 20px",
                          background: "var(--bg-card)",
                          color: page <= 1 ? "var(--text-muted)" : "var(--text-secondary)",
                          border: "1px solid var(--border-color)",
                          cursor: page <= 1 ? "not-allowed" : "pointer",
                          fontSize: "13px",
                          fontFamily: "var(--font-body)",
                        }}
                      >
                        ← Previous
                      </button>
                      <span
                        style={{
                          padding: "8px 0",
                          fontSize: "12px",
                          color: "var(--text-muted)",
                          fontFamily: "var(--font-mono)",
                        }}
                      >
                        Page {page}
                      </span>
                      <button
                        onClick={() => setPage((p) => p + 1)}
                        disabled={articles.length < 20}
                        style={{
                          padding: "8px 20px",
                          background: "var(--bg-card)",
                          color: articles.length < 20 ? "var(--text-muted)" : "var(--text-secondary)",
                          border: "1px solid var(--border-color)",
                          cursor: articles.length < 20 ? "not-allowed" : "pointer",
                          fontSize: "13px",
                          fontFamily: "var(--font-body)",
                        }}
                      >
                        Next →
                      </button>
                    </div>
                  </>
                )}

                {/* Social Pulse — mobile only, below articles */}
                {isMobile && (
                  <div style={{
                    borderTop: "1px solid var(--border-color)",
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

        {/* Social Pulse — right column, desktop only. Same sticky-top +
            internal-scroll pattern as the left sidebar. Hidden on the
            Economy and Trade tabs to give those wide panels room. */}
        <aside
          className="hide-scrollbar"
          style={{
            background: "var(--sidebar-bg)",
            borderLeft: "1px solid var(--border-color)",
            padding: "24px 20px",
            position: "sticky",
            top: 0,
            alignSelf: "start",
            maxHeight: "calc(100vh - 52px)",
            overflowY: "auto",
            minWidth: 0,
            display: WIDE_VIEWS.includes(view)
              ? "none"
              : (isMobile ? (mobileTab === "social" ? "block" : "none") : "block"),
          }}
        >
          <SocialPulse column />
        </aside>
      </div>


      {/* About modal */}
      {showAbout && <AboutModal onClose={() => setShowAbout(false)} />}

      {/* Footer — desktop only */}
      <footer
        style={{
          borderTop: "1px solid var(--border-color)",
          padding: "14px 28px",
          display: isMobile ? "none" : "flex",
          justifyContent: "space-between",
          fontSize: "11px",
          color: "var(--text-muted)",
          fontFamily: "var(--font-mono)",
          background: "var(--bg-secondary)",
        }}
      >
        <span>Cross-Strait Signal · Ed Moon</span>
        <span>{stats?.total_articles || 0} articles processed</span>
      </footer>
    </div>
  );
}