import { createApp } from "vue";
import { createPinia } from "pinia";
import App from "./App.vue";
import router from "./router";
import { useAuthStore } from "./stores/auth";

const app = createApp(App);
const pinia = createPinia();
app.use(pinia).use(router).mount("#app");

window.addEventListener("app-unauthorized", () => {
  const auth = useAuthStore(pinia);
  auth.markUnauthorized();
  if (router.currentRoute.value.path !== "/login") {
    router.push("/login");
  }
});
