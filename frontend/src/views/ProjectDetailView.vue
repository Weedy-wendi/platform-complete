<script setup lang="ts">
import { useRoute } from "vue-router";
import { useI18n } from "vue-i18n";
import ResourceView from "./ResourceView.vue";

const { t } = useI18n();
const route = useRoute();
</script>

<template><ResourceView :title="t('nav.projects')" :endpoint="`/projects/${route.params.id}`" /></template>
