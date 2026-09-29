import { createRouter, createWebHistory } from "vue-router";
import { getActivePinia } from "pinia";
import { useAuthStore } from "../stores/auth";

const routes = [
  {
    path: "/",
    component: () => import("../mobile/layouts/MobileLayout.vue"),
    children: [
      { path: "", component: () => import("../mobile/views/MobileHomeView.vue") },
    ],
  },
  { path: "/login", component: () => import("../views/LoginView.vue") },
  { path: "/:pathMatch(.*)*", redirect: "/" },
];

const router = createRouter({ history: createWebHistory(), routes });

router.beforeEach(async (to) => {
  const pinia = getActivePinia();
  if (!pinia) return true;
  const auth = useAuthStore(pinia);
  await auth.ensureReady();
  if (auth.error) return true;
  if (!auth.authRequired) {
    return to.path === "/login" ? "/" : true;
  }
  if (to.path === "/login") return auth.authenticated ? "/" : true;
  if (!auth.authenticated) {
    return { path: "/login", query: { redirect: to.fullPath } };
  }
  return true;
});

export default router;
