import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import ReportsView from "@/views/ReportsView.vue";
import { setLocale } from "@/i18n";
import { globalMountOptions, jsonResponse, textResponse } from "./helpers";

const SECRET = "pk_live_SECRET123";

function findByTest(wrapper: VueWrapper, name: string) {
  return wrapper.find(`[data-test="${name}"]`);
}

function inputByTest(wrapper: VueWrapper, name: string) {
  const direct = wrapper.find(`input[data-test="${name}"]`);
  if (direct.exists()) return direct;
  return wrapper.find(`[data-test="${name}"] input`);
}

describe("ReportsView", () => {
  beforeEach(() => {
    sessionStorage.clear();
    sessionStorage.setItem("pingce.apiKey", SECRET);
    localStorage.clear();
    setLocale("zh-CN");
    vi.spyOn(console, "warn").mockImplementation(() => {});
  });

  it("renders sanitized Markdown from /reports/{runId}?format=markdown", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      textResponse("# Report\n\nSafe body\n\n<script>window.__xss = 1</script>"),
    );
    vi.stubGlobal("fetch", fetchMock);

    const wrapper = mount(ReportsView, { global: globalMountOptions() });
    await inputByTest(wrapper, "run-id").setValue("run-1");
    await findByTest(wrapper, "load-report").trigger("click");
    await flushPromises();

    const call = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(call[0]).toBe("/v1/reports/run-1?format=markdown");
    const preview = findByTest(wrapper, "markdown-preview");
    expect(preview.exists()).toBe(true);
    expect(preview.element.innerHTML).toContain("<h1>Report</h1>");
    expect(preview.element.innerHTML).not.toContain("<script");
    expect(preview.element.innerHTML).not.toContain("__xss");
  });

  it("creates a share link and copies the absolute URL without leaking the API key", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/reports/run-1/share")) {
        return jsonResponse({
          url: "/v1/reports/share/abc",
          expires_at: "2026-11-05T12:00:00Z",
        });
      }
      throw new Error(`unexpected request ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });

    const wrapper = mount(ReportsView, { global: globalMountOptions() });
    await inputByTest(wrapper, "run-id").setValue("run-1");
    await findByTest(wrapper, "share").trigger("click");
    await flushPromises();

    const shareCall = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(shareCall[0]).toBe("/v1/reports/run-1/share");
    expect(shareCall[1].method).toBe("POST");
    expect(JSON.parse(String(shareCall[1].body))).toEqual({ ttl_seconds: 3600 });
    expect((shareCall[1].headers as Record<string, string>)["Idempotency-Key"]).toBeTruthy();

    const expectedUrl = `${window.location.origin}/v1/reports/share/abc`;
    expect(inputByTest(wrapper, "share-url").element).toHaveProperty("value", expectedUrl);
    expect(expectedUrl).not.toContain(SECRET);
    expect(wrapper.text()).toContain("分享链接已生成");
    expect(wrapper.text()).toContain("过期时间");
    expect(wrapper.text()).not.toContain(SECRET);

    await findByTest(wrapper, "copy-share").trigger("click");
    await flushPromises();

    expect(writeText).toHaveBeenCalledWith(expectedUrl);
    expect(wrapper.text()).toContain("已复制到剪贴板");
  });

  it("shows errors with the trace id", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(
          {
            error: {
              code: "REPORT_FAILED",
              message: "report generation failed",
              trace_id: "trace-report-1",
            },
          },
          500,
        ),
      ),
    );

    const wrapper = mount(ReportsView, { global: globalMountOptions() });
    await inputByTest(wrapper, "run-id").setValue("run-1");
    await findByTest(wrapper, "load-report").trigger("click");
    await flushPromises();

    expect(wrapper.text()).toContain("trace-report-1");
  });
});
