import { createApp } from "vue";
import { createPinia } from "pinia";
import App from "./App.vue";
import router from "./router";
import { useAuthStore } from "./stores/auth";

const app = createApp(App);
const pinia = createPinia();
app.use(pinia).use(router);

window.addEventListener("app-unauthorized", () => {
  const auth = useAuthStore(pinia);
  auth.markUnauthorized();
  if (router.currentRoute.value.path !== "/login") {
    router.push("/login");
  }
});

router.isReady().then(() => app.mount("#app"));
