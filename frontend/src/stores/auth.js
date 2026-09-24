import { defineStore } from "pinia";
import { api } from "../api";

export const useAuthStore = defineStore("auth", {
  state: () => ({
    authRequired: false,
    authenticated: false,
    ready: false,
    loading: false,
  }),
  actions: {
    async fetchMe() {
      const data = await api.authMe();
      this.authRequired = data.auth_required;
      this.authenticated = data.authenticated;
      this.ready = true;
    },
    async ensureReady() {
      if (this.ready) return;
      if (this._pending) return this._pending;
      this._pending = (async () => {
        try {
          await this.fetchMe();
        } catch {
          this.ready = true;
        } finally {
          this._pending = null;
        }
      })();
      return this._pending;
    },
    async login(password) {
      this.loading = true;
      try {
        await api.login(password);
        this.authenticated = true;
      } catch (err) {
        this.authenticated = false;
        throw err;
      } finally {
        this.loading = false;
      }
    },
    async logout() {
      await api.logout();
      this.authenticated = false;
    },
    markUnauthorized() {
      this.authenticated = false;
    },
  },
});
