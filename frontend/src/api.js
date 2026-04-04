const API_BASE = "http://localhost:8000";

export async function fetchArticles(params = {}) {
  const query = new URLSearchParams(params).toString();
  const res = await fetch(`${API_BASE}/api/articles?${query}`);
  return res.json();
}

export async function fetchArticle(id) {
  const res = await fetch(`${API_BASE}/api/articles/${id}`);
  return res.json();
}

export async function fetchStats(days = 7) {
  const res = await fetch(`${API_BASE}/api/stats?days=${days}`);
  return res.json();
}

export async function fetchEntities(params = {}) {
  const query = new URLSearchParams(params).toString();
  const res = await fetch(`${API_BASE}/api/stats/entities?${query}`);
  return res.json();
}

export async function createNote(note) {
  const res = await fetch(`${API_BASE}/api/notes/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(note),
  });
  return res.json();
}

export async function fetchNotes(articleId) {
  const res = await fetch(`${API_BASE}/api/notes/article/${articleId}`);
  return res.json();
}

export async function fetchReviewQueue() {
  const res = await fetch(`${API_BASE}/review/queue`);
  return res.json();
}

export async function fetchReviewStats() {
  const res = await fetch(`${API_BASE}/review/stats`);
  return res.json();
}

export async function resolveReview(analysisId, decision) {
  const res = await fetch(`${API_BASE}/review/${analysisId}/resolve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(decision),
  });
  return res.json();
}

export async function fetchArticleCluster(articleId) {
  const res = await fetch(`${API_BASE}/api/articles/${articleId}/cluster`);
  return res.json();
}

export async function hideArticle(articleId) {
  const res = await fetch(`${API_BASE}/api/articles/${articleId}/hide`, {
    method: "PATCH",
  });
  return res.json();
}

export async function markAsSignal(articleId) {
  const res = await fetch(`${API_BASE}/api/articles/${articleId}/signal`, {
    method: "PATCH",
  });
  return res.json();
}