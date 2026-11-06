<script setup lang="ts">
import { useI18n } from "vue-i18n";
import ResourceView from "./ResourceView.vue";

const { t } = useI18n();
</script>

<template><ResourceView :title="t('nav.datasets')" endpoint="/datasets" /></template>
