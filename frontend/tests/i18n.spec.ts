import { beforeEach, describe, expect, it } from "vitest";
import {
  currentLocale,
  getStoredLocale,
  i18n,
  isSupportedLocale,
  LOCALE_STORAGE_KEY,
  setLocale,
} from "@/i18n";
import { formatCurrency, formatNumber, formatPercent, formatUtcTimestamp } from "@/i18n/format";
import enUS from "@/locales/en-US";
import zhCN from "@/locales/zh-CN";

describe("i18n", () => {
  beforeEach(() => {
    localStorage.clear();
    setLocale("zh-CN");
    localStorage.clear();
  });

  it("ships complete zh-CN and en-US catalogs", () => {
    expect(zhCN.nav.dashboard).toBe("工作台");
    expect(enUS.nav.dashboard).toBe("Dashboard");
    expect(Object.keys(enUS.nav).sort()).toEqual(Object.keys(zhCN.nav).sort());
    expect(Object.keys(enUS.errors).sort()).toEqual(Object.keys(zhCN.errors).sort());
  });

  it("validates supported locales and falls back safely", () => {
    expect(isSupportedLocale("zh-CN")).toBe(true);
    expect(isSupportedLocale("en-US")).toBe(true);
    expect(isSupportedLocale("fr-FR")).toBe(false);

    localStorage.setItem(LOCALE_STORAGE_KEY, "fr-FR");
    expect(getStoredLocale()).toBe("zh-CN");
  });

  it("persists only the locale choice and updates the active locale", () => {
    setLocale("en-US");

    expect(i18n.global.locale.value).toBe("en-US");
    expect(currentLocale()).toBe("en-US");
    expect(localStorage.length).toBe(1);
    expect(localStorage.getItem(LOCALE_STORAGE_KEY)).toBe("en-US");
    expect(document.documentElement.lang).toBe("en-US");
  });

  it("renders timestamps in UTC with an explicit marker", () => {
    const formatted = formatUtcTimestamp("2024-01-02T03:04:05Z", "en-US");
    expect(formatted).toContain("2024");
    expect(formatted).toContain("03:04:05");
    expect(formatted.endsWith("UTC")).toBe(true);

    expect(formatUtcTimestamp("not-a-date", "en-US")).toBe("not-a-date");
    expect(formatUtcTimestamp(null, "en-US")).toBe("");
  });

  it("localizes numbers, currency and percentages", () => {
    expect(formatNumber(1234567.89, "en-US", { maximumFractionDigits: 1 })).toBe("1,234,567.9");
    expect(formatNumber(1234567.89, "zh-CN", { maximumFractionDigits: 0 })).toBe("1,234,568");
    expect(formatNumber(null, "en-US")).toBe("-");
    expect(formatCurrency(1234.5, "en-US")).toContain("1,234.5");
    expect(formatPercent(0.5, "en-US")).toBe("50%");
  });
});
