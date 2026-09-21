import { defineStore } from "pinia";
import { api } from "../api";

export const useLibraryStore = defineStore("library", {
  state: () => ({
    games: [],
    total: 0,
    page: 1,
    pageSize: 20,
    stats: null,
    loading: false,
    _requestId: 0,
  }),
  actions: {
    async fetchGames(params) {
      this.loading = true;
      const requestId = ++this._requestId;
      try {
        const data = await api.listGames({
          page: this.page,
          page_size: this.pageSize,
          ...params,
        });
        if (requestId === this._requestId) {
          this.games = data.items;
          this.total = data.total ?? data.items.length;
        }
      } finally {
        if (requestId === this._requestId) {
          this.loading = false;
        }
      }
    },
    async fetchStats() {
      this.stats = await api.stats();
    },
    async remove(id) {
      await api.deleteGame(id);
      this.games = this.games.filter((game) => game.id !== id);
      this.total = Math.max(0, this.total - 1);
    },
  },
});
