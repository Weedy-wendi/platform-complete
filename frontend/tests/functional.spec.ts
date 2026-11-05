import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createMemoryHistory, createRouter } from "vue-router";
import FunctionalRunDetailView from "@/views/FunctionalRunDetailView.vue";
import FunctionalView from "@/views/FunctionalView.vue";
import { setLocale } from "@/i18n";
import { statusTagType, normalizeSteps } from "@/utils/functional";
import { globalMountOptions, jsonResponse, stubResizeObserver } from "./helpers";

const SECRET = "pk_live_SECRET123";

const RUN = {
  run_id: "run-1",
  status: "failed",
  started_at: "2026-11-05T10:00:00Z",
  steps: [
    {
      step_id: "s1",
      name: "Open login page",
      status: "passed",
      duration_ms: 1200,
      evidence: {
        screenshot: "https://cdn.example/s1.png",
        console: "https://cdn.example/s1.log",
      },
      visual_diff: {
        mismatch_ratio: 0.034,
        passed: false,
        url: "https://cdn.example/diff.png",
      },
    },
    {
      step_id: "s2",
      name: "Submit credentials",
      status: "failed",
      duration_ms: 340,
      evidence: [
        { type: "network", url: "https://cdn.example/har.json" },
        { type: "trace", url: "https://cdn.example/trace.zip" },
      ],
    },
  ],
};

async function makeRouter(path: string) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/functional", component: { template: "<div />" } },
      { path: "/functional/:id", component: { template: "<div />" } },
    ],
  });
  await router.push(path);
  await router.isReady();
  return router;
}

describe("functional step normalization", () => {
  it("maps step status, duration, evidence and visual diff fields", () => {
    const steps = normalizeSteps(RUN);
    expect(steps).toHaveLength(2);
    expect(steps[0]).toMatchObject({
      id: "s1",
      name: "Open login page",
      status: "passed",
      durationMs: 1200,
      mismatchRatio: 0.034,
      visualPassed: false,
      visualRef: "https://cdn.example/diff.png",
    });
    expect(steps[0].evidence).toEqual([
      { kind: "screenshot", ref: "https://cdn.example/s1.png", url: "https://cdn.example/s1.png" },
      { kind: "console", ref: "https://cdn.example/s1.log", url: "https://cdn.example/s1.log" },
    ]);
    expect(steps[1].evidence.map((item) => item.kind)).toEqual(["network", "trace"]);
    expect(statusTagType("failed")).toBe("danger");
    expect(statusTagType("passed")).toBe("success");
  });
});

describe("FunctionalRunDetailView", () => {
  beforeEach(() => {
    sessionStorage.clear();
    sessionStorage.setItem("pingce.apiKey", SECRET);
    localStorage.clear();
    setLocale("zh-CN");
    stubResizeObserver();
    vi.spyOn(console, "warn").mockImplementation(() => {});
  });

  it("renders steps, durations, evidence links and visual diff results", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(RUN));
    vi.stubGlobal("fetch", fetchMock);
    const router = await makeRouter("/functional/run-1");

    const wrapper = mount(FunctionalRunDetailView, {
      global: { plugins: [router, ...globalMountOptions().plugins] },
    });
    await flushPromises();

    expect(fetchMock).toHaveBeenCalledWith("/v1/functional/runs/run-1", expect.any(Object));
    expect(wrapper.text()).toContain("Open login page");
    expect(wrapper.text()).toContain("Submit credentials");
    expect(wrapper.text()).toContain("1.2 s");
    expect(wrapper.text()).toContain("340 ms");
    expect(wrapper.text()).toContain("3.4%");
    expect(wrapper.text()).toContain("视觉未通过");

    const links = wrapper.findAll('[data-test="evidence-link"]');
    expect(links).toHaveLength(4);
    const hrefs = links.map((link) => link.attributes("href"));
    expect(hrefs).toContain("https://cdn.example/s1.png");
    expect(hrefs).toContain("https://cdn.example/s1.log");
    expect(hrefs).toContain("https://cdn.example/har.json");
    expect(hrefs).toContain("https://cdn.example/trace.zip");
    expect(hrefs.join(" ")).not.toContain(SECRET);

    expect(wrapper.find('[data-test="visual-link"]').attributes("href")).toBe(
      "https://cdn.example/diff.png",
    );
    expect(wrapper.findAll(".el-tag--danger").length).toBeGreaterThanOrEqual(1);
    expect(wrapper.findAll(".el-tag--success").length).toBeGreaterThanOrEqual(1);
  });
});

describe("FunctionalView", () => {
  beforeEach(() => {
    localStorage.clear();
    setLocale("zh-CN");
    stubResizeObserver();
    vi.spyOn(console, "warn").mockImplementation(() => {});
  });

  it("links each functional run row to /functional/{id}", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({
          items: [{ run_id: "run-9", status: "succeeded", duration_ms: 2100 }],
          next_cursor: null,
        }),
      ),
    );
    const router = await makeRouter("/functional");

    const wrapper = mount(FunctionalView, {
      global: { plugins: [router, ...globalMountOptions().plugins] },
    });
    await flushPromises();

    const link = wrapper.get('[data-test="functional-run-link"]');
    expect(link.text()).toBe("run-9");
    expect(link.attributes("href")).toBe("/functional/run-9");
    expect(wrapper.text()).toContain("2.1 s");
  });
});
