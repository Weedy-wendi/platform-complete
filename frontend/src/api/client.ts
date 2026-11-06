import { reportError } from "@/observability/errors";
import {
  API_KEY_STORAGE_KEY,
  clearStoredCredentials,
  TOKEN_TYPE_STORAGE_KEY,
} from "@/auth/session";

export interface ApiErrorBody {
  error?: {
    code?: string;
    message?: string;
    trace_id?: string;
    details?: Record<string, unknown>;
  };
}

export class ApiError extends Error {
  code: string;
  traceId?: string;
  status: number;

  constructor(status: number, body: ApiErrorBody) {
    super(body.error?.message ?? `HTTP ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.code = body.error?.code ?? "UNKNOWN";
    this.traceId = body.error?.trace_id;
  }

  get unauthorized(): boolean {
    return this.status === 401;
  }

  get forbidden(): boolean {
    return this.status === 403;
  }

  get notFound(): boolean {
    return this.status === 404;
  }
}

export function authHeader(): Record<string, string> {
  const key = sessionStorage.getItem(API_KEY_STORAGE_KEY) ?? "";
  if (!key) return {};
  // The token never appears in a URL or a log line; it travels only in this header.
  return { Authorization: `Bearer ${key}` };
}

/**
 * Current credential transport, exposed for the JWT/OIDC placeholder path.
 */
export function tokenType(): "apiKey" | "jwt" {
  return sessionStorage.getItem(TOKEN_TYPE_STORAGE_KEY) === "jwt" ? "jwt" : "apiKey";
}

/**
 * Idempotency keys for create/submit requests. The value is opaque and is
 * never derived from credentials.
 */
export function idempotencyKey(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `idem-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function notifyUnauthorized(): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent("pingce:unauthorized"));
}

async function request(path: string, init: RequestInit = {}): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(`/v1${path}`, {
      ...init,
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        ...authHeader(),
        ...(init.headers ?? {}),
      },
    });
  } catch (exc) {
    const networkError = new ApiError(0, {
      error: {
        code: "NETWORK_ERROR",
        message: exc instanceof Error ? exc.message : "Network request failed",
      },
    });
    reportError(networkError);
    throw networkError;
  }

  if (response.status === 401) {
    clearStoredCredentials();
    notifyUnauthorized();
  }
  if (!response.ok) {
    let body: ApiErrorBody = {};
    try {
      body = (await response.json()) as ApiErrorBody;
    } catch {
      body = {};
    }
    const error = new ApiError(response.status, body);
    reportError(error, error.traceId);
    throw error;
  }
  return response;
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await request(path, init);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

/**
 * Fetch a non-JSON representation (Markdown/CSV/JUnit) as text.
 */
export async function apiText(path: string, init: RequestInit = {}): Promise<string> {
  const response = await request(path, init);
  return await response.text();
}

export function sanitizeFilename(filename: string): string {
  const base = filename.split(/[\\/]/).pop() ?? "download";
  const cleaned = base.replace(/[^\w.-]+/g, "_").replace(/^\.+/, "");
  return cleaned || "download";
}

/**
 * Trigger a browser download for an in-memory blob. Kept separate from the
 * network layer so component tests can observe the generated anchor.
 */
export function triggerDownload(blob: Blob, filename: string): void {
  if (typeof document === "undefined") return;
  if (typeof URL === "undefined" || typeof URL.createObjectURL !== "function") return;

  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = sanitizeFilename(filename);
  link.rel = "noopener";
  link.style.display = "none";
  document.body.appendChild(link);
  link.click();
  link.remove();
  if (typeof URL.revokeObjectURL === "function") URL.revokeObjectURL(objectUrl);
}

/**
 * Download a `/v1` response verbatim. Authentication travels in the request
 * header only; no credential is ever appended to the path or the filename.
 */
export async function apiDownload(
  path: string,
  filename: string,
  init: RequestInit = {},
): Promise<Blob> {
  const response = await request(path, init);
  const blob = await response.blob();
  triggerDownload(blob, filename);
  return blob;
}

export function cursorQuery(cursor?: string, limit = 20): string {
  const params = new URLSearchParams({ limit: String(limit) });
  if (cursor) params.set("cursor", cursor);
  return params.toString();
}
