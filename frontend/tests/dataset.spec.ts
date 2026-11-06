import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createMemoryHistory, createRouter } from "vue-router";
import DatasetDetailView from "@/views/DatasetDetailView.vue";
import { setLocale } from "@/i18n";
import { buildDatasetPreview, normalizeSchema } from "@/utils/dataset";
import { maskValue, maskRecord } from "@/utils/masking";
import { globalMountOptions, jsonResponse, stubResizeObserver } from "./helpers";

const PAYLOAD = {
  schema: [
    { field: "email", type: "string", nullable: false },
    { field: "phone", type: "string", nullable: true },
    { field: "note", type: "string", nullable: true },
  ],
  samples: [
    {
      email: "alice@example.com",
      phone: "13800138000",
      note: "abcdefghijklmnopqrstuvwxyz0123456789ABCD",
    },
  ],
};

describe("sample masking", () => {
  it("masks emails, phones, long strings and secret fields", () => {
    expect(maskValue("alice@example.com")).toBe("a***@example.com");
    expect(maskValue("13800138000")).toBe("138****8000");
    expect(maskValue("abcdefghijklmnopqrstuvwxyz0123456789ABCD")).toBe("abcdefgh…ABCD");
    expect(maskValue("short")).toBe("short");
    expect(maskValue("2026-11-05")).toBe("2026-11-05");

    const masked = maskRecord({
      password: "hunter2",
      email: "alice@example.com",
      nested: { token: "tok_live_123", phone: "+8613800138000" },
    });
    expect(masked.password).toBe("***");
    expect(masked.email).toBe("a***@example.com");
    expect(masked.nested).toEqual({ token: "***", phone: "+86****8000" });
  });

  it("normalizes field lists and JSON Schema properties", () => {
    expect(
      normalizeSchema([
        { name: "email", type: "string", nullable: false },
        { field: "age", data_type: "integer", required: true },
      ]),
    ).toEqual([
      { field: "email", type: "string", nullable: false },
      { field: "age", type: "integer", nullable: false },
    ]);

    expect(
      normalizeSchema({
        type: "object",
        required: ["id"],
        properties: {
          id: { type: "string" },
          score: { type: "number", nullable: true },
        },
      }),
    ).toEqual([
      { field: "id", type: "string", nullable: false },
      { field: "score", type: "number", nullable: true },
    ]);
  });

  it("builds masked preview rows from samples or items", () => {
    const preview = buildDatasetPreview(PAYLOAD);
    expect(preview.schema).toHaveLength(3);
    expect(preview.columns).toEqual(["email", "phone", "note"]);
    expect(preview.rows[0]).toEqual({
      email: "a***@example.com",
      phone: "138****8000",
      note: "abcdefgh…ABCD",
    });

    const fromItems = buildDatasetPreview({ items: [{ payload: { email: "bob@example.com" } }] });
    expect(fromItems.rows[0]).toEqual({ email: "b***@example.com" });
  });
});

describe("DatasetDetailView", () => {
  beforeEach(() => {
    localStorage.clear();
    setLocale("zh-CN");
    stubResizeObserver();
    vi.spyOn(console, "warn").mockImplementation(() => {});
  });

  it("renders schema, masked sample preview and the raw fallback", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(PAYLOAD));
    vi.stubGlobal("fetch", fetchMock);

    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: "/datasets/:id", component: DatasetDetailView },
        { path: "/datasets", component: { template: "<div />" } },
      ],
    });
    await router.push("/datasets/ds-1");
    await router.isReady();

    const wrapper = mount(DatasetDetailView, {
      global: { plugins: [router, ...globalMountOptions().plugins] },
    });
    await flushPromises();

    expect(fetchMock).toHaveBeenCalledWith(
      "/v1/datasets/ds-1/versions/latest/samples?limit=20",
      expect.any(Object),
    );
    expect(wrapper.text()).toContain("email");
    expect(wrapper.text()).toContain("string");
    expect(wrapper.text()).toContain("a***@example.com");
    expect(wrapper.text()).toContain("138****8000");
    expect(wrapper.text()).not.toContain("alice@example.com");
    expect(wrapper.text()).not.toContain("13800138000");

    await wrapper.get('[data-test="toggle-raw"]').trigger("click");
    expect(wrapper.find('[data-test="raw-dataset"]').text()).toContain("alice@example.com");
  });

  it("requests the typed version when supplied", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ schema: [], samples: [] }));
    vi.stubGlobal("fetch", fetchMock);

    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: "/datasets/:id", component: DatasetDetailView }],
    });
    await router.push("/datasets/ds-1");
    await router.isReady();

    const wrapper = mount(DatasetDetailView, {
      global: { plugins: [router, ...globalMountOptions().plugins] },
    });
    await flushPromises();

    const versionInput = wrapper.find('input[data-test="dataset-version"]').exists()
      ? wrapper.find('input[data-test="dataset-version"]')
      : wrapper.find('[data-test="dataset-version"] input');
    await versionInput.setValue("3");
    await wrapper.get('[data-test="load-dataset"]').trigger("click");
    await flushPromises();

    expect(fetchMock).toHaveBeenLastCalledWith(
      "/v1/datasets/ds-1/versions/3/samples?limit=20",
      expect.any(Object),
    );
  });

  it("shows the trace id when the dataset request fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(
          { error: { code: "NOT_FOUND", message: "missing", trace_id: "trace-ds-1" } },
          404,
        ),
      ),
    );

    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: "/datasets/:id", component: DatasetDetailView }],
    });
    await router.push("/datasets/ds-404");
    await router.isReady();

    const wrapper = mount(DatasetDetailView, {
      global: { plugins: [router, ...globalMountOptions().plugins] },
    });
    await flushPromises();

    expect(wrapper.text()).toContain("trace-ds-1");
  });
});
