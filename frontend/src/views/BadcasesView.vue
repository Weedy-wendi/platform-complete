<script setup lang="ts">
import { ref } from "vue";
import { apiFetch } from "@/api/client";

const query = ref("");
const payload = ref<unknown>(null);
const error = ref("");

async function search() {
  error.value = "";
  try {
    payload.value = await apiFetch<unknown>("/badcases/search", {
      method: "POST",
      body: JSON.stringify({ query: query.value, limit: 20 }),
    });
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : "搜索失败";
  }
}
</script>

<template>
  <section>
    <h1>Badcase 检索</h1>
    <el-input v-model="query" placeholder="语义检索" class="inline" @keyup.enter="search" />
    <el-button @click="search">搜索</el-button>
    <el-alert v-if="error" :title="error" type="error" show-icon />
    <el-alert
      v-if="payload && (payload as Record<string, unknown>).degraded"
      title="语义检索已降级为关键词检索"
      type="warning"
      show-icon
    />
    <pre v-if="payload" class="json">{{ JSON.stringify(payload, null, 2) }}</pre>
  </section>
</template>
