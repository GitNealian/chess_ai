import { createRouter, createWebHistory } from "vue-router";

const routes = [
  { path: "/", redirect: "/library" },
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

export default createRouter({ history: createWebHistory(), routes });
