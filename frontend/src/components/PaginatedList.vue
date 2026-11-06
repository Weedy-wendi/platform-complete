<script setup lang="ts">
import { computed, onMounted } from "vue";
import { useI18n } from "vue-i18n";
import { describeError } from "@/api/errors";
import { usePaginatedList } from "@/composables/usePaginatedList";

const props = withDefaults(
  defineProps<{
    endpoint: string;
    query?: string;
    pageSize?: number;
    columns?: string[];
    ariaLabel?: string;
  }>(),
  { pageSize: 20 },
);

const { t } = useI18n();
const list = usePaginatedList({
  limit: props.pageSize,
  endpoint: () => props.endpoint + (props.query ? `?${props.query}` : ""),
});

const columns = computed(() => props.columns ?? Object.keys(list.items.value[0] ?? {}));
const errorText = computed(() => (list.error.value ? describeError(list.error.value, t) : ""));

onMounted(() => {
  void list.reload();
});

function refresh() {
  void list.reload();
}

defineExpose({ reload: list.reload });
</script>

<template>
  <section class="paginated-list" :aria-label="ariaLabel">
    <div class="list-toolbar">
      <slot name="toolbar" :reload="refresh" :loading="list.loading.value" :count="list.items.value.length" />
      <el-button :loading="list.loading.value" @click="refresh">{{ t("common.refresh") }}</el-button>
    </div>

    <el-alert v-if="errorText" :title="errorText" type="error" show-icon />

    <el-table
      v-if="list.items.value.length"
      :data="list.items.value"
      class="table"
      :aria-label="ariaLabel"
    >
      <el-table-column
        v-for="key in columns"
        :key="key"
        :prop="key"
        :label="key"
        show-overflow-tooltip
      />
    </el-table>

    <slot v-else-if="list.payload.value && !list.loading.value" name="raw" :payload="list.payload.value" />

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
