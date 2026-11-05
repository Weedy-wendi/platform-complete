<script setup lang="ts">
import { computed, onMounted } from "vue";
import { useI18n } from "vue-i18n";
import { describeError } from "@/api/errors";
import { usePaginatedList } from "@/composables/usePaginatedList";
import { formatUtcTimestamp } from "@/i18n/format";
import { formatDuration, statusTagType } from "@/utils/functional";

const { t, locale } = useI18n();
const list = usePaginatedList<Record<string, unknown>>({ endpoint: () => "/functional/runs" });
const errorText = computed(() => (list.error.value ? describeError(list.error.value, t) : ""));

function rowId(row: Record<string, unknown>): string {
  return String(row.run_id ?? row.id ?? "");
}

function rowStatus(row: Record<string, unknown>): string {
  return String(row.status ?? "unknown");
}

function rowStarted(row: Record<string, unknown>): string {
  return typeof row.started_at === "string"
    ? row.started_at
    : typeof row.created_at === "string"
      ? row.created_at
      : "";
}

function rowDuration(row: Record<string, unknown>): number | null {
  const raw = row.duration_ms ?? row.durationMs;
  if (typeof raw === "number" && Number.isFinite(raw)) return raw;
  if (typeof raw === "string" && raw.trim()) {
    const parsed = Number(raw);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

onMounted(() => {
  void list.reload();
});
</script>

<template>
  <section>
    <h1>{{ t("functional.listTitle") }}</h1>

    <div class="list-toolbar">
      <el-button :loading="list.loading.value" @click="list.reload()">
        {{ t("common.refresh") }}
      </el-button>
    </div>

    <el-alert v-if="errorText" :title="errorText" type="error" show-icon data-test="functional-list-error" />

    <el-table
      v-if="list.items.value.length"
      :data="list.items.value"
      class="table"
      data-test="functional-runs-table"
    >
      <el-table-column :label="t('functional.runId')" min-width="200">
        <template #default="{ row }: { row: Record<string, unknown> }">
          <router-link
            v-if="rowId(row)"
            :to="`/functional/${encodeURIComponent(rowId(row))}`"
            data-test="functional-run-link"
          >
            {{ rowId(row) }}
          </router-link>
          <span v-else>{{ t("common.notAvailable") }}</span>
        </template>
      </el-table-column>
      <el-table-column :label="t('functional.status')" width="130">
        <template #default="{ row }: { row: Record<string, unknown> }">
          <el-tag :type="statusTagType(rowStatus(row))" size="small">{{ rowStatus(row) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column :label="t('functional.startedAt')" min-width="200">
        <template #default="{ row }: { row: Record<string, unknown> }">
          {{ rowStarted(row) ? formatUtcTimestamp(rowStarted(row), locale) : t("common.notAvailable") }}
        </template>
      </el-table-column>
      <el-table-column :label="t('functional.duration')" width="120">
        <template #default="{ row }: { row: Record<string, unknown> }">
          {{ formatDuration(rowDuration(row), locale) }}
        </template>
      </el-table-column>
    </el-table>
    <p v-else-if="!list.loading.value && !errorText" class="empty">{{ t("common.empty") }}</p>

    <div class="list-footer" aria-live="polite">
      <span class="muted">{{ t("common.loadedCount", { count: list.items.value.length }) }}</span>
      <el-button
        v-if="list.hasMore.value && !errorText"
        :loading="list.loading.value"
        @click="list.loadMore()"
      >
        {{ t("common.loadMore") }}
      </el-button>
    </div>
  </section>
</template>
