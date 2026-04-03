import { useState, useEffect } from "react";
import { fetchArticles, fetchStats } from "./api";
import ThemeToggle from "./components/ThemeToggle";
import FlashTraffic from "./components/FlashTraffic";
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

  useEffect(() => {
    setLoading(true);
    const params = { ...filters, page, page_size: 20 };
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
    fetchStats(30).then(setStats);
    fetch("http://localhost:8000/review/stats")
      .then((r) => r.json())
      .then((d) => setReviewPending(d.pending || 0))
      .catch(() => {});
  }, []);

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg-primary)" }}>
      {/* Header */}
      <header
        style={{
          background: "var(--header-bg)",
          color: "var(--header-text)",
          padding: "14px 28px",
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
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <span
            style={{
              fontSize: "11px",
              fontFamily: "var(--font-mono)",
              opacity: 0.5,
            }}
          >
            {total} articles · {stats?.escalation_signals?.length || 0} signals
          </span>

          {/* Review Queue button with pending badge */}
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

          <ThemeToggle />
        </div>
      </header>

      {/* Main layout */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "280px 1fr",
          minHeight: "calc(100vh - 52px)",
        }}
      >
        {/* Sidebar */}
        <aside
          style={{
            background: "var(--sidebar-bg)",
            borderRight: "1px solid var(--border-color)",
            padding: "24px 20px",
            overflowY: "auto",
          }}
        >
          <StatsSidebar stats={stats} />
        </aside>

        {/* Main content */}
        <main style={{ padding: view === "review" ? "0" : "28px 32px" }}>
          {view === "review" ? (
            <ReviewQueue onClose={() => setView("feed")} />
          ) : (
            <>
              {/* Priority Signals */}
              <FlashTraffic escalations={stats?.escalation_signals} />

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
              <FilterBar filters={filters} setFilters={setFilters} />

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
                    <ArticleCard key={article.id} article={article} />
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
      </div>

      {/* Footer */}
      <footer
        style={{
          borderTop: "1px solid var(--border-color)",
          padding: "14px 28px",
          display: "flex",
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