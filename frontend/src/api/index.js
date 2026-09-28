import axios from "axios";

function notifyUnauthorized() {
  window.dispatchEvent(new CustomEvent("app-unauthorized"));
}

const http = axios.create({ baseURL: "/api" });

http.interceptors.response.use(
  (response) => response,
  (error) => {
    if (axios.isCancel(error) || error?.code === "ECONNABORTED") {
      return Promise.reject(error);
    }
    if (error.response?.status === 401) {
      if (!error.config?.url?.includes("/auth/")) {
        notifyUnauthorized();
      }
      return Promise.reject(error);
    }
    const data = error.response?.data;
    const message = data?.detail || data?.error || "请求失败";
    window.dispatchEvent(new CustomEvent("app-toast", { detail: message }));
    return Promise.reject(error);
  }
);

export async function analyzeStream(payload, { signal, onResult, onDone, onError } = {}) {
  try {
    const response = await fetch("/api/engine/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal,
    });
    if (!response.ok) {
      if (response.status === 401) notifyUnauthorized();
      const data = await response.json().catch(() => ({}));
      throw new Error(data.detail || data.error || `分析请求失败（${response.status}）`);
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    const handleLine = (line) => {
      const text = line.trim();
      if (!text) return;
      let msg;
      try {
        msg = JSON.parse(text);
      } catch {
        return;
      }
      if (msg.type === "result") onResult?.(msg);
      else if (msg.type === "done") onDone?.(msg);
      else if (msg.type === "error") onError?.(new Error(msg.message || "分析失败"));
    };
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop();
      lines.forEach(handleLine);
    }
    buffer += decoder.decode();
    handleLine(buffer);
  } catch (err) {
    if (err?.name === "AbortError") return;
    onError?.(err);
  }
}

export async function intentStream(
  payload,
  { signal, onRank, onThreat, onBait, onDone, onError } = {}
) {
  try {
    const response = await fetch("/api/engine/intent", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal,
    });
    if (!response.ok) {
      if (response.status === 401) notifyUnauthorized();
      const data = await response.json().catch(() => ({}));
      throw new Error(data.detail || data.error || `意图推演请求失败（${response.status}）`);
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    const handleLine = (line) => {
      const text = line.trim();
      if (!text) return;
      let msg;
      try {
        msg = JSON.parse(text);
      } catch {
        return;
      }
      if (msg.type === "rank") onRank?.(msg);
      else if (msg.type === "threat") onThreat?.(msg);
      else if (msg.type === "bait") onBait?.(msg);
      else if (msg.type === "done") onDone?.(msg);
      else if (msg.type === "error") onError?.(new Error(msg.message || "意图推演失败"));
      // ping 忽略
    };
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop();
      lines.forEach(handleLine);
    }
    buffer += decoder.decode();
    handleLine(buffer);
  } catch (err) {
    if (err?.name === "AbortError") return;
    onError?.(err);
  }
}

export const api = {
  listGames: (params) => http.get("/games", { params }).then((r) => r.data),
  listCollections: (params) => http.get("/games/collections", { params }).then((r) => r.data),
  listEvents: (params) => http.get("/games/events", { params }).then((r) => r.data),
  openGame: (id) => http.post(`/games/${id}/open`).then((r) => r.data),
  favoriteGame: (id) => http.post(`/games/${id}/favorite`).then((r) => r.data),
  getGame: (id) => http.get(`/games/${id}`).then((r) => r.data),
  createGame: (data) => http.post("/games", data).then((r) => r.data),
  updateGame: (id, data) => http.put(`/games/${id}`, data).then((r) => r.data),
  deleteGame: (id) => http.delete(`/games/${id}`).then((r) => r.data),
  parse: (data) => http.post("/games/parse", data).then((r) => r.data),
  importPgn: (data) => http.post("/games/import-pgn", data).then((r) => r.data),
  checkMove: (id, data) => http.post(`/games/${id}/check-move`, data).then((r) => r.data),
  reviewQueue: () => http.get("/review/queue").then((r) => r.data),
  submitReview: (id, data) => http.post(`/review/${id}/submit`, data).then((r) => r.data),
  stats: () => http.get("/stats").then((r) => r.data),
  validateMove: (data) => http.post("/engine/validate-move", data).then((r) => r.data),
  bestMove: (data, config) => http.post("/engine/best-move", data, config).then((r) => r.data),
  validatePosition: (data, config) =>
    http.post("/engine/validate-position", data, config).then((r) => r.data),
  recognize: (formData, config) => http.post("/recognize", formData, config).then((r) => r.data),
  login: (password) => http.post("/auth/login", { password }).then((r) => r.data),
  logout: () => http.post("/auth/logout").then((r) => r.data),
  authMe: () => http.get("/auth/me").then((r) => r.data),
};
