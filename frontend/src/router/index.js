import { createRouter, createWebHistory } from "vue-router";

const routes = [
  { path: "/", redirect: "/library" },
  { path: "/library", component: () => import("../views/LibraryView.vue") },
  { path: "/editor/:id?", component: () => import("../views/EditorView.vue") },
  { path: "/practice/:id", component: () => import("../views/PracticeView.vue") },
  { path: "/review", component: () => import("../views/ReviewView.vue") },
];

export default createRouter({ history: createWebHistory(), routes });
