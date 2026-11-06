<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import { apiFetch } from "@/api/client";
import { useUiStore } from "@/stores/ui";
import { formatNumber } from "@/i18n/format";

const { t, locale } = useI18n();
const projects = ref(0);
const runs = ref(0);
const ui = useUiStore();

onMounted(async () => {
  try {
    const [p, r] = await Promise.all([
      apiFetch<{ items?: unknown[] }>("/projects"),
      apiFetch<{ items?: unknown[] }>("/runs"),
    ]);
    projects.value = p.items?.length ?? 0;
    runs.value = r.items?.length ?? 0;
  } catch {
    ui.setError(t("dashboard.loadError"));
  }
});
</script>

<template>
  <section>
    <h1>{{ t("dashboard.title") }}</h1>
    <el-row :gutter="16">
      <el-col :xs="24" :sm="8">
        <el-card>
          <h3>{{ t("dashboard.projects") }}</h3>
          <p class="metric">{{ formatNumber(projects, locale) }}</p>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="8">
        <el-card>
          <h3>{{ t("dashboard.runs") }}</h3>
          <p class="metric">{{ formatNumber(runs, locale) }}</p>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="8">
        <el-card>
          <h3>{{ t("dashboard.status") }}</h3>
          <p>{{ t("dashboard.statusText") }}</p>
        </el-card>
      </el-col>
    </el-row>
  </section>
</template>
