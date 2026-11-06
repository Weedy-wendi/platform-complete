<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { RouterView, useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import en from "element-plus/es/locale/lang/en";
import zhCn from "element-plus/es/locale/lang/zh-cn";
import NavMenu from "@/components/NavMenu.vue";
import { setLocale, type AppLocale } from "@/i18n";
import { useAuthStore } from "@/stores/auth";
import { useUiStore } from "@/stores/ui";
import { useMediaQuery } from "@/composables/useMediaQuery";

const auth = useAuthStore();
const ui = useUiStore();
const router = useRouter();
const { t, locale } = useI18n();
const narrow = useMediaQuery("(max-width: 800px)", false);
const drawerOpen = ref(false);

const elementLocale = computed(() => (locale.value === "en-US" ? en : zhCn));
const showSidebar = computed(() => auth.hasKey && !narrow.value);

function onLocaleChange(value: string) {
  setLocale(value as AppLocale);
  locale.value = value as AppLocale;
}

function onUnauthorized() {
  auth.logout();
  void router.push("/login");
}

function logout() {
  auth.logout();
  void router.push("/login");
}

watch(narrow, (isNarrow) => {
  if (!isNarrow) drawerOpen.value = false;
});

onMounted(() => window.addEventListener("pingce:unauthorized", onUnauthorized));
onBeforeUnmount(() => window.removeEventListener("pingce:unauthorized", onUnauthorized));
</script>

<template>
  <el-config-provider :locale="elementLocale">
    <a class="skip-link" href="#main-content">{{ t("a11y.skipToContent") }}</a>
    <el-container class="shell">
      <el-aside v-if="showSidebar" width="220px" class="nav">
        <h2 class="brand">Pingce</h2>
        <NavMenu />
      </el-aside>

      <el-container class="shell-body">
        <el-header class="header" role="banner" :aria-label="t('a11y.banner')">
          <div class="header-start">
            <el-button
              v-if="auth.hasKey && narrow"
              class="menu-toggle"
              text
              :aria-label="drawerOpen ? t('a11y.closeMenu') : t('a11y.openMenu')"
              :aria-expanded="drawerOpen"
              aria-controls="app-nav-drawer"
              @click="drawerOpen = !drawerOpen"
            >
              <span aria-hidden="true">☰</span>
            </el-button>
            <span class="shell-title">{{ t(ui.titleKey) }}</span>
          </div>
          <div class="header-actions">
            <el-select
              :model-value="locale"
              class="locale-select"
              :aria-label="t('a11y.language')"
              @change="onLocaleChange"
            >
              <el-option :label="t('locale.zh')" value="zh-CN" />
              <el-option :label="t('locale.en')" value="en-US" />
            </el-select>
            <el-button v-if="auth.hasKey" text @click="logout">{{ t("nav.logout") }}</el-button>
          </div>
        </el-header>

        <el-main
          id="main-content"
          class="main-content"
          tabindex="-1"
          :aria-label="t('a11y.mainContent')"
        >
          <el-alert v-if="ui.error" :title="ui.error" type="error" show-icon closable @close="ui.clearError" />
          <RouterView />
        </el-main>
      </el-container>
    </el-container>

    <el-drawer
      v-model="drawerOpen"
      direction="ltr"
      size="260px"
      :title="t('nav.menu')"
      class="nav-drawer"
    >
      <div id="app-nav-drawer">
        <NavMenu @navigate="drawerOpen = false" />
      </div>
    </el-drawer>
  </el-config-provider>
</template>
