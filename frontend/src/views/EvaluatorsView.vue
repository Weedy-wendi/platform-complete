<script setup lang="ts">
import { ref } from "vue";
import { useI18n } from "vue-i18n";
import ConfigResourcePanel from "@/components/ConfigResourcePanel.vue";

type ConfigResource = "evaluators" | "suites" | "targets";

const props = withDefaults(defineProps<{ initialTab?: ConfigResource }>(), {
  initialTab: "evaluators",
});

const { t } = useI18n();
const activeTab = ref<ConfigResource>(props.initialTab);
</script>

<template>
  <section>
    <h1>{{ t("config.title") }}</h1>
    <el-tabs v-model="activeTab">
      <el-tab-pane :label="t('config.tabEvaluators')" name="evaluators" lazy>
        <ConfigResourcePanel endpoint="/evaluators" resource="evaluators" />
      </el-tab-pane>
      <el-tab-pane :label="t('config.tabSuites')" name="suites" lazy>
        <ConfigResourcePanel endpoint="/suites" resource="suites" />
      </el-tab-pane>
      <el-tab-pane :label="t('config.tabTargets')" name="targets" lazy>
        <ConfigResourcePanel endpoint="/targets" resource="targets" />
      </el-tab-pane>
    </el-tabs>
  </section>
</template>
