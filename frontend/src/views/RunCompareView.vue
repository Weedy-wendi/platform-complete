<script setup lang="ts">
import { ref } from "vue";
import { useRoute } from "vue-router";
import { apiFetch } from "@/api/client";

const route = useRoute();
const baseline = ref("");
const payload = ref<unknown>(null);
const error = ref("");

async function load() {
  error.value = "";
  try {
    payload.value = await apiFetch<unknown>(
      `/runs/${route.params.id}/compare?baseline=${encodeURIComponent(baseline.value)}`,
    );
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : "对比失败";
  }
}
</script>

<template>
  <section>
    <h1>Run 对比</h1>
    <el-input v-model="baseline" placeholder="基线 Run ID" class="inline" />
    <el-button @click="load">对比</el-button>
    <el-alert v-if="error" :title="error" type="error" show-icon />
    <pre v-if="payload" class="json">{{ JSON.stringify(payload, null, 2) }}</pre>
  </section>
</template>
