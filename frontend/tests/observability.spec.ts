import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  clearReportedErrors,
  getReportedErrors,
  MAX_REPORTED_ERRORS,
  reportError,
  sanitizeErrorText,
} from "@/observability/errors";

const SECRET = "pk_live_SECRET123";

describe("frontend error reporting", () => {
  beforeEach(() => {
    clearReportedErrors();
    vi.spyOn(console, "warn").mockImplementation(() => {});
  });

  it("keeps a bounded in-memory ring buffer on window.__pingceErrors", () => {
    for (let index = 0; index < MAX_REPORTED_ERRORS + 25; index += 1) {
      reportError(new Error(`failure ${index}`));
    }

    const reported = getReportedErrors();
    expect(reported).toHaveLength(MAX_REPORTED_ERRORS);
    expect(window.__pingceErrors).toHaveLength(MAX_REPORTED_ERRORS);
    expect(reported[0]?.message).toBe("failure 25");
    expect(reported.at(-1)?.message).toBe(`failure ${MAX_REPORTED_ERRORS + 24}`);
  });

  it("captures only code, message, trace_id and timestamp", () => {
    const error = Object.assign(new Error("failed to load run"), {
      code: "RUN_LOAD_FAILED",
      stack: "Error: secret stack",
      body: { api_key: SECRET },
    });
    const record = reportError(error, "trace-1");

    expect(Object.keys(record).sort()).toEqual(["at", "code", "message", "trace_id"]);
    expect(record.code).toBe("RUN_LOAD_FAILED");
    expect(record.message).toBe("failed to load run");
    expect(record.trace_id).toBe("trace-1");
    expect(JSON.stringify(record)).not.toContain("secret stack");
    expect(JSON.stringify(record)).not.toContain(SECRET);
  });

  it("redacts API keys, bearer tokens, JWTs and URL secrets", () => {
    expect(sanitizeErrorText(`request failed for ${SECRET}`)).not.toContain(SECRET);
    expect(sanitizeErrorText(`Authorization: Bearer ${SECRET}`)).not.toContain(SECRET);
    expect(sanitizeErrorText("token=super-secret-value")).not.toContain("super-secret-value");
    expect(
      sanitizeErrorText("https://example.test/v1/runs?api_key=pk_live_SECRET123&limit=20"),
    ).not.toContain(SECRET);
    expect(
      sanitizeErrorText("login eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.signature"),
    ).not.toContain("eyJhbGciOiJIUzI1NiJ9");
  });

  it("never stores the API key even when it is part of the message and trace id", () => {
    reportError(new Error(`boom ${SECRET}`), `trace-${SECRET}`);
    const serialized = JSON.stringify(getReportedErrors());

    expect(serialized).not.toContain(SECRET);
    expect(serialized).toContain("[redacted");
  });
});
