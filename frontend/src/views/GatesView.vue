<script setup lang="ts">
import { computed, ref } from "vue";
import { useI18n } from "vue-i18n";
import { apiFetch } from "@/api/client";
import { describeError } from "@/api/errors";
import { gateRowClass, gateSummary, normalizeGateRules, type GateRule } from "@/utils/gate";

const { t } = useI18n();
const suiteId = ref("");
const runId = ref("");
const rules = ref<GateRule[]>([]);
const loading = ref(false);
const loaded = ref(false);
const loadError = ref<unknown>(null);

const errorText = computed(() => (loadError.value ? describeError(loadError.value, t) : ""));
const summary = computed(() => gateSummary(rules.value));
const canQuery = computed(() => suiteId.value.trim().length > 0 && runId.value.trim().length > 0);

function rowClassName({ row }: { row: GateRule }): string {
  return gateRowClass(row);
}

function evidenceHref(ref: string): string {
  return /^(https?:\/\/|\/)/i.test(ref) ? ref : "";
}

async function load() {
  if (!canQuery.value) return;
  loading.value = true;
  loadError.value = null;
  loaded.value = false;
  try {
    const payload = await apiFetch<unknown>(
      `/gates/${encodeURIComponent(suiteId.value.trim())}/${encodeURIComponent(runId.value.trim())}`,
    );
    rules.value = normalizeGateRules(payload);
    loaded.value = true;
  } catch (exc) {
    loadError.value = exc;
    rules.value = [];
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <section>
    <h1>{{ t("gates.title") }}</h1>

    <div class="list-toolbar">
      <el-input
        v-model="suiteId"
        class="inline"
        data-test="gate-suite"
        :aria-label="t('gates.suiteId')"
        :placeholder="t('gates.suiteId')"
      />
      <el-input
        v-model="runId"
        class="inline"
        data-test="gate-run"
        :aria-label="t('gates.runId')"
        :placeholder="t('gates.runId')"
        @keyup.enter="load"
      />
      <el-button type="primary" :loading="loading" :disabled="!canQuery" data-test="gate-query" @click="load">
        {{ t("gates.query") }}
      </el-button>
    </div>

    <el-alert v-if="errorText" :title="errorText" type="error" show-icon data-test="gate-error" />

    <template v-if="loaded">
      <el-alert
        v-if="summary.failed > 0"
        :title="t('gates.summaryFailed', { failed: summary.failed, total: summary.total })"
        type="error"
        show-icon
        data-test="gate-summary"
      />
      <el-alert
        v-else
        :title="t('gates.summaryPassed', { total: summary.total })"
        type="success"
        show-icon
        data-test="gate-summary"
      />

      <el-table
        v-if="rules.length"
        :data="rules"
        class="table"
        :row-class-name="rowClassName"
        data-test="gate-table"
      >
        <el-table-column prop="name" :label="t('gates.rule')" show-overflow-tooltip />
        <el-table-column prop="expected" :label="t('gates.expected')" show-overflow-tooltip />
        <el-table-column prop="actual" :label="t('gates.actual')" show-overflow-tooltip />
        <el-table-column :label="t('gates.result')" width="120">
          <template #default="{ row }: { row: GateRule }">
            <el-tag :type="row.passed ? 'success' : 'danger'" size="small">
              {{ row.passed ? t("gates.passed") : t("gates.failed") }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('gates.evidence')" show-overflow-tooltip>
          <template #default="{ row }: { row: GateRule }">
            <a
              v-if="row.evidenceRef && evidenceHref(row.evidenceRef)"
              :href="evidenceHref(row.evidenceRef)"
              target="_blank"
              rel="noopener noreferrer"
            >
              {{ row.evidenceRef }}
            </a>
            <template v-else-if="row.evidenceRef">{{ row.evidenceRef }}</template>
            <span v-else class="muted">{{ t("gates.noEvidence") }}</span>
          </template>
        </el-table-column>
      </el-table>
      <p v-else class="empty">{{ t("gates.empty") }}</p>
    </template>
    <p v-else-if="!loading && !errorText" class="empty">{{ t("gates.empty") }}</p>
  </section>
</template>

<style scoped>
:deep(.gate-row-failed) > td.el-table__cell {
  background: #fef2f2;
}

:deep(.gate-row-failed:hover) > td.el-table__cell {
  background: #fee2e2;
}
</style>
