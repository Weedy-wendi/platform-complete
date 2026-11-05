<script setup lang="ts">
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import { useAuthStore } from "@/stores/auth";

const emit = defineEmits<{ navigate: [] }>();
const auth = useAuthStore();
const route = useRoute();
const router = useRouter();
const { t } = useI18n();

const items = computed(() => [
  { path: "/", label: t("nav.dashboard") },
  { path: "/projects", label: t("nav.projects") },
  { path: "/datasets", label: t("nav.datasets") },
  { path: "/runs", label: t("nav.runs") },
  { path: "/evaluators", label: t("nav.evaluators") },
  { path: "/suites", label: t("nav.suites") },
  { path: "/gates", label: t("nav.gates") },
  { path: "/reports", label: t("nav.reports") },
  { path: "/badcases", label: t("nav.badcases") },
  { path: "/functional", label: t("nav.functional") },
  { path: "/admin", label: t("nav.admin"), scope: "admin:read" },
  { path: "/settings", label: t("nav.settings") },
]);

const visibleItems = computed(() => items.value.filter((item) => !item.scope || auth.can(item.scope)));

function go(path: string) {
  if (route.path !== path) router.push(path);
  emit("navigate");
}
</script>

<template>
  <nav :aria-label="t('a11y.mainNav')" class="nav-menu">
    <el-menu :default-active="route.path" class="nav-menu-list">
      <el-menu-item
        v-for="item in visibleItems"
        :key="item.path"
        :index="item.path"
        @click="go(item.path)"
      >
        {{ item.label }}
      </el-menu-item>
    </el-menu>
  </nav>
</template>
