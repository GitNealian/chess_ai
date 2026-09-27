import { defineStore } from "pinia";
import { api } from "../../api";

export const useMobileHomeStore = defineStore("mobileHome", {
  state: () => ({
    pickerOpen: false,
    settingsOpen: false,
    currentGame: null,
    favorited: false,
  }),
  actions: {
    openPicker() {
      this.pickerOpen = true;
    },
    closePicker() {
      this.pickerOpen = false;
    },
    openSettings() {
      this.settingsOpen = true;
    },
    closeSettings() {
      this.settingsOpen = false;
    },
    setGame(game) {
      this.currentGame = game;
      this.favorited = !!game.favorited;
      api
        .openGame(game.id)
        .then((res) => {
          this.favorited = !!res.favorited;
        })
        .catch(() => {});
    },
    clearGame() {
      this.currentGame = null;
      this.favorited = false;
    },
    async toggleFavorite() {
      if (!this.currentGame) return;
      try {
        const res = await api.favoriteGame(this.currentGame.id);
        this.favorited = !!res.favorited;
      } catch {
        // 收藏失败静默，保持原状态
      }
    },
  },
});