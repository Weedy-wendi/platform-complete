import { createI18n } from "vue-i18n";
import enUS from "@/locales/en-US";
import zhCN from "@/locales/zh-CN";

export const LOCALE_STORAGE_KEY = "pingce.locale";
export const SUPPORTED_LOCALES = ["zh-CN", "en-US"] as const;
export type AppLocale = (typeof SUPPORTED_LOCALES)[number];
export const DEFAULT_LOCALE: AppLocale = "zh-CN";

export function isSupportedLocale(value: unknown): value is AppLocale {
  return typeof value === "string" && (SUPPORTED_LOCALES as readonly string[]).includes(value);
}

/**
 * Read the persisted locale. Only the locale choice is ever persisted, never credentials.
 */
export function getStoredLocale(): AppLocale {
  try {
    const stored = localStorage.getItem(LOCALE_STORAGE_KEY);
    return isSupportedLocale(stored) ? stored : DEFAULT_LOCALE;
  } catch {
    return DEFAULT_LOCALE;
  }
}

export function persistLocale(locale: AppLocale): void {
  try {
    localStorage.setItem(LOCALE_STORAGE_KEY, locale);
  } catch {
    // Storage may be unavailable (private mode); the in-memory locale still applies.
  }
}

export const i18n = createI18n({
  legacy: false,
  locale: getStoredLocale(),
  fallbackLocale: DEFAULT_LOCALE,
  messages: {
    "zh-CN": zhCN,
    "en-US": enUS,
  },
});

export function setLocale(locale: AppLocale): void {
  i18n.global.locale.value = locale;
  persistLocale(locale);
  if (typeof document !== "undefined") document.documentElement.lang = locale;
}

export function currentLocale(): AppLocale {
  const active = i18n.global.locale.value;
  return isSupportedLocale(active) ? active : DEFAULT_LOCALE;
}
