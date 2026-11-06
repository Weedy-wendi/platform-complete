<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { useI18n } from "vue-i18n";
import { apiFetch } from "@/api/client";
import { describeError } from "@/api/errors";
import PaginatedList from "@/components/PaginatedList.vue";
import PermissionGate from "@/components/PermissionGate.vue";
import { formatCurrency, formatPercent, formatUtcTimestamp } from "@/i18n/format";
import { useAuthStore } from "@/stores/auth";

const { t, locale } = useI18n();
const auth = useAuthStore();
const route = useRoute();
const run = ref<Record<string, unknown> | null>(null);
const loadError = ref<unknown>(null);
const cancelError = ref<unknown>(null);

const runId = computed(() => String(route.params.id ?? ""));
const itemsEndpoint = computed(() => `/runs/${runId.value}/items`);
const loadErrorText = computed(() => (loadError.value ? describeError(loadError.value, t) : ""));
const cancelErrorText = computed(() => (cancelError.value ? describeError(cancelError.value, t) : ""));

async function load() {
  loadError.value = null;
  try {
    run.value = await apiFetch<Record<string, unknown>>(`/runs/${runId.value}`);
  } catch (exc) {
    loadError.value = exc;
  }
}

async function cancelRun() {
  cancelError.value = null;
  try {
    await apiFetch(`/runs/${runId.value}/cancel`, { method: "POST" });
    await load();
  } catch (exc) {
    cancelError.value = exc;
  }
}

onMounted(load);
</script>

<template>
  <section>
    <h1>{{ t("runs.detailTitle") }}</h1>
    <el-alert v-if="loadErrorText" :title="loadErrorText" type="error" show-icon />
    <el-alert v-if="cancelErrorText" :title="cancelErrorText" type="error" show-icon />
    <el-card v-if="run">
      <p>{{ t("runs.status") }}：{{ run.status ?? t("common.notAvailable") }}</p>
      <p>
        {{ t("runs.progress") }}：
        {{ formatPercent(typeof run.progress === "number" ? run.progress : null, locale) }}
      </p>
      <p>
        {{ t("runs.cost") }}：
        {{ formatCurrency(typeof run.cost_usd === "number" ? run.cost_usd : null, locale) }}
      </p>
      <p>{{ t("runs.manifest") }}：{{ run.manifest_hash ?? t("common.notAvailable") }}</p>
      <p v-if="run.created_at">
        {{ t("runs.created") }}：{{ formatUtcTimestamp(run.created_at as string, locale) }}
      </p>
      <p v-if="run.updated_at">
        {{ t("runs.updated") }}：{{ formatUtcTimestamp(run.updated_at as string, locale) }}
      </p>
      <PermissionGate scope="runs:write" mode="disable">
        <el-button type="danger" @click="cancelRun">{{ t("runs.cancel") }}</el-button>
      </PermissionGate>
      <el-button @click="load">{{ t("runs.refresh") }}</el-button>
      <p v-if="!auth.can('runs:write')" class="muted">{{ t("runs.cancelForbidden") }}</p>
    </el-card>
    <h2>{{ t("runs.samples") }}</h2>
    <PaginatedList :endpoint="itemsEndpoint" :aria-label="t('runs.samples')" />
  </section>
</template>
