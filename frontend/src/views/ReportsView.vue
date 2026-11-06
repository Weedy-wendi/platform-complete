<script setup lang="ts">
import { computed, ref } from "vue";
import { useI18n } from "vue-i18n";
import { apiDownload, apiFetch, apiText, idempotencyKey } from "@/api/client";
import { describeError } from "@/api/errors";
import { formatUtcTimestamp } from "@/i18n/format";
import { renderMarkdown } from "@/utils/markdown";
import { absoluteShareUrl } from "@/utils/share";

type ReportFormat = "json" | "markdown" | "csv" | "junit";

const REPORT_FORMATS: ReportFormat[] = ["json", "markdown", "csv", "junit"];
const ACCEPT: Record<ReportFormat, string> = {
  json: "application/json",
  markdown: "text/markdown",
  csv: "text/csv",
  junit: "application/xml",
};
const EXTENSION: Record<ReportFormat, string> = {
  json: "json",
  markdown: "md",
  csv: "csv",
  junit: "xml",
};
const SHARE_TTL_SECONDS = 3600;

const { t, locale } = useI18n();
const runId = ref("");
const format = ref<ReportFormat>("markdown");
const content = ref("");
const markdownHtml = ref("");
const loading = ref(false);
const loaded = ref(false);
const loadError = ref<unknown>(null);
const exportError = ref<unknown>(null);
const shareError = ref<unknown>(null);
const copyError = ref(false);
const copied = ref(false);
const sharePath = ref("");
const shareExpiry = ref<Date | null>(null);
const sharing = ref(false);

const errorText = computed(() => (loadError.value ? describeError(loadError.value, t) : ""));
const exportErrorText = computed(() => (exportError.value ? describeError(exportError.value, t) : ""));
const shareErrorText = computed(() => (shareError.value ? describeError(shareError.value, t) : ""));
const shareUrl = computed(() => absoluteShareUrl(sharePath.value));
const shareExpiryText = computed(() =>
  shareExpiry.value ? formatUtcTimestamp(shareExpiry.value, locale.value) : "",
);
const canLoad = computed(() => runId.value.trim().length > 0);

function reportPath(id: string, selected: ReportFormat): string {
  return `/reports/${encodeURIComponent(id)}?format=${selected}`;
}

function filename(id: string, selected: ReportFormat): string {
  return `report-${id}.${EXTENSION[selected]}`;
}

function resetResult() {
  content.value = "";
  markdownHtml.value = "";
  loaded.value = false;
  loadError.value = null;
  exportError.value = null;
  shareError.value = null;
  copyError.value = false;
  copied.value = false;
  sharePath.value = "";
  shareExpiry.value = null;
}

async function load() {
  const id = runId.value.trim();
  if (!id) return;
  resetResult();
  loading.value = true;
  try {
    if (format.value === "json") {
      const payload = await apiFetch<unknown>(reportPath(id, "json"));
      content.value = JSON.stringify(payload, null, 2);
    } else if (format.value === "markdown") {
      const text = await apiText(reportPath(id, "markdown"), {
        headers: { Accept: ACCEPT.markdown },
      });
      content.value = text;
      markdownHtml.value = renderMarkdown(text);
    } else {
      content.value = await apiText(reportPath(id, format.value), {
        headers: { Accept: ACCEPT[format.value] },
      });
    }
    loaded.value = true;
  } catch (exc) {
    loadError.value = exc;
  } finally {
    loading.value = false;
  }
}

async function download(selected: ReportFormat) {
  const id = runId.value.trim();
  if (!id) return;
  exportError.value = null;
  try {
    await apiDownload(reportPath(id, selected), filename(id, selected), {
      headers: { Accept: ACCEPT[selected] },
    });
  } catch (exc) {
    exportError.value = exc;
  }
}

async function createShare() {
  const id = runId.value.trim();
  if (!id) return;
  shareError.value = null;
  copyError.value = false;
  copied.value = false;
  sharing.value = true;
  try {
    const payload = await apiFetch<Record<string, unknown>>(
      `/reports/${encodeURIComponent(id)}/share`,
      {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey() },
        body: JSON.stringify({ ttl_seconds: SHARE_TTL_SECONDS }),
      },
    );
    const url = payload.url ?? payload.share_url ?? payload.shareUrl;
    if (typeof url !== "string" || !url) {
      throw new Error(t("reports.shareFailed"));
    }
    sharePath.value = url;
    const expiresAt = payload.expires_at ?? payload.expiresAt;
    const expiresIn = payload.expires_in ?? payload.expiresIn;
    if (typeof expiresAt === "string") {
      shareExpiry.value = new Date(expiresAt);
    } else if (typeof expiresIn === "number") {
      shareExpiry.value = new Date(Date.now() + expiresIn * 1000);
    } else {
      shareExpiry.value = new Date(Date.now() + SHARE_TTL_SECONDS * 1000);
    }
  } catch (exc) {
    shareError.value = exc;
  } finally {
    sharing.value = false;
  }
}

