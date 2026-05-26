const API_BASE = "";

// When the admin build is configured with REACT_APP_ADMIN_TOKEN, every write
// request includes it as X-Admin-Token. The public read-only build leaves it
// undefined and never issues writes (nginx blocks those anyway).
const ADMIN_TOKEN = process.env.REACT_APP_ADMIN_TOKEN || "";

function authHeaders() {
  return ADMIN_TOKEN ? { "X-Admin-Token": ADMIN_TOKEN } : {};
}

async function request(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, options);
  if (!res.ok) {
    let detail = "";
    try {
      const body = await res.json();
      detail = body?.detail || JSON.stringify(body);
    } catch {
      try { detail = await res.text(); } catch { /* ignore */ }
    }
    const err = new Error(`API ${res.status}: ${detail || res.statusText}`);
    err.status = res.status;
    throw err;
  }
  // Some endpoints return 204 / empty body.
  const text = await res.text();
  return text ? JSON.parse(text) : null;
}

export async function fetchArticles(params = {}) {
  const query = new URLSearchParams(params).toString();
  return request(`/api/articles?${query}`);
}

export async function fetchArticle(id) {
  return request(`/api/articles/${id}`);
}

export async function fetchStats(days = 30, filters = {}) {
  const params = new URLSearchParams({ days });
  const SCOPING_KEYS = ["topic", "source_place", "source_name", "bias", "urgency", "escalation_only", "entity"];
  SCOPING_KEYS.forEach((k) => {
    if (filters[k] !== undefined && filters[k] !== "" && filters[k] !== false) {
      params.append(k, filters[k]);
    }
  });
  return request(`/api/stats?${params}`);
}

export async function fetchEntities(params = {}) {
  const query = new URLSearchParams(params).toString();
  return request(`/api/stats/entities?${query}`);
}

export async function createNote(note) {
  return request(`/api/notes/`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(note),
  });
}

export async function fetchNotes(articleId) {
  return request(`/api/notes/article/${articleId}`);
}

export async function fetchReviewQueue() {
  return request(`/review/queue`);
}

export async function fetchReviewStats() {
  return request(`/review/stats`);
}

export async function resolveReview(analysisId, decision) {
  return request(`/review/${analysisId}/resolve`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(decision),
  });
}

export async function fetchArticleCluster(articleId) {
  return request(`/api/articles/${articleId}/cluster`);
}

export async function hideArticle(articleId) {
  return request(`/api/articles/${articleId}/hide`, {
    method: "POST",
    headers: authHeaders(),
  });
}

export async function toggleSignal(articleId) {
  return request(`/api/articles/${articleId}/signal`, {
    method: "PATCH",
    headers: authHeaders(),
  });
}

export async function fetchSocialPulse() {
  return request(`/api/social`);
}

export async function fetchKeyFigures() {
  return request(`/api/stats/key-figures`);
}

export async function fetchKeyFigureCandidates() {
  return request(`/api/stats/key-figures/candidates`);
}

export async function approveKeyFigureStatement(id) {
  return request(`/api/stats/key-figures/statements/${id}/approve`, {
    method: "POST",
    headers: authHeaders(),
  });
}

export async function dismissKeyFigureStatement(id) {
  return request(`/api/stats/key-figures/statements/${id}/dismiss`, {
    method: "POST",
    headers: authHeaders(),
  });
}

export async function approveArticle(articleId) {
  return request(`/api/articles/${articleId}/approve`, {
    method: "POST",
    headers: authHeaders(),
  });
}

export async function updateArticleTranslation(articleId, overrides) {
  return request(`/api/articles/${articleId}/translation`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(overrides),
  });
}

