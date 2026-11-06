<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { useI18n } from "vue-i18n";
import { apiFetch } from "@/api/client";
import { describeError } from "@/api/errors";
import {
  formatDuration,
  isPassedVisual,
  normalizeSteps,
  statusTagType,
  type EvidenceLink,
  type FunctionalStep,
} from "@/utils/functional";
import { formatPercent, formatUtcTimestamp } from "@/i18n/format";

const route = useRoute();
const { t, locale } = useI18n();
const payload = ref<Record<string, unknown> | null>(null);
const loadError = ref<unknown>(null);

const runId = computed(() => String(route.params.id ?? ""));
const errorText = computed(() => (loadError.value ? describeError(loadError.value, t) : ""));
const steps = computed<FunctionalStep[]>(() => normalizeSteps(payload.value));
const runStatus = computed(() => String(payload.value?.status ?? "unknown"));
const startedAt = computed(() => {
  const value = payload.value?.started_at ?? payload.value?.created_at;
  return typeof value === "string" ? value : "";
});

function evidenceLabel(link: EvidenceLink): string {
  return t(`functional.evidenceKinds.${link.kind}`);
}

function evidenceHref(ref: string): string {
  return /^(https?:\/\/|\/|blob:)/i.test(ref) ? ref : "";
}

function visualPassed(step: FunctionalStep): boolean {
  return isPassedVisual(step);
}

async function load() {
  loadError.value = null;
  try {
    payload.value = await apiFetch<Record<string, unknown>>(
      `/functional/runs/${encodeURIComponent(runId.value)}`,
    );
  } catch (exc) {
    loadError.value = exc;
    payload.value = null;
  }
}

onMounted(load);
</script>

<template>
  <section>
    <h1>{{ t("functional.detailTitle") }}</h1>
    <p class="muted">{{ runId }}</p>

    <el-alert v-if="errorText" :title="errorText" type="error" show-icon data-test="functional-error" />

    <el-card v-if="payload">
      <div class="run-meta">
        <span>{{ t("functional.status") }}：</span>
        <el-tag :type="statusTagType(runStatus)" data-test="functional-status">
          {{ runStatus }}
        </el-tag>
        <span v-if="startedAt" class="muted">
          {{ t("functional.startedAt") }}：{{ formatUtcTimestamp(startedAt, locale) }}
        </span>
      </div>
    </el-card>

    <h2>{{ t("functional.steps") }}</h2>
    <el-table
      v-if="steps.length"
      :data="steps"
      class="table"
      data-test="functional-steps"
    >
      <el-table-column prop="name" :label="t('functional.step')" show-overflow-tooltip />
      <el-table-column :label="t('functional.status')" width="130">
        <template #default="{ row }: { row: FunctionalStep }">
          <el-tag :type="statusTagType(row.status)" size="small">{{ row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column :label="t('functional.duration')" width="120">
        <template #default="{ row }: { row: FunctionalStep }">
          {{ formatDuration(row.durationMs, locale) }}
        </template>
      </el-table-column>
      <el-table-column :label="t('functional.evidence')">
        <template #default="{ row }: { row: FunctionalStep }">
          <div v-if="row.evidence.length" class="evidence-list">
            <span v-for="link in row.evidence" :key="link.ref" class="evidence-item">
              <a
                v-if="evidenceHref(link.ref)"
                :href="evidenceHref(link.ref)"
                target="_blank"
                rel="noopener noreferrer"
                data-test="evidence-link"
              >
                {{ evidenceLabel(link) }}
              </a>
              <template v-else>
                <span>{{ evidenceLabel(link) }}：</span>
                <code data-test="evidence-ref">{{ link.ref }}</code>
              </template>
            </span>
          </div>
          <span v-else class="muted">{{ t("functional.noEvidence") }}</span>
        </template>
      </el-table-column>
      <el-table-column :label="t('functional.visualDiff')" width="220">
        <template #default="{ row }: { row: FunctionalStep }">
          <div v-if="row.mismatchRatio !== null || row.visualRef" class="visual-diff">
            <span v-if="row.mismatchRatio !== null" data-test="mismatch-ratio">
              {{ t("functional.mismatchRatio") }}：{{ formatPercent(row.mismatchRatio, locale) }}
            </span>
            <el-tag
              v-if="row.mismatchRatio !== null || row.visualPassed !== null"
              :type="visualPassed(row) ? 'success' : 'danger'"
              size="small"
              data-test="visual-status"
            >
              {{ visualPassed(row) ? t("functional.visualPassed") : t("functional.visualFailed") }}
            </el-tag>
            <a
              v-if="row.visualRef && evidenceHref(row.visualRef)"
              :href="evidenceHref(row.visualRef)"
              target="_blank"
              rel="noopener noreferrer"
              data-test="visual-link"
            >
              {{ t("functional.visualDiff") }}
            </a>
            <code v-else-if="row.visualRef">{{ row.visualRef }}</code>
          </div>
          <span v-else class="muted">{{ t("functional.noVisual") }}</span>
        </template>
      </el-table-column>
    </el-table>
    <p v-else-if="!errorText" class="empty">{{ t("functional.empty") }}</p>

    <template v-if="payload && !steps.length">
      <h2>{{ t("functional.raw") }}</h2>
      <pre class="json" data-test="functional-raw">{{ JSON.stringify(payload, null, 2) }}</pre>
    </template>
  </section>
</template>

<style scoped>
.run-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
}

.evidence-list,
.visual-diff {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.evidence-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
</style>
