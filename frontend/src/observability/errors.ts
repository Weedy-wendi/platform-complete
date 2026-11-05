export const MAX_REPORTED_ERRORS = 50;
const MAX_TEXT_LENGTH = 240;

export interface FrontendErrorRecord {
  code: string;
  message: string;
  trace_id?: string;
  at: number;
}

declare global {
  interface Window {
    __pingceErrors?: FrontendErrorRecord[];
  }
}

const SECRET_PATTERNS: ReadonlyArray<readonly [RegExp, string]> = [
  [/\bbearer\s+[A-Za-z0-9._~+/=-]+/gi, "Bearer [redacted]"],
  [/\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}/g, "[redacted-jwt]"],
  [/\b(?:pk|sk|ak|rk)_[A-Za-z0-9_-]{4,}\b/g, "[redacted-api-key]"],
  [
    /((?:api[_-]?key|apikey|access[_-]?token|token|secret|password|authorization)\s*[:=]\s*)("[^"]*"|'[^']*'|[^\s,;&]+)/gi,
    "$1[redacted]",
  ],
  [
    /([?&](?:api[_-]?key|apikey|token|key)=)[^&\s]+/gi,
    "$1[redacted]",
  ],
];

/**
 * Strips credentials, tokens and URL secrets from free-form error text.
 * Error reporting must never capture the API key or request bodies.
 */
export function sanitizeErrorText(value: string): string {
  let text = value;
  for (const [pattern, replacement] of SECRET_PATTERNS) {
    text = text.replace(pattern, replacement);
  }
  return text.slice(0, MAX_TEXT_LENGTH);
}

function errorCode(error: unknown): string {
  if (error && typeof error === "object") {
    const candidate = error as { code?: unknown; name?: unknown };
    if (typeof candidate.code === "string" && candidate.code) return sanitizeErrorText(candidate.code);
    if (typeof candidate.name === "string" && candidate.name) return sanitizeErrorText(candidate.name);
  }
  return "UNKNOWN";
}

function errorMessage(error: unknown): string {
  if (error && typeof error === "object") {
    const candidate = error as { message?: unknown };
    if (typeof candidate.message === "string" && candidate.message) {
      return sanitizeErrorText(candidate.message);
    }
  }
  if (typeof error === "string") return sanitizeErrorText(error);
  return "Unknown error";
}

function currentBuffer(): FrontendErrorRecord[] {
  if (typeof window === "undefined") return [];
  return Array.isArray(window.__pingceErrors) ? window.__pingceErrors : [];
}

/**
 * Record a sanitized frontend error in a bounded in-memory ring buffer. Only
 * code, message and trace_id are kept: no request bodies, headers or PII.
 */
export function reportError(error: unknown, traceId?: string): FrontendErrorRecord {
  const record: FrontendErrorRecord = {
    code: errorCode(error),
    message: errorMessage(error),
    at: Date.now(),
  };
  if (traceId) record.trace_id = sanitizeErrorText(traceId);

  const buffer = currentBuffer();
  buffer.push(record);
  if (buffer.length > MAX_REPORTED_ERRORS) {
    buffer.splice(0, buffer.length - MAX_REPORTED_ERRORS);
  }
  if (typeof window !== "undefined") window.__pingceErrors = buffer;

  if (import.meta.env.DEV) {
    console.warn("[pingce] frontend error", {
      code: record.code,
      message: record.message,
      trace_id: record.trace_id,
    });
  }

  return record;
}

export function getReportedErrors(): FrontendErrorRecord[] {
  return [...currentBuffer()];
}

export function clearReportedErrors(): void {
  if (typeof window !== "undefined") window.__pingceErrors = [];
}
