import { createRouter, createWebHistory } from "vue-router";
import { getActivePinia } from "pinia";
import { useAuthStore } from "../stores/auth";

const routes = [
  { path: "/", redirect: "/library" },
  { path: "/login", component: () => import("../views/LoginView.vue") },
  { path: "/library", component: () => import("../views/LibraryView.vue") },
  { path: "/editor/:id?", component: () => import("../views/EditorView.vue") },
  { path: "/practice/:id", component: () => import("../views/PracticeView.vue") },
  { path: "/play", component: () => import("../views/PlayView.vue") },
  { path: "/review", component: () => import("../views/ReviewView.vue") },
  {
    path: "/m",
    component: () => import("../mobile/layouts/MobileLayout.vue"),
    children: [
      { path: "", component: () => import("../mobile/views/MobileHomeView.vue") },
    ],
  },
  { path: "/m/:pathMatch(.*)*", redirect: "/m" },
];

const router = createRouter({ history: createWebHistory(), routes });

router.beforeEach(async (to) => {
  const pinia = getActivePinia();
  if (!pinia) return true;
  const auth = useAuthStore(pinia);
  await auth.ensureReady();
  if (auth.error) return true;
  if (!auth.authRequired) {
    return to.path === "/login" ? "/library" : true;
  }
  if (to.path === "/login") return auth.authenticated ? "/library" : true;
  if (!auth.authenticated) return "/login";
  return true;
});

export default router;
