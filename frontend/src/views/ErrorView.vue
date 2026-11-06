<script setup lang="ts">
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useI18n } from "vue-i18n";

const route = useRoute();
const router = useRouter();
const { t } = useI18n();

const status = computed(() => Number(route.meta.status ?? 404));
const title = computed(() => (status.value === 403 ? t("errors.forbidden") : t("errors.notFound")));
const icon = computed(() => (status.value === 403 ? "warning" : "info"));

function goHome() {
  void router.push("/");
}
</script>

<template>
  <el-result :icon="icon" :title="String(status)" :sub-title="title">
    <template #extra>
      <el-button type="primary" @click="goHome">{{ t("errors.backHome") }}</el-button>
    </template>
  </el-result>
</template>
