import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import GatesView from "@/views/GatesView.vue";
import { setLocale } from "@/i18n";
import { gateSummary, normalizeGateRules } from "@/utils/gate";
import { globalMountOptions, jsonResponse, stubResizeObserver } from "./helpers";

const GATE = {
  passed: false,
  rules: [
    {
      name: "accuracy",
      expected: ">= 0.90",
      actual: "0.82",
      passed: false,
      evidence_ref: "s3://evidence/gate-1.json",
    },
    {
      name: "latency",
      expected: "<= 2.0s",
      actual: "1.1s",
      passed: true,
      evidence_ref: "https://evidence.example/latency.json",
    },
  ],
};

function inputByTest(wrapper: VueWrapper, name: string) {
  const direct = wrapper.find(`input[data-test="${name}"]`);
  if (direct.exists()) return direct;
  return wrapper.find(`[data-test="${name}"] input`);
}

describe("gate rules", () => {
  it("normalizes rules and summarizes failures", () => {
    const rules = normalizeGateRules(GATE);
    expect(rules).toHaveLength(2);
    expect(rules[0]).toEqual({
      name: "accuracy",
      expected: ">= 0.90",
      actual: "0.82",
      passed: false,
      evidenceRef: "s3://evidence/gate-1.json",
    });
    expect(gateSummary(rules)).toEqual({
      total: 2,
      passed: 1,
      failed: 1,
      allPassed: false,
    });
  });
});

describe("GatesView", () => {
  beforeEach(() => {
    localStorage.clear();
    setLocale("zh-CN");
    stubResizeObserver();
    vi.spyOn(console, "warn").mockImplementation(() => {});
  });

  it("highlights failed rows and renders expected/actual/evidence", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(GATE));
    vi.stubGlobal("fetch", fetchMock);

    const wrapper = mount(GatesView, { global: globalMountOptions() });
    await inputByTest(wrapper, "gate-suite").setValue("suite-1");
    await inputByTest(wrapper, "gate-run").setValue("run-1");
    await wrapper.get('[data-test="gate-query"]').trigger("click");
    await flushPromises();

    expect(fetchMock).toHaveBeenCalledWith("/v1/gates/suite-1/run-1", expect.any(Object));
    expect(wrapper.text()).toContain("accuracy");
    expect(wrapper.text()).toContain(">= 0.90");
    expect(wrapper.text()).toContain("0.82");
    expect(wrapper.text()).toContain("s3://evidence/gate-1.json");

    expect(wrapper.findAll("tr.gate-row-failed")).toHaveLength(1);
    expect(wrapper.findAll(".el-tag--danger").length).toBeGreaterThanOrEqual(1);
    expect(wrapper.findAll(".el-tag--success").length).toBeGreaterThanOrEqual(1);
    expect(wrapper.get('[data-test="gate-summary"]').text()).toContain("1 / 2");
  });

  it("shows a success summary when every rule passes", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({
          passed: true,
          rules: [{ name: "accuracy", expected: ">= 0.9", actual: "0.95", passed: true }],
        }),
      ),
    );

    const wrapper = mount(GatesView, { global: globalMountOptions() });
    await inputByTest(wrapper, "gate-suite").setValue("suite-1");
    await inputByTest(wrapper, "gate-run").setValue("run-2");
    await wrapper.get('[data-test="gate-query"]').trigger("click");
    await flushPromises();

    expect(wrapper.findAll("tr.gate-row-failed")).toHaveLength(0);
    expect(wrapper.get('[data-test="gate-summary"]').text()).toContain("全部 1 条规则通过");
  });

  it("shows the trace id when the gate query fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(
          { error: { code: "NOT_FOUND", message: "missing", trace_id: "trace-gate-1" } },
          404,
        ),
      ),
    );

    const wrapper = mount(GatesView, { global: globalMountOptions() });
    await inputByTest(wrapper, "gate-suite").setValue("suite-1");
    await inputByTest(wrapper, "gate-run").setValue("missing");
    await wrapper.get('[data-test="gate-query"]').trigger("click");
    await flushPromises();

    expect(wrapper.text()).toContain("trace-gate-1");
  });
});
