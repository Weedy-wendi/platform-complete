import { ApiError } from "@/api/client";

export type ErrorKind = "unauthorized" | "forbidden" | "not_found" | "unknown";

export function errorKind(error: unknown): ErrorKind {
  if (error instanceof ApiError) {
    if (error.status === 401) return "unauthorized";
    if (error.status === 403) return "forbidden";
    if (error.status === 404) return "not_found";
  }
  const status = (error as { status?: unknown } | null)?.status;
  if (status === 401) return "unauthorized";
  if (status === 403) return "forbidden";
  if (status === 404) return "not_found";
  return "unknown";
}

const MESSAGE_KEYS: Record<ErrorKind, string> = {
  unauthorized: "errors.unauthorized",
  forbidden: "errors.forbidden",
  not_found: "errors.notFound",
  unknown: "errors.unknown",
};

/**
 * Unified 401/403/404 copy. Detail from the server is only used for unknown
 * failures so forbidden and missing resources never leak existence metadata.
 */
export function describeError(error: unknown, t: (key: string, params?: Record<string, unknown>) => string): string {
  const kind = errorKind(error);
  const traceId = error instanceof ApiError ? error.traceId : undefined;
  const trace = traceId ? ` (${t("errors.trace", { traceId })})` : "";
  if (kind === "unknown" && error instanceof Error && error.message) {
    return `${error.message}${trace}`;
  }
  return `${t(MESSAGE_KEYS[kind])}${trace}`;
}
