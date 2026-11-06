<script setup lang="ts">
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import { useAuthStore } from "@/stores/auth";

const { t } = useI18n();
const auth = useAuthStore();
const adminGranted = computed(() => auth.can("admin:read"));

function toggleAdmin() {
  if (adminGranted.value) auth.revokeScope("admin:read");
  else auth.grantScope("admin:read");
}
</script>

<template>
  <section>
    <h1>{{ t("settings.title") }}</h1>
    <el-card>
      <p>{{ t("settings.currentTenant") }}：{{ auth.tenantId || t("settings.tenantAuto") }}</p>
      <p>{{ t("settings.tokenType") }}：{{ auth.tokenType }}</p>
      <p>{{ t("settings.scopes") }}：{{ auth.scopes.join(", ") || t("common.notAvailable") }}</p>
      <p>{{ t("settings.roles") }}：{{ auth.roles.join(", ") || t("common.notAvailable") }}</p>
      <p class="muted">{{ t("settings.storageNotice") }}</p>
      <el-button type="primary" @click="toggleAdmin">
        {{ adminGranted ? t("settings.revokeAdmin") : t("settings.grantAdmin") }}
      </el-button>
      <el-button type="danger" @click="auth.logout()">{{ t("settings.clearCredentials") }}</el-button>
    </el-card>
  </section>
</template>
