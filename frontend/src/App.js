import { useState, useEffect } from "react";
import { fetchArticles, fetchStats } from "./api";
import { READ_ONLY } from "./readOnly";
import { useWindowWidth } from "./hooks/useWindowWidth";
import ThemeToggle from "./components/ThemeToggle";
import AboutModal from "./components/AboutModal";
import FlashTraffic from "./components/FlashTraffic";
import KeyFigures from "./components/KeyFigures";
import SocialPulse from "./components/SocialPulse";
import ArticleCard from "./components/ArticleCard";
import StatsSidebar from "./components/StatsSidebar";
import FilterBar from "./components/FilterBar";
import ReviewQueue from "./components/ReviewQueue";

export default function App() {
  const [articles, setArticles] = useState([]);
  const [stats, setStats] = useState(null);
  const [filters, setFilters] = useState({});
  const [loading, setLoading] = useState(true);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [view, setView] = useState("feed"); // "feed" | "review"
  const [reviewPending, setReviewPending] = useState(0);
  const [showAbout, setShowAbout] = useState(false);
  const [pendingApproval, setPendingApproval] = useState(0);
  const [mobileTab, setMobileTab] = useState("feed"); // "feed" | "stats" | "social" | "review"
  const windowWidth = useWindowWidth();
  const isMobile = windowWidth < 768;

  useEffect(() => {
    setLoading(true);
    const params = { ...filters, page, page_size: 20 };
    if (!READ_ONLY) params.include_pending = true;
    Object.keys(params).forEach(
      (k) => params[k] === undefined && delete params[k]
    );
    fetchArticles(params).then((data) => {
      setArticles(data.articles || []);
      setTotal(data.total || 0);
      setLoading(false);
    });
  }, [filters, page]);

  useEffect(() => {
    fetchStats(30, {
      topic: filters.topic,
      source_place: filters.source_place,
      urgency: filters.urgency,
      escalation_only: filters.escalation_only,
      entity: filters.entity,
    }).then(setStats);
    fetch("/review/stats")
      .then((r) => r.json())
      .then((d) => {
        setReviewPending(d.pending || 0);
        setPendingApproval(d.pending_approval || 0);
      })
      .catch(() => {});
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters.topic, filters.source_place, filters.urgency, filters.escalation_only, filters.entity]);

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg-primary)" }}>
      {/* Header */}
      <header
        style={{
          background: "var(--header-bg)",
          color: "var(--header-text)",
          padding: isMobile ? "10px 16px" : "14px 28px",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}
      >
        <div style={{ display: "flex", alignItems: "baseline", gap: "16px" }}>
          <h1
            style={{
              fontSize: "22px",
              fontFamily: "var(--font-headline)",
              fontWeight: 400,
              letterSpacing: "0.5px",
            }}
          >
            Cross-Strait Signal
          </h1>
          {!isMobile && (
            <span
              style={{
                fontSize: "11px",
                fontFamily: "var(--font-mono)",
                opacity: 0.5,
                textTransform: "uppercase",
                letterSpacing: "2px",
              }}
            >
              Open-Source Intelligence
            </span>
          )}
          {!isMobile && (
            <button
              onClick={() => setShowAbout(true)}
              style={{
                background: "none",
                border: "none",
                cursor: "pointer",
                fontSize: "11px",
                fontFamily: "var(--font-mono)",
                color: "var(--text-muted)",
                opacity: 0.6,
                padding: 0,
                textTransform: "uppercase",
                letterSpacing: "1px",
              }}
            >
              About
            </button>
          )}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          {!isMobile && (
            <span
              style={{
                fontSize: "11px",
                fontFamily: "var(--font-mono)",
                opacity: 0.5,
              }}
            >
              {total} articles · {stats?.escalation_signals?.length || 0} signals
            </span>
          )}

          {/* Pending approval count — admin only, desktop only */}
          {!READ_ONLY && !isMobile && pendingApproval > 0 && (
            <span
              style={{
                fontSize: "11px",
                fontFamily: "var(--font-mono)",
                color: "#f59e0b",
                background: "rgba(245,158,11,0.1)",
                border: "1px solid rgba(245,158,11,0.3)",
                borderRadius: "4px",
                padding: "4px 10px",
              }}
            >
              {pendingApproval} pending
            </span>
          )}

          {/* Review Queue button with pending badge — admin only, desktop only */}
          {!READ_ONLY && !isMobile && (
            <button
              onClick={() => setView(view === "review" ? "feed" : "review")}
              style={{
                padding: "6px 14px",
                background: view === "review" ? "var(--accent)" : "var(--bg-card)",
                color: view === "review" ? "#fff" : "var(--text-secondary)",
                border: "1px solid var(--border-color)",
                borderRadius: "4px",
                cursor: "pointer",
                fontSize: "12px",
                fontFamily: "var(--font-mono)",
                position: "relative",
              }}
            >
              Review
              {reviewPending > 0 && (
                <span
                  style={{
                    position: "absolute",
                    top: "-6px",
                    right: "-6px",
                    background: "#e67e22",
                    color: "#fff",
                    borderRadius: "50%",
                    width: "16px",
                    height: "16px",
                    fontSize: "10px",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontFamily: "var(--font-mono)",
                  }}
                >
                  {reviewPending}
                </span>
              )}
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

      {/* Mobile tab bar — sticky top, below header */}
      {isMobile && (
        <nav style={{
          position: "sticky",
          top: 0,
          background: "var(--header-bg)",
          borderBottom: "1px solid rgba(255,255,255,0.1)",
          display: "flex",
          zIndex: 100,
        }}>
          {[
            { id: "feed", label: "Feed" },
            { id: "stats", label: "Stats" },
            { id: "social", label: "Social" },
            ...(!READ_ONLY ? [{ id: "review", label: (reviewPending + pendingApproval) > 0 ? `Review (${reviewPending + pendingApproval})` : "Review" }] : []),
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => {
                setMobileTab(tab.id);
                if (tab.id === "review") setView("review");
                if (tab.id === "feed") setView("feed");
              }}
              style={{
                flex: 1,
                padding: "14px 4px",
                background: "transparent",
                color: mobileTab === tab.id ? "var(--header-text)" : "rgba(255,255,255,0.4)",
                border: "none",
                borderBottom: mobileTab === tab.id ? "2px solid var(--accent)" : "2px solid transparent",
                fontSize: "12px",
                fontFamily: "var(--font-mono)",
                textTransform: "uppercase",
                letterSpacing: "1px",
                cursor: "pointer",
              }}
            >
              {tab.label}
            </button>
          ))}
        </nav>
      )}

      {/* Main layout */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: isMobile ? "1fr" : "280px 1fr 300px",
          minHeight: "calc(100vh - 52px)",
        }}
      >
        {/* Sidebar */}
        <aside
          style={{
            background: "var(--sidebar-bg)",
            borderRight: isMobile ? "none" : "1px solid var(--border-color)",
            padding: "24px 20px",
            overflowY: "auto",
            display: isMobile ? (mobileTab === "stats" ? "block" : "none") : "block",
          }}
        >
          <StatsSidebar
            stats={stats}
            filters={filters}
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

        {/* Main content */}
        <main style={{
          padding: isMobile ? "16px" : ((!READ_ONLY && view === "review") ? "0" : "28px 32px"),
          minWidth: 0,
          overflow: "hidden",
          display: isMobile ? (mobileTab === "feed" || mobileTab === "review" ? "block" : "none") : "block",
        }}>
          {!READ_ONLY && view === "review" ? (
            <ReviewQueue onClose={() => setView("feed")} />
          ) : (
            <>
              {/* Priority Signals */}
              <FlashTraffic
                escalations={stats?.escalation_signals}
                onTopicClick={(topic) => { setFilters((f) => ({ ...f, topic })); setPage(1); }}
                onEntityClick={(entityName) => { setFilters((f) => ({ ...f, entity: entityName, search: undefined })); setPage(1); }}
                onApprove={() => setPendingApproval((n) => Math.max(0, n - 1))}
              />

              <KeyFigures />

              {/* Section header */}
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "baseline",
                  marginBottom: "6px",
                }}
              >
                <h2
                  style={{
                    fontFamily: "var(--font-headline)",
                    fontSize: "24px",
                    fontWeight: 400,
                    color: "var(--text-primary)",
                  }}
                >
                  Signal Feed
                </h2>
                <span
                  style={{
                    fontSize: "11px",
                    fontFamily: "var(--font-mono)",
                    color: "var(--text-muted)",
                  }}
                >
                  {total} results
                </span>
              </div>

              {/* Divider */}
              <div
                style={{
                  height: "2px",
                  background: "var(--text-primary)",
                  marginBottom: "16px",
                  opacity: 0.15,
                }}
              />

              {/* Filters */}
              <FilterBar
                filters={filters}
                setFilters={setFilters}
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
                  No articles match these filters.
                </p>
              ) : (
                <>
                  {articles.map((article) => (
                    <ArticleCard
                      key={article.id}
                      article={article}
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
                      paddingBottom: "40px",
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
                        borderRadius: "4px",
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
                        borderRadius: "4px",
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
            </>
          )}
        </main>

        {/* Right column — Social Pulse */}
        <aside
          style={{
            background: "var(--sidebar-bg)",
            borderLeft: isMobile ? "none" : "1px solid var(--border-color)",
            padding: "24px 20px",
            overflowY: "auto",
            display: isMobile ? (mobileTab === "social" ? "block" : "none") : "block",
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