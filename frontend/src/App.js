import { useState, useEffect } from "react";
import { fetchArticles, fetchStats } from "./api";
import ThemeToggle from "./components/ThemeToggle";
import FlashTraffic from "./components/FlashTraffic";
import ArticleCard from "./components/ArticleCard";
import StatsSidebar from "./components/StatsSidebar";
import FilterBar from "./components/FilterBar";

export default function App() {
  const [articles, setArticles] = useState([]);
  const [stats, setStats] = useState(null);
  const [filters, setFilters] = useState({});
  const [loading, setLoading] = useState(true);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);

  // Fetch articles when filters or page change
  useEffect(() => {
    setLoading(true);
    const params = { ...filters, page, page_size: 20 };
    // Remove undefined values
    Object.keys(params).forEach(
      (k) => params[k] === undefined && delete params[k]
    );
    fetchArticles(params).then((data) => {
      setArticles(data.articles || []);
      setTotal(data.total || 0);
      setLoading(false);
    });
  }, [filters, page]);

  // Fetch stats on load
  useEffect(() => {
    fetchStats(30).then(setStats);
  }, []);

  return (
    <div
      style={{
        minHeight: "100vh",
        background: "var(--bg-primary)",
        color: "var(--text-primary)",
      }}
    >
      {/* Header */}
      <header
        style={{
          borderBottom: "1px solid var(--border-color)",
          padding: "16px 24px",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          background: "var(--bg-secondary)",
        }}
      >
        <div>
          <h1
            style={{
              fontSize: "20px",
              fontWeight: 700,
              letterSpacing: "1px",
              margin: 0,
              fontFamily: "'JetBrains Mono', 'Courier New', monospace",
            }}
          >
            CROSS-STRAIT SIGNAL
          </h1>
          <p
            style={{
              fontSize: "11px",
              color: "var(--text-muted)",
              margin: "2px 0 0 0",
              fontFamily: "'JetBrains Mono', 'Courier New', monospace",
              textTransform: "uppercase",
              letterSpacing: "1.5px",
            }}
          >
            Intelligence Dashboard
          </p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
          <span
            style={{
              fontSize: "11px",
              color: "var(--text-muted)",
              fontFamily: "'JetBrains Mono', 'Courier New', monospace",
            }}
          >
            {total} articles · {stats?.escalation_signals?.length || 0} signals
          </span>
          <ThemeToggle />
        </div>
      </header>

      {/* Main layout */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "260px 1fr",
          gap: "24px",
          padding: "24px",
          maxWidth: "1400px",
          margin: "0 auto",
        }}
      >
        {/* Sidebar */}
        <aside>
          <StatsSidebar stats={stats} />
        </aside>

        {/* Main content */}
        <main>
          {/* Flash traffic */}
          <FlashTraffic escalations={stats?.escalation_signals} />

          {/* Filters */}
          <FilterBar filters={filters} setFilters={setFilters} />

          {/* Article feed */}
          {loading ? (
            <p
              style={{
                color: "var(--text-muted)",
                fontFamily: "'JetBrains Mono', 'Courier New', monospace",
                fontSize: "13px",
              }}
            >
              Loading...
            </p>
          ) : articles.length === 0 ? (
            <p
              style={{
                color: "var(--text-muted)",
                fontFamily: "'JetBrains Mono', 'Courier New', monospace",
                fontSize: "13px",
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
                  marginTop: "20px",
                }}
              >
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page <= 1}
                  style={{
                    padding: "6px 16px",
                    background: "var(--bg-card)",
                    color: "var(--text-secondary)",
                    border: "1px solid var(--border-color)",
                    borderRadius: "4px",
                    cursor: page <= 1 ? "not-allowed" : "pointer",
                    fontSize: "12px",
                    fontFamily: "'JetBrains Mono', 'Courier New', monospace",
                  }}
                >
                  ← Prev
                </button>
                <span
                  style={{
                    padding: "6px 0",
                    fontSize: "12px",
                    color: "var(--text-muted)",
                    fontFamily: "'JetBrains Mono', 'Courier New', monospace",
                  }}
                >
                  Page {page}
                </span>
                <button
                  onClick={() => setPage((p) => p + 1)}
                  disabled={articles.length < 20}
                  style={{
                    padding: "6px 16px",
                    background: "var(--bg-card)",
                    color: "var(--text-secondary)",
                    border: "1px solid var(--border-color)",
                    borderRadius: "4px",
                    cursor: articles.length < 20 ? "not-allowed" : "pointer",
                    fontSize: "12px",
                    fontFamily: "'JetBrains Mono', 'Courier New', monospace",
                  }}
                >
                  Next →
                </button>
              </div>
            </>
          )}
        </main>
      </div>

      {/* Footer */}
      <footer
        style={{
          borderTop: "1px solid var(--border-color)",
          padding: "16px 24px",
          textAlign: "center",
          fontSize: "11px",
          color: "var(--text-muted)",
          fontFamily: "'JetBrains Mono', 'Courier New', monospace",
        }}
      >
        Cross-Strait Signal · Built by Ed Moon · {stats?.total_articles || 0}{" "}
        articles analysed
      </footer>
    </div>
  );
}