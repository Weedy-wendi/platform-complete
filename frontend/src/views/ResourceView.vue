<script setup lang="ts">
import PaginatedList from "@/components/PaginatedList.vue";

defineProps<{
  title: string;
  endpoint: string;
  query?: string;
}>();
</script>

<template>
  <section>
    <h1>{{ title }}</h1>
    <PaginatedList :endpoint="endpoint" :query="query" :aria-label="title">
      <template #raw="{ payload }">
        <pre class="json">{{ JSON.stringify(payload, null, 2) }}</pre>
      </template>
    </PaginatedList>
  </section>
</template>
