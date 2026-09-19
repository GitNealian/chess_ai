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
};
