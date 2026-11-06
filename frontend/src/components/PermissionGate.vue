<script setup lang="ts">
import { computed } from "vue";
import { useAuthStore } from "@/stores/auth";

const props = withDefaults(
  defineProps<{
    scope: string;
    mode?: "hide" | "disable";
  }>(),
  { mode: "hide" },
);

const auth = useAuthStore();
const allowed = computed(() => auth.can(props.scope));
</script>

<template>
  <slot v-if="allowed" />
  <span
    v-else-if="mode === 'disable'"
    class="permission-disabled"
    aria-disabled="true"
  >
    <slot />
  </span>
  <slot v-else name="fallback" />
</template>

<style scoped>
.permission-disabled {
  display: inline-block;
  opacity: 0.55;
  pointer-events: none;
  cursor: not-allowed;
}
</style>
