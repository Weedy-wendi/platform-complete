import { ref, type Ref } from "vue";
import { apiFetch } from "@/api/client";

export interface PagePayload {
  items?: unknown[];
  next_cursor?: string | null;
}

export interface PaginatedListOptions {
  endpoint: () => string;
  limit?: number;
  fetcher?: (path: string) => Promise<unknown>;
}

export interface PaginatedList<T = Record<string, unknown>> {
  items: Ref<T[]>;
  payload: Ref<unknown>;
  cursor: Ref<string>;
  hasMore: Ref<boolean>;
  loading: Ref<boolean>;
  loadedPages: Ref<number>;
  error: Ref<unknown>;
  load: (reset?: boolean) => Promise<void>;
  loadMore: () => Promise<void>;
  reload: () => Promise<void>;
}

export function buildPagePath(endpoint: string, cursor: string, limit: number): string {
  const params = new URLSearchParams({ limit: String(limit) });
  if (cursor) params.set("cursor", cursor);
  const separator = endpoint.includes("?") ? "&" : "?";
  return `${endpoint}${separator}${params.toString()}`;
}

function extractPage(payload: unknown): PagePayload {
  return payload && typeof payload === "object" ? (payload as PagePayload) : {};
}

/**
 * Cursor pagination state. The API contract returns `items` plus an opaque
 * `next_cursor`; an empty/absent cursor means the list is exhausted.
 */
export function usePaginatedList<T = Record<string, unknown>>(
  options: PaginatedListOptions,
): PaginatedList<T> {
  const limit = options.limit ?? 20;
  const fetcher = options.fetcher ?? apiFetch;

  const items = ref([]) as Ref<T[]>;
  const payload = ref<unknown>(null);
  const cursor = ref("");
  const hasMore = ref(true);
  const loading = ref(false);
  const loadedPages = ref(0);
  const error = ref<unknown>(null);

  async function load(reset = false): Promise<void> {
    if (loading.value) return;
    if (!reset && loadedPages.value > 0 && !hasMore.value) return;

    if (reset) {
      items.value = [] as T[];
      cursor.value = "";
      hasMore.value = true;
      loadedPages.value = 0;
    }

    loading.value = true;
    error.value = null;
    const requestCursor = cursor.value;
    try {
      const data = await fetcher(buildPagePath(options.endpoint(), requestCursor, limit));
      const page = extractPage(data);
      const pageItems = Array.isArray(page.items) ? (page.items as T[]) : [];
      items.value = reset || loadedPages.value === 0 ? pageItems : [...items.value, ...pageItems];
      payload.value = data;
      cursor.value = typeof page.next_cursor === "string" ? page.next_cursor : "";
      hasMore.value = cursor.value.length > 0;
      loadedPages.value += 1;
    } catch (exc) {
      error.value = exc;
    } finally {
      loading.value = false;
    }
  }

  async function loadMore(): Promise<void> {
    await load(false);
  }

  async function reload(): Promise<void> {
    await load(true);
  }

  return { items, payload, cursor, hasMore, loading, loadedPages, error, load, loadMore, reload };
}
