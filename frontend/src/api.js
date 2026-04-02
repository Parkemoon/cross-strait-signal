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