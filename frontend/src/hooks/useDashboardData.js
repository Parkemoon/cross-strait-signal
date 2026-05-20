import { useEffect, useState } from "react";
import { fetchArticles, fetchStats, fetchReviewStats } from "../api";
import { READ_ONLY } from "../readOnly";

// Drives the three async loads that back the main dashboard view:
//   - the paginated article feed (refetches on filter/page change)
//   - aggregate stats for the sidebar + sentiment charts (refetches on
//     scoping-filter change; sentiment + search are excluded — see api.js)
//   - review-queue and pending-approval counts (refetches alongside stats)
//
// Returns plain state plus a setter for pendingApproval so callers can
// optimistically decrement it after an Approve action without waiting for
// the next stats refresh.
export function useDashboardData(filters, page) {
  const [articles, setArticles] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState(null);
  const [reviewPending, setReviewPending] = useState(0);
  const [pendingApproval, setPendingApproval] = useState(0);

  useEffect(() => {
    setLoading(true);
    const params = { ...filters, page, page_size: 20 };
    if (!READ_ONLY) params.include_pending = true;
    Object.keys(params).forEach(
      (k) => params[k] === undefined && delete params[k]
    );
    fetchArticles(params)
      .then((data) => {
        setArticles(data.articles || []);
        setTotal(data.total || 0);
      })
      .catch((err) => {
        console.error("Failed to load articles:", err);
        setArticles([]);
        setTotal(0);
      })
      .finally(() => setLoading(false));
  }, [filters, page]);

  // Only the scoping filters affect stats — sentiment/search/source_name
  // are article-list-only filters (see api.js SCOPING_KEYS).
  const { topic, source_place, urgency, escalation_only, entity } = filters;
  useEffect(() => {
    fetchStats(30, { topic, source_place, urgency, escalation_only, entity })
      .then(setStats)
      .catch((err) => console.error("Failed to load stats:", err));
    fetchReviewStats()
      .then((d) => {
        setReviewPending(d?.pending || 0);
        setPendingApproval(d?.pending_approval || 0);
      })
      .catch(() => {});
  }, [topic, source_place, urgency, escalation_only, entity]);

  return {
    articles,
    total,
    loading,
    stats,
    reviewPending,
    pendingApproval,
    setPendingApproval,
  };
}
