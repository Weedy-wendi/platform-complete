import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import EvaluatorsView from "@/views/EvaluatorsView.vue";
import { setLocale } from "@/i18n";
import { useAuthStore } from "@/stores/auth";
import { globalMountOptions, jsonResponse, stubResizeObserver } from "./helpers";

const ITEMS = {
  items: [
    {
      id: "ev-1",
      name: "Exact match",
      description: "Compares normalized strings",
      version: "1.2.0",
      kind: "rule",
      config: { threshold: 0.9 },
    },
  ],
};

function inputByTest(wrapper: VueWrapper, name: string) {
  const direct = wrapper.find(`input[data-test="${name}"]`);
  if (direct.exists()) return direct;
  return wrapper.find(`[data-test="${name}"] input`);
}

function textareaByTest(wrapper: VueWrapper, name: string) {
  const direct = wrapper.find(`textarea[data-test="${name}"]`);
  if (direct.exists()) return direct;
  return wrapper.find(`[data-test="${name}"] textarea`);
}

describe("EvaluatorsView", () => {
  beforeEach(() => {
    sessionStorage.clear();
    localStorage.clear();
    setLocale("zh-CN");
    stubResizeObserver();
    vi.spyOn(console, "warn").mockImplementation(() => {});
  });

  it("lists evaluators with version metadata and creates an evaluator", async () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    const auth = useAuthStore(pinia);
    auth.login("pk_test_abc");

    let postedBody: unknown = null;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (init?.method === "POST") {
        postedBody = JSON.parse(String(init.body)) as unknown;
        return jsonResponse({ id: "ev-2", name: "New evaluator", version: "0.1.0" });
      }
      return jsonResponse(ITEMS);
    });
    vi.stubGlobal("fetch", fetchMock);

    const wrapper = mount(EvaluatorsView, {
      global: {
        ...globalMountOptions([pinia]),
        stubs: { teleport: true },
      },
    });
    await flushPromises();

    expect(wrapper.text()).toContain("Exact match");
    expect(wrapper.text()).toContain("1.2.0");
    expect(wrapper.text()).toContain("版本");

    await wrapper.get('[data-test="config-create"]').trigger("click");
    await flushPromises();
    await inputByTest(wrapper, "config-name").setValue("New evaluator");
    await inputByTest(wrapper, "config-description").setValue("desc");
    await textareaByTest(wrapper, "config-json").setValue('{"threshold":0.8}');
    await wrapper.get('[data-test="config-save"]').trigger("click");
    await flushPromises();

    expect(postedBody).toEqual({
      name: "New evaluator",
      description: "desc",
      config: { threshold: 0.8 },
    });
    const postCall = fetchMock.mock.calls.find(
      ([, init]) => (init as RequestInit | undefined)?.method === "POST",
    );
    expect(postCall?.[0]).toBe("/v1/evaluators");
    const headers = (postCall?.[1] as RequestInit).headers as Record<string, string>;
    expect(headers["Idempotency-Key"]).toBeTruthy();
  });

  it("opens the edit dialog and posts the existing id back to the collection", async () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    useAuthStore(pinia).login("pk_test_abc");

    let postedBody: unknown = null;
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      if (init?.method === "POST") {
        postedBody = JSON.parse(String(init.body)) as unknown;
        return jsonResponse({ id: "ev-1", name: "Renamed", version: "1.3.0" });
      }
      return jsonResponse(ITEMS);
    });
    vi.stubGlobal("fetch", fetchMock);

    const wrapper = mount(EvaluatorsView, {
      global: {
        ...globalMountOptions([pinia]),
        stubs: { teleport: true },
      },
    });
    await flushPromises();

    await wrapper.get('[data-test="config-edit"]').trigger("click");
    await flushPromises();
    await inputByTest(wrapper, "config-name").setValue("Renamed");
    await wrapper.get('[data-test="config-save"]').trigger("click");
    await flushPromises();

    expect(postedBody).toMatchObject({
      id: "ev-1",
      name: "Renamed",
      description: "Compares normalized strings",
      config: { threshold: 0.9 },
    });
  });

  it("hides write actions without the evaluators:write scope", async () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    const auth = useAuthStore(pinia);
    auth.loginWithJwt("eyJhbGciOiJIUzI1NiJ9.payload.signature", "tenant-j");

    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(ITEMS)));

    const wrapper = mount(EvaluatorsView, {
      global: {
        ...globalMountOptions([pinia]),
        stubs: { teleport: true },
      },
    });
    await flushPromises();

    expect(auth.can("evaluators:write")).toBe(false);
    expect(wrapper.find('[data-test="config-create"]').exists()).toBe(false);
    expect(wrapper.text()).toContain("当前 scope 不允许编辑配置");
  });
});
