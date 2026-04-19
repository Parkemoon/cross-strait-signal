const API_BASE = "";

export async function fetchArticles(params = {}) {
  const query = new URLSearchParams(params).toString();
  const res = await fetch(`${API_BASE}/api/articles?${query}`);
  return res.json();
}

export async function fetchArticle(id) {
  const res = await fetch(`${API_BASE}/api/articles/${id}`);
  return res.json();
}

export async function fetchStats(days = 7, filters = {}) {
  const params = new URLSearchParams({ days });
  const SCOPING_KEYS = ["topic", "source_place", "source_name", "bias", "urgency", "escalation_only", "entity"];
  SCOPING_KEYS.forEach((k) => {
    if (filters[k] !== undefined && filters[k] !== "" && filters[k] !== false) {
      params.append(k, filters[k]);
    }
  });
  const res = await fetch(`${API_BASE}/api/stats?${params}`);
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
    method: "POST",
  });
  return res.json();
}

export async function toggleSignal(articleId) {
  const res = await fetch(`${API_BASE}/api/articles/${articleId}/signal`, {
    method: "PATCH",
  });
  return res.json();
}

export async function fetchSocialPulse() {
  const res = await fetch(`${API_BASE}/api/social`);
  return res.json();
}

export async function fetchKeyFigures() {
  const res = await fetch(`${API_BASE}/api/stats/key-figures`);
  return res.json();
}

export async function fetchKeyFigureCandidates() {
  const res = await fetch(`${API_BASE}/api/stats/key-figures/candidates`);
  return res.json();
}

export async function approveKeyFigureStatement(id) {
  const res = await fetch(`${API_BASE}/api/stats/key-figures/statements/${id}/approve`, { method: "POST" });
  return res.json();
}

export async function dismissKeyFigureStatement(id) {
  const res = await fetch(`${API_BASE}/api/stats/key-figures/statements/${id}/dismiss`, { method: "POST" });
  return res.json();
}

export async function approveArticle(articleId) {
  const res = await fetch(`${API_BASE}/api/articles/${articleId}/approve`, { method: "POST" });
  return res.json();
}

export async function updateArticleTranslation(articleId, overrides) {
  const res = await fetch(`${API_BASE}/api/articles/${articleId}/translation`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(overrides),
  });
  return res.json();
}

export async function updateEntityName(articleId, entityId, entityNameEn) {
  const res = await fetch(`${API_BASE}/api/articles/${articleId}/entities/${entityId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ entity_name_en: entityNameEn }),
  });
  return res.json();
}

export async function correctSocialTranslation(id, titleEnOverride) {
  const res = await fetch(`${API_BASE}/api/social/${id}/translation`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title_en_override: titleEnOverride }),
  });
  return res.json();
}