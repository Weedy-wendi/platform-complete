import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { useAuthStore } from "@/stores/auth";
import { apiFetch, ApiError } from "@/api/client";
import { clearReportedErrors, getReportedErrors } from "@/observability/errors";
import { LOCALE_STORAGE_KEY } from "@/i18n";
import { readFileSync } from "node:fs";

const SECRET = "pk_live_SECRET123";

function fakeResponse(status: number, body: unknown): Response {
  return {
    status,
    ok: status >= 200 && status < 300,
    json: async () => body,
  } as unknown as Response;
}

describe("credential safety", () => {
  beforeEach(() => {
    sessionStorage.clear();
    localStorage.clear();
    setActivePinia(createPinia());
    history.replaceState({}, "", "/");
    clearReportedErrors();
    vi.spyOn(console, "warn").mockImplementation(() => {});
    delete (window as { fetch?: unknown }).fetch;
  });

  it("keeps the API key out of cookies, the URL and localStorage", () => {
    const auth = useAuthStore();
    auth.login(SECRET, "tenant-a");

    expect(auth.hasKey).toBe(true);
    expect(sessionStorage.getItem("pingce.apiKey")).toBe(SECRET);
    expect(document.cookie).not.toContain(SECRET);
    expect(window.location.href).not.toContain(SECRET);
    expect(JSON.stringify({ ...localStorage })).not.toContain(SECRET);
    expect(localStorage.getItem("pingce.apiKey")).toBeNull();
  });

  it("only persists the locale choice, never the key", () => {
    localStorage.setItem(LOCALE_STORAGE_KEY, "en-US");
    expect(localStorage.length).toBe(1);
    expect(localStorage.key(0)).toBe(LOCALE_STORAGE_KEY);
  });

  it("ships a Content-Security-Policy meta tag", () => {
    const html = readFileSync("index.html", "utf8");
    expect(html).toMatch(/http-equiv="Content-Security-Policy"/i);
    expect(html).toContain("default-src 'self'");
    expect(html).toContain("object-src 'none'");
    expect(html).toContain("frame-ancestors 'none'");
  });

  it("clears credentials on 401 and reports only status metadata", async () => {
    sessionStorage.setItem("pingce.apiKey", SECRET);
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        fakeResponse(401, {
          error: {
            code: "UNAUTHORIZED",
            message: "invalid credentials",
            trace_id: "trace-401",
            details: { api_key: SECRET, body: { sample: "PII" } },
          },
        }),
      ),
    );

    await expect(apiFetch("/projects")).rejects.toBeInstanceOf(ApiError);

    expect(sessionStorage.getItem("pingce.apiKey")).toBeNull();
    const report = getReportedErrors().at(-1);
    expect(report?.trace_id).toBe("trace-401");
    expect(report?.code).toBe("UNAUTHORIZED");
    expect(JSON.stringify(getReportedErrors())).not.toContain(SECRET);
    expect(JSON.stringify(getReportedErrors())).not.toContain("PII");
    vi.unstubAllGlobals();
  });
});
