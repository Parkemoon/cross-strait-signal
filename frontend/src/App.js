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
          {!isMobile && !READ_ONLY && (
            <button
              onClick={() => setView(view === "review" ? "feed" : "review")}
              style={{
                padding: "5px 12px",
                background: view === "review" ? "rgba(255,255,255,0.12)" : "transparent",
                color: view === "review" ? "var(--header-text)" : "rgba(255,255,255,0.45)",
                border: "1px solid rgba(255,255,255,0.14)",
                cursor: "pointer",
                fontSize: "10px",
                fontFamily: "var(--font-mono)",
                letterSpacing: "0.1em",
                textTransform: "uppercase",
                position: "relative",
              }}
            >
              Review
              {reviewPending > 0 && (
                <span style={{
                  position: "absolute",
                  top: "-5px",
                  right: "-5px",
                  background: "#e67e22",
                  color: "#fff",
                  borderRadius: "50%",
                  width: "14px",
                  height: "14px",
                  fontSize: "9px",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontFamily: "var(--font-mono)",
                }}>
                  {reviewPending}
                </span>
              )}
            </button>
          )}
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

      {/* Tab bar — mobile only */}
      {isMobile && <nav style={{
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
          ...(!READ_ONLY ? [{ id: "review", label: reviewPending > 0 ? `Review (${reviewPending})` : "Review" }] : []),
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => {
              setMobileTab(tab.id);
              if (tab.id === "review") setView("review");
              else setView("feed");
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
      </nav>}

      {/* Main layout */}
      <div style={{
        display: isMobile ? "block" : "grid",
        gridTemplateColumns: "clamp(300px, 20vw, 420px) 1fr 300px",
        minHeight: "calc(100vh - 52px)",
        alignItems: "start",
        overflow: "hidden",
      }}>
        {/* Stats sidebar — always visible on desktop, tab-controlled on mobile */}
        <aside
          className={isMobile ? "" : "hide-scrollbar"}
          style={{
            background: "var(--sidebar-bg)",
            borderRight: isMobile ? "none" : "1px solid var(--border-color)",
            padding: "24px 20px",
            overflowY: "auto",
            position: isMobile ? "static" : "sticky",
            top: 0,
            height: isMobile ? "auto" : "100vh",
            minWidth: 0,
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

        {/* Feed / Review — center column */}
        <div style={{ display: isMobile ? ((mobileTab === "feed" || mobileTab === "review") ? "block" : "none") : "block", minWidth: 0 }}>
          {!READ_ONLY && view === "review" ? (
            <ReviewQueue onClose={() => setView("feed")} />
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

        {/* Social Pulse — right column, desktop only, sticky full-height */}
        <aside
          className={isMobile ? "" : "hide-scrollbar"}
          style={{
            background: "var(--sidebar-bg)",
            borderLeft: "1px solid var(--border-color)",
            padding: "24px 20px",
            position: "sticky",
            top: 0,
            height: "100vh",
            overflowY: "auto",
            minWidth: 0,
            display: isMobile ? "none" : "block",
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