function fallbackCopy(text: string): boolean {
  if (typeof document === "undefined") return false;
  const area = document.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  area.style.position = "fixed";
  area.style.opacity = "0";
  document.body.appendChild(area);
  area.select();
  try {
    return typeof document.execCommand === "function" && document.execCommand("copy");
  } catch {
    return false;
  } finally {
    area.remove();
  }
}

async function copyShareUrl() {
  if (!shareUrl.value) return;
  copyError.value = false;
  copied.value = false;
  try {
    if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(shareUrl.value);
    } else if (!fallbackCopy(shareUrl.value)) {
      throw new Error(t("reports.copyFailed"));
    }
    copied.value = true;
  } catch (exc) {
    copyError.value = true;
    shareError.value = exc;
  }
}
</script>

<template>
  <section>
    <h1>{{ t("reports.title") }}</h1>

    <div class="list-toolbar">
      <el-input
        v-model="runId"
        class="inline"
        data-test="run-id"
        :aria-label="t('reports.runId')"
        :placeholder="t('reports.runIdPlaceholder')"
        @keyup.enter="load"
      />
      <el-select v-model="format" class="inline" :aria-label="t('reports.format')" data-test="format">
        <el-option
          v-for="item in REPORT_FORMATS"
          :key="item"
          :label="t(`reports.formats.${item}`)"
          :value="item"
        />
      </el-select>
      <el-button
        type="primary"
        :loading="loading"
        :disabled="!canLoad"
        data-test="load-report"
        @click="load"
      >
        {{ t("reports.load") }}
      </el-button>
    </div>

    <el-alert v-if="errorText" :title="errorText" type="error" show-icon data-test="report-error" />
    <el-alert
      v-if="exportErrorText"
      :title="`${t('reports.downloadFailed')}: ${exportErrorText}`"
      type="error"
      show-icon
      data-test="export-error"
    />

    <div class="list-toolbar">
      <span class="muted">{{ t("reports.export") }}</span>
      <el-button data-test="export-json" @click="download('json')">
        {{ t("reports.downloadJson") }}
      </el-button>
      <el-button data-test="export-csv" @click="download('csv')">
        {{ t("reports.downloadCsv") }}
      </el-button>
      <el-button data-test="export-junit" @click="download('junit')">
        {{ t("reports.downloadJunit") }}
      </el-button>
      <el-button data-test="export-markdown" @click="download('markdown')">
        {{ t("reports.downloadMarkdown") }}
      </el-button>
    </div>

    <el-card v-if="loaded" class="report-card">
      <h2>{{ format === "markdown" ? t("reports.previewMarkdown") : t("reports.rawPreview") }}</h2>
      <article
        v-if="format === 'markdown'"
        class="markdown-body"
        data-test="markdown-preview"
        v-html="markdownHtml"
      ></article>
      <pre v-else class="json" data-test="raw-report">{{ content }}</pre>
    </el-card>

    <p v-else-if="!loading" class="empty">{{ t("reports.empty") }}</p>

    <el-card class="share-card">
      <h2>{{ t("reports.shareTitle") }}</h2>
      <el-button
        type="primary"
        :loading="sharing"
        :disabled="!canLoad"
        data-test="share"
        @click="createShare"
      >
        {{ t("reports.share") }}
      </el-button>

      <el-alert
        v-if="shareErrorText"
        :title="shareErrorText"
        type="error"
        show-icon
        data-test="share-error"
      />

      <div v-if="shareUrl" class="share-result">
        <el-alert :title="t('reports.shareCreated')" type="success" show-icon />
        <el-input
          :model-value="shareUrl"
          readonly
          class="share-url"
          data-test="share-url"
          :aria-label="t('reports.shareTitle')"
        />
        <el-button data-test="copy-share" @click="copyShareUrl">{{ t("reports.copy") }}</el-button>
        <p v-if="copied" class="muted" data-test="copy-status">{{ t("reports.copied") }}</p>
        <p v-if="copyError" class="muted" data-test="copy-status">{{ t("reports.copyFailed") }}</p>
        <p v-if="shareExpiryText" class="muted" data-test="share-expiry">
          {{ t("reports.shareExpires", { time: shareExpiryText }) }}
        </p>
      </div>
      <p v-else-if="!sharing" class="muted">{{ t("reports.shareUnavailable") }}</p>
    </el-card>
  </section>
</template>

<style scoped>
.share-card {
  margin-top: 16px;
}

.share-result {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
}

.share-url {
  width: min(640px, 100%);
}

.markdown-body {
  line-height: 1.65;
  overflow-wrap: anywhere;
}

.markdown-body :deep(pre) {
  background: #0f172a;
  color: #e2e8f0;
  padding: 12px;
  border-radius: 6px;
  overflow: auto;
}

.markdown-body :deep(code) {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.markdown-body :deep(table) {
  border-collapse: collapse;
}

.markdown-body :deep(th),
.markdown-body :deep(td) {
  border: 1px solid var(--pingce-border);
  padding: 6px 10px;
}
</style>
