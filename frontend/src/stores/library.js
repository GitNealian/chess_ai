import { defineStore } from "pinia";
import { api } from "../api";

export const useLibraryStore = defineStore("library", {
  state: () => ({ games: [], stats: null, loading: false }),
  actions: {
    async fetchGames(params) {
      this.loading = true;
      try {
        this.games = (await api.listGames(params)).items;
      } finally {
        this.loading = false;
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
