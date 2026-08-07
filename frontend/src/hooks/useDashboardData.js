import { useEffect, useRef, useState } from "react";
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
// `altLens` ({model, arm} | null, admin only) re-renders the feed AND the
// sidebar stats through an alt-model sweep's classifications — the server
// narrows both to swept articles; stats re-aggregate from the sweep's ok rows.
export function useDashboardData(filters, page, altLens = null) {
  const [articles, setArticles] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState(null);
  const [reviewPending, setReviewPending] = useState(0);
  const [pendingApproval, setPendingApproval] = useState(0);
  // Monotonic request id — filters can change per keystroke (no debounce), so a
  // slow earlier response must not clobber a newer one (or clear its spinner).
  const articlesReq = useRef(0);

  useEffect(() => {
    setLoading(true);
    const myReq = ++articlesReq.current;
    const params = { ...filters, page, page_size: 20 };
    if (!READ_ONLY) params.include_pending = true;
    if (altLens) {
      params.alt_model = altLens.model;
      params.alt_arm = altLens.arm;
    }
    Object.keys(params).forEach(
      (k) => params[k] === undefined && delete params[k]
    );
    fetchArticles(params)
      .then((data) => {
        if (myReq !== articlesReq.current) return; // superseded by a newer load
        setArticles(data.articles || []);
        setTotal(data.total || 0);
      })
      .catch((err) => {
        if (myReq !== articlesReq.current) return;
        console.error("Failed to load articles:", err);
        setArticles([]);
        setTotal(0);
      })
      .finally(() => {
        if (myReq === articlesReq.current) setLoading(false);
      });
  }, [filters, page, altLens]);

  // Only the scoping filters affect stats — sentiment/search are article-list-
  // only filters. bias + source_name ARE scoping filters (see api.js
  // SCOPING_KEYS and StatsSidebar's bias/source click handlers), so they must
  // be threaded here too or the sidebar charts stay unscoped after those clicks.
  const { topic, source_place, urgency, escalation_only, entity, bias, source_name } = filters;
  useEffect(() => {
    fetchStats(30, { topic, source_place, urgency, escalation_only, entity, bias, source_name }, altLens)
      .then(setStats)
      .catch((err) => console.error("Failed to load stats:", err));
    fetchReviewStats()
      .then((d) => {
        setReviewPending(d?.pending || 0);
        setPendingApproval(d?.pending_approval || 0);
      })
      .catch(() => {});
  }, [topic, source_place, urgency, escalation_only, entity, bias, source_name, altLens]);

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
