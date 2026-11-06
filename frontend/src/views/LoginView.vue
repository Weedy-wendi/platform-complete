<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import { useAuthStore } from "@/stores/auth";
import type { TokenType } from "@/auth/session";

const { t } = useI18n();
const auth = useAuthStore();
const router = useRouter();
const key = ref("");
const tenant = ref("");
const tokenType = ref<TokenType>("apiKey");

function submit() {
  if (!key.value.trim()) return;
  if (tokenType.value === "jwt") auth.loginWithJwt(key.value, tenant.value);
  else auth.login(key.value, tenant.value);
  void router.push("/");
}
</script>

<template>
  <el-card class="login">
    <h1>{{ t("auth.title") }}</h1>
    <p class="muted">{{ t("auth.storageNotice") }}</p>
    <el-form :label-width="'120px'" @submit.prevent="submit">
      <el-form-item :label="t('auth.tokenType')">
        <el-radio-group v-model="tokenType">
          <el-radio-button value="apiKey">{{ t("auth.apiKeyType") }}</el-radio-button>
          <el-radio-button value="jwt">{{ t("auth.jwtType") }}</el-radio-button>
        </el-radio-group>
      </el-form-item>
      <el-form-item :label="t('auth.apiKey')">
        <el-input
          v-model="key"
          type="password"
          show-password
          autocomplete="off"
          :placeholder="tokenType === 'jwt' ? t('auth.jwtPlaceholder') : t('auth.apiKeyPlaceholder')"
          :aria-label="t('auth.apiKey')"
        />
      </el-form-item>
      <el-form-item :label="t('auth.tenant')">
        <el-input v-model="tenant" :placeholder="t('auth.tenantPlaceholder')" :aria-label="t('auth.tenant')" />
      </el-form-item>
      <p v-if="tokenType === 'jwt'" class="muted">{{ t("auth.jwtComingSoon") }}</p>
      <el-button type="primary" native-type="submit">{{ t("auth.submit") }}</el-button>
    </el-form>
  </el-card>
</template>
