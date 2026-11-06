import { createRouter, createWebHistory } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { useUiStore } from "@/stores/ui";
import { reportError } from "@/observability/errors";

const routes = [
  { path: "/login", component: () => import("@/views/LoginView.vue"), meta: { public: true, titleKey: "auth.title" } },
  { path: "/", component: () => import("@/views/DashboardView.vue"), meta: { titleKey: "nav.dashboard" } },
  { path: "/projects", component: () => import("@/views/ProjectsView.vue"), meta: { titleKey: "nav.projects" } },
  { path: "/projects/:id", component: () => import("@/views/ProjectDetailView.vue"), meta: { titleKey: "nav.projects" } },
  { path: "/datasets", component: () => import("@/views/DatasetsView.vue"), meta: { titleKey: "nav.datasets" } },
  { path: "/datasets/:id", component: () => import("@/views/DatasetDetailView.vue"), meta: { titleKey: "nav.datasets" } },
  { path: "/runs", component: () => import("@/views/RunsView.vue"), meta: { titleKey: "nav.runs" } },
  { path: "/runs/:id", component: () => import("@/views/RunDetailView.vue"), meta: { titleKey: "nav.runs" } },
  { path: "/runs/:id/compare", component: () => import("@/views/RunCompareView.vue"), meta: { titleKey: "nav.runs" } },
  { path: "/evaluators", component: () => import("@/views/EvaluatorsView.vue"), meta: { titleKey: "nav.evaluators" } },
  { path: "/suites", component: () => import("@/views/SuitesView.vue"), meta: { titleKey: "nav.suites" } },
  { path: "/gates", component: () => import("@/views/GatesView.vue"), meta: { titleKey: "nav.gates" } },
  { path: "/reports", component: () => import("@/views/ReportsView.vue"), meta: { titleKey: "nav.reports" } },
  { path: "/badcases", component: () => import("@/views/BadcasesView.vue"), meta: { titleKey: "nav.badcases" } },
  { path: "/functional", component: () => import("@/views/FunctionalView.vue"), meta: { titleKey: "nav.functional" } },
  {
    path: "/functional/:id",
    component: () => import("@/views/FunctionalRunDetailView.vue"),
    meta: { titleKey: "nav.functional" },
  },
  {
    path: "/admin",
    component: () => import("@/views/AdminView.vue"),
    meta: { titleKey: "nav.admin", scope: "admin:read" },
  },
  { path: "/settings", component: () => import("@/views/SettingsView.vue"), meta: { titleKey: "nav.settings" } },
  {
    path: "/403",
    component: () => import("@/views/ErrorView.vue"),
    meta: { public: true, status: 403, titleKey: "errors.forbidden" },
  },
  {
    path: "/404",
    component: () => import("@/views/ErrorView.vue"),
    meta: { public: true, status: 404, titleKey: "errors.notFoundTitle" },
  },
  { path: "/:pathMatch(.*)*", redirect: "/404" },
];

const router = createRouter({ history: createWebHistory(), routes });

router.beforeEach((to) => {
  const auth = useAuthStore();
  const ui = useUiStore();
  const titleKey = typeof to.meta.titleKey === "string" ? to.meta.titleKey : "app.title";
  ui.setTitleKey(titleKey);

  if (!to.meta.public && !auth.hasKey) return "/login";

  const scope = typeof to.meta.scope === "string" ? to.meta.scope : "";
  if (scope && !auth.can(scope)) return "/403";

  return true;
});

router.onError((error) => {
  reportError(error);
});

export default router;
