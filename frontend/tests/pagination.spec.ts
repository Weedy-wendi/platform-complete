import { describe, expect, it } from "vitest";
import { buildPagePath, usePaginatedList } from "@/composables/usePaginatedList";
import { evaluateLcp, LCP_BUDGET_MS, observeLcp } from "@/perf/webVitals";

describe("cursor pagination", () => {
  it("builds cursor query strings for plain and pre-parameterized endpoints", () => {
    expect(buildPagePath("/runs", "", 20)).toBe("/runs?limit=20");
    expect(buildPagePath("/runs", "abc", 10)).toBe("/runs?limit=10&cursor=abc");
    expect(buildPagePath("/runs?status=done", "abc", 10)).toBe(
      "/runs?status=done&limit=10&cursor=abc",
    );
  });

  it("accumulates pages and stops at the final cursor", async () => {
    const pages = [
      { items: [{ id: 1 }, { id: 2 }], next_cursor: "c1" },
      { items: [{ id: 3 }], next_cursor: null },
    ];
    const calls: string[] = [];
    const list = usePaginatedList({
      limit: 2,
      endpoint: () => "/runs",
      fetcher: async (path) => {
        calls.push(path);
        return pages[calls.length - 1];
      },
    });

    expect(list.loadedPages.value).toBe(0);
    await list.load(true);
    expect(list.items.value).toHaveLength(2);
    expect(list.cursor.value).toBe("c1");
    expect(list.hasMore.value).toBe(true);
    expect(list.loadedPages.value).toBe(1);
    expect(calls[0]).toBe("/runs?limit=2");

    await list.loadMore();
    expect(list.items.value).toHaveLength(3);
    expect(list.cursor.value).toBe("");
    expect(list.hasMore.value).toBe(false);
    expect(list.loadedPages.value).toBe(2);

    await list.loadMore();
    expect(calls).toHaveLength(2);
  });

  it("captures errors and can reset after a failure", async () => {
    let fail = true;
    const list = usePaginatedList({
      limit: 2,
      endpoint: () => "/runs",
      fetcher: async () => {
        if (fail) throw new Error("boom");
        return { items: [{ id: 1 }], next_cursor: null };
      },
    });

    await list.load(true);
    expect(list.error.value).toBeInstanceOf(Error);
    expect(list.items.value).toHaveLength(0);

    fail = false;
    await list.reload();
    expect(list.error.value).toBeNull();
    expect(list.items.value).toHaveLength(1);
  });
});

describe("LCP budget", () => {
  it("marks values up to the 2500ms budget as good", () => {
    expect(LCP_BUDGET_MS).toBe(2500);
    expect(evaluateLcp(0).status).toBe("good");
    expect(evaluateLcp(2500).status).toBe("good");
    expect(evaluateLcp(2500.1).status).toBe("over-budget");
    expect(evaluateLcp(2501).budget).toBe(2500);
  });

  it("normalizes invalid samples and never throws when the observer is absent", () => {
    expect(evaluateLcp(Number.NaN).value).toBe(0);
    expect(evaluateLcp(-10).value).toBe(0);
    expect(() => observeLcp()).not.toThrow();
    const cleanup = observeLcp();
    expect(cleanup === undefined || typeof cleanup === "function").toBe(true);
    if (cleanup) cleanup();
  });
});