export async function updateEntityName(articleId, entityId, entityNameEn) {
  return request(`/api/articles/${articleId}/entities/${entityId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ entity_name_en: entityNameEn }),
  });
}

export async function fetchEconomySeries(params = {}) {
  const query = new URLSearchParams();
  if (params.ids) query.append("ids", Array.isArray(params.ids) ? params.ids.join(",") : params.ids);
  if (params.start) query.append("start", params.start);
  if (params.end) query.append("end", params.end);
  if (params.months) query.append("months", params.months);
  return request(`/api/economy/series?${query}`);
}

export async function fetchEconomyVerification(params = {}) {
  const query = new URLSearchParams();
  if (params.months) query.append("months", params.months);
  return request(`/api/economy/verification?${query}`);
}

export async function fetchInvestmentByIndustry(direction = "prc_to_tw", top = 10) {
  return request(`/api/economy/investment-by-industry?direction=${direction}&top=${top}`);
}

export async function fetchInvestmentVerification() {
  return request(`/api/economy/investment-verification`);
}

export async function fetchPeopleRecords() {
  return request(`/api/economy/people-records`);
}

export async function fetchTradeAccessItems(params = {}) {
  const query = new URLSearchParams();
  ["direction", "status", "hs_prefix", "search", "limit", "offset"].forEach((k) => {
    if (params[k] !== undefined && params[k] !== "" && params[k] !== null) {
      query.append(k, params[k]);
    }
  });
  return request(`/api/trade-access/items?${query}`);
}

export async function fetchTradeAccessSummary() {
  return request(`/api/trade-access/summary`);
}

export async function fetchCiferSnapshot() {
  return request(`/api/trade-access/cifer-snapshot`);
}

export async function fetchMilitaryIncursions(params = {}) {
  const query = new URLSearchParams();
  ["days", "start", "end"].forEach((k) => {
    if (params[k] !== undefined && params[k] !== "" && params[k] !== null) {
      query.append(k, params[k]);
    }
  });
  return request(`/api/military/incursions?${query}`);
}

export async function fetchMilitaryIncursionsMonthly(months = 48) {
  return request(`/api/military/incursions/monthly?months=${months}`);
}

export async function fetchMilitarySummary() {
  return request(`/api/military/incursions/summary`);
}

export async function fetchMilitaryZones() {
  return request(`/api/military/zones`);
}

export async function fetchMilitaryExercises(params = {}) {
  const query = new URLSearchParams();
  ["start", "end", "performer", "kind", "days", "with_geo"].forEach((k) => {
    if (params[k] !== undefined && params[k] !== "" && params[k] !== null) {
      query.append(k, params[k]);
    }
  });
  return request(`/api/military/exercises?${query}`);
}

export async function fetchMilitaryExerciseSummary() {
  return request(`/api/military/exercises/summary`);
}

export async function fetchMilitaryExerciseCandidates() {
  return request(`/api/military/exercises/candidates`, {
    headers: authHeaders(),
  });
}

export async function approveMilitaryExercise(id) {
  return request(`/api/military/exercises/${id}/approve`, {
    method: "POST",
    headers: authHeaders(),
  });
}

export async function dismissMilitaryExercise(id) {
  return request(`/api/military/exercises/${id}/dismiss`, {
    method: "POST",
    headers: authHeaders(),
  });
}

export async function mergeMilitaryExercise(id, targetId) {
  return request(`/api/military/exercises/${id}/merge`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ target_id: targetId }),
  });
}

export async function updateMilitaryExercise(id, patch) {
  return request(`/api/military/exercises/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(patch),
  });
}

// Polls — read endpoints (admin actions land alongside in a follow-up).
// The list endpoint returns multi-question poll envelopes (one polls row
// can carry identity + unification + party-ID for the same survey wave);
// use the `questions[]` array on each poll rather than expecting one
// question per row. by-question filters down to a single canonical
// question across pollsters for the trend charts.

export async function fetchPolls(params = {}) {
  const query = new URLSearchParams(params).toString();
  return request(`/api/polls/?${query}`);
}

export async function fetchPollsByQuestion(questionKey, params = {}) {
  const query = new URLSearchParams(params).toString();
  return request(`/api/polls/by-question/${encodeURIComponent(questionKey)}${query ? `?${query}` : ""}`);
}

export async function fetchPollsRoster() {
  return request(`/api/polls/roster`);
}

export async function createPollster(body) {
  return request(`/api/polls/pollsters`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body),
  });
}

export async function fetchPollsTopics() {
  return request(`/api/polls/topics`);
}

// Admin / review queue helpers. Approve payload carries one
// QuestionResolution per pending question (in pending_results_json
// order) — caller picks an existing question_key OR supplies new-key
// creation fields. PATCH / dismiss / merge mirror the exercise tracker
// shape so the components can be cribbed.

export async function fetchPollCandidates() {
  return request(`/api/polls/candidates`, { headers: authHeaders() });
}

export async function approvePoll(id, payload) {
  return request(`/api/polls/${id}/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(payload),
  });
}

export async function dismissPoll(id, reviewedBy) {
  const query = reviewedBy ? `?reviewed_by=${encodeURIComponent(reviewedBy)}` : "";
  return request(`/api/polls/${id}/dismiss${query}`, {
    method: "POST",
    headers: authHeaders(),
  });
}

export async function mergePoll(id, targetId, reviewedBy) {
  return request(`/api/polls/${id}/merge`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ target_id: targetId, reviewed_by: reviewedBy }),
  });
}

export async function updatePoll(id, patch) {
  return request(`/api/polls/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(patch),
  });
}

export async function createPoll(body) {
  return request(`/api/polls/`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body),
  });
}

export async function correctSocialTranslation(id, titleEnOverride) {
  return request(`/api/social/${id}/translation`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ title_en_override: titleEnOverride }),
  });
}
