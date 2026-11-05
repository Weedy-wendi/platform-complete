import type { Plugin } from "vue";
import { vi } from "vitest";
import ElementPlus from "element-plus";
import { i18n } from "@/i18n";

export function jsonResponse(body: unknown, status = 200): Response {
  const text = JSON.stringify(body);
  return {
    status,
    ok: status >= 200 && status < 300,
    json: async () => body,
    text: async () => text,
    blob: async () => new Blob([text], { type: "application/json" }),
  } as unknown as Response;
}

export function textResponse(text: string, status = 200): Response {
  return {
    status,
    ok: status >= 200 && status < 300,
    json: async () => JSON.parse(text) as unknown,
    text: async () => text,
    blob: async () => new Blob([text], { type: "text/plain" }),
  } as unknown as Response;
}

export function stubResizeObserver(): void {
  class ResizeObserverStub {
    observe(): void {}
    unobserve(): void {}
    disconnect(): void {}
  }
  vi.stubGlobal("ResizeObserver", ResizeObserverStub);
}

export function globalMountOptions(extraPlugins: Plugin[] = []): {
  plugins: Plugin[];
} {
  return { plugins: [ElementPlus, i18n, ...extraPlugins] };
}
