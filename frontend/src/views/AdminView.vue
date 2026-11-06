<script setup lang="ts">
import { computed, ref } from "vue";
import { useI18n } from "vue-i18n";
import { apiFetch } from "@/api/client";
import { describeError } from "@/api/errors";
import PermissionGate from "@/components/PermissionGate.vue";

const { t } = useI18n();
const endpoint = ref("/admin/tenants");
const payload = ref<unknown>(null);
const apiError = ref<unknown>(null);

const errorText = computed(() => (apiError.value ? describeError(apiError.value, t) : ""));

async function load() {
  apiError.value = null;
  try {
    payload.value = await apiFetch<unknown>(endpoint.value);
  } catch (exc) {
    apiError.value = exc;
  }
}
</script>

<template>
  <section>
    <h1>{{ t("admin.title") }}</h1>
    <el-alert :title="t('admin.notice')" type="info" show-icon />
    <PermissionGate scope="admin:read">
      <template #fallback>
        <el-alert :title="t('errors.forbidden')" type="error" show-icon />
      </template>
      <el-input v-model="endpoint" class="inline" :aria-label="t('admin.endpoint')" />
      <el-button @click="load">{{ t("admin.load") }}</el-button>
      <el-alert v-if="errorText" :title="errorText" type="error" show-icon />
      <pre v-if="payload" class="json">{{ JSON.stringify(payload, null, 2) }}</pre>
    </PermissionGate>
  </section>
</template>
