export const API = import.meta.env.VITE_API_URL || "http://localhost:8000";
export const WS = API.replace(/^http/, "ws");

// Session token comes from the URL (candidate or interviewer link). The admin token is kept
// in this browser's session storage and is sent only when no session token is present.
let sessionToken = "";
let adminToken = sessionStorage.getItem("adminToken") || "";

export const setSessionToken = (token) => {
  sessionToken = token || "";
};
export const getSessionToken = () => sessionToken;
export const getAdminToken = () => adminToken;
export const hasAdminToken = () => Boolean(adminToken);
export const setAdminToken = (token) => {
  adminToken = token || "";
  if (adminToken) sessionStorage.setItem("adminToken", adminToken);
  else sessionStorage.removeItem("adminToken");
};

function authHeaders() {
  if (sessionToken) return { "X-Session-Token": sessionToken };
  if (adminToken) return { "X-Admin-Token": adminToken };
  return {};
}

async function request(path, options = {}) {
  const res = await fetch(API + path, {
    headers: { "Content-Type": "application/json", ...authHeaders() },
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed (${res.status})`);
  }
  return res.status === 204 ? null : res.json();
}

const json = (body) => JSON.stringify(body);

export const api = {
  problems: () => request("/problems"),
  createProblem: (body) => request("/problems", { method: "POST", body: json(body) }),
  deleteProblem: (id) => request(`/problems/${id}`, { method: "DELETE" }),
  problemTests: (id) => request(`/problems/${id}/tests`),
  addTest: (id, body) => request(`/problems/${id}/tests`, { method: "POST", body: json(body) }),
  listSessions: () => request("/sessions?limit=100"),
  createSession: (body) => request("/sessions", { method: "POST", body: json(body) }),
  getSession: (id) => request(`/sessions/${id}`),
  updateSession: (id, body) => request(`/sessions/${id}`, { method: "PATCH", body: json(body) }),
  sessionProblem: (id) => request(`/sessions/${id}/problem`),
  summary: (id) => request(`/sessions/${id}/summary`),
  feedback: (id) => request(`/sessions/${id}/feedback`),
  recordEvent: (id, kind, detail) => request(`/sessions/${id}/events`, { method: "POST", body: json({ kind, detail }) }),
  latestSnapshot: (id) => request(`/sessions/${id}/snapshot`),
  saveSnapshot: (id, code) => request(`/sessions/${id}/snapshot`, { method: "PUT", body: json({ code }) }),
  runs: (id) => request(`/sessions/${id}/runs`),
  startRun: (id, kind, code) => request(`/sessions/${id}/runs`, { method: "POST", body: json({ kind, code }) }),
  copilot: (id) => request(`/sessions/${id}/copilot`, { method: "POST" }),
  aiScorecard: (id) => request(`/sessions/${id}/ai-scorecard`, { method: "POST" }),
  aiProblemDraft: (body) => request("/problems/ai-draft", { method: "POST", body: json(body) }),
  saveScorecard: (id, body) => request(`/sessions/${id}/scorecard`, { method: "PUT", body: json(body) }),
};
