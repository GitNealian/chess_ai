import axios from "axios";

const http = axios.create({ baseURL: "/api" });

http.interceptors.response.use(
  (response) => response,
  (error) => {
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

export const api = {
  listGames: (params) => http.get("/games", { params }).then((r) => r.data),
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
};
