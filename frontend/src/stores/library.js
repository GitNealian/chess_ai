import { defineStore } from "pinia";
import { api } from "../api";

export const useLibraryStore = defineStore("library", {
  state: () => ({ games: [], stats: null, loading: false, _requestId: 0 }),
  actions: {
    async fetchGames(params) {
      this.loading = true;
      const requestId = ++this._requestId;
      try {
        const data = await api.listGames(params);
        if (requestId === this._requestId) {
          this.games = data.items;
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
    },
  },
});
