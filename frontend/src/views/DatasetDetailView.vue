<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { useI18n } from "vue-i18n";
import { apiFetch } from "@/api/client";
import { describeError } from "@/api/errors";
import {
  buildDatasetPreview,
  displayCell,
  type DatasetPreview,
  type SchemaField,
} from "@/utils/dataset";

const route = useRoute();
const { t } = useI18n();
const version = ref("");
const payload = ref<unknown>(null);
const preview = ref<DatasetPreview>({ schema: [], rows: [], columns: [] });
const loading = ref(false);
const loaded = ref(false);
const loadError = ref<unknown>(null);
const showRaw = ref(false);

const datasetId = computed(() => String(route.params.id ?? ""));
const errorText = computed(() => (loadError.value ? describeError(loadError.value, t) : ""));
const endpoint = computed(() => {
  const selected = version.value.trim() || "latest";
  return `/datasets/${encodeURIComponent(datasetId.value)}/versions/${encodeURIComponent(selected)}/samples?limit=20`;
});
const showRawFallback = computed(
  () => showRaw.value || (!preview.value.schema.length && !preview.value.rows.length),
);

function cellValue(row: Record<string, unknown>, column: string): string {
  return displayCell(row[column]);
}

async function load() {
  loading.value = true;
  loadError.value = null;
  try {
    payload.value = await apiFetch<unknown>(endpoint.value);
    preview.value = buildDatasetPreview(payload.value);
    loaded.value = true;
  } catch (exc) {
    loadError.value = exc;
    payload.value = null;
    preview.value = { schema: [], rows: [], columns: [] };
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>

<template>
  <section>
    <h1>{{ t("datasets.detailTitle") }}</h1>

    <div class="list-toolbar">
      <span class="muted">{{ datasetId }}</span>
      <el-input
        v-model="version"
        class="inline"
        data-test="dataset-version"
        :aria-label="t('datasets.version')"
        :placeholder="t('datasets.versionPlaceholder')"
        @keyup.enter="load"
      />
      <el-button type="primary" :loading="loading" data-test="load-dataset" @click="load">
        {{ t("datasets.load") }}
      </el-button>
      <el-button v-if="payload" data-test="toggle-raw" @click="showRaw = !showRaw">
        {{ showRaw ? t("datasets.hideRaw") : t("datasets.showRaw") }}
      </el-button>
    </div>

    <el-alert v-if="errorText" :title="errorText" type="error" show-icon data-test="dataset-error" />
    <el-alert v-if="preview.rows.length" :title="t('datasets.maskedNotice')" type="info" show-icon />

    <template v-if="loaded">
      <h2>{{ t("datasets.schema") }}</h2>
      <el-table
        v-if="preview.schema.length"
        :data="preview.schema"
        class="table"
        data-test="schema-table"
      >
        <el-table-column prop="field" :label="t('datasets.field')" show-overflow-tooltip />
        <el-table-column prop="type" :label="t('datasets.type')" show-overflow-tooltip />
        <el-table-column :label="t('datasets.nullable')" width="120">
          <template #default="{ row }: { row: SchemaField }">
            <el-tag :type="row.nullable ? 'info' : 'success'" size="small">
              {{ row.nullable ? t("datasets.yes") : t("datasets.no") }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
      <p v-else class="muted">{{ t("datasets.noSchema") }}</p>

      <h2>{{ t("datasets.samples") }}</h2>
      <el-table
        v-if="preview.rows.length"
        :data="preview.rows"
        class="table"
        data-test="sample-table"
      >
        <el-table-column
          v-for="column in preview.columns"
          :key="column"
          :label="column"
          show-overflow-tooltip
        >
          <template #default="{ row }: { row: Record<string, unknown> }">
            {{ cellValue(row, column) }}
          </template>
        </el-table-column>
      </el-table>
      <p v-else class="muted">{{ t("datasets.noSamples") }}</p>

      <template v-if="showRawFallback && payload">
        <h2>{{ t("datasets.raw") }}</h2>
        <pre class="json" data-test="raw-dataset">{{ JSON.stringify(payload, null, 2) }}</pre>
      </template>
    </template>
    <p v-else-if="!loading && !errorText" class="empty">{{ t("datasets.load") }}</p>
  </section>
</template>
