import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiDownload, sanitizeFilename } from "@/api/client";
import { absoluteShareUrl } from "@/utils/share";

const SECRET = "pk_live_SECRET123";

function csvResponse(): Response {
  const blob = new Blob(["sample_id,score\ns1,0.9\n"], { type: "text/csv" });
  return {
    status: 200,
    ok: true,
    blob: async () => blob,
    json: async () => ({}),
    text: async () => "",
  } as unknown as Response;
}

describe("apiDownload", () => {
  beforeEach(() => {
    sessionStorage.clear();
    sessionStorage.setItem("pingce.apiKey", SECRET);
    vi.spyOn(console, "warn").mockImplementation(() => {});
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("requests the /v1 path with the auth header and never leaks the key into the URL", async () => {
    const fetchMock = vi.fn().mockResolvedValue(csvResponse());
    vi.stubGlobal("fetch", fetchMock);

    const createObjectURL = vi.fn().mockReturnValue("blob:report");
    const revokeObjectURL = vi.fn();
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: createObjectURL });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: revokeObjectURL });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    const blob = await apiDownload("/reports/run-1?format=csv", "report-run-1.csv", {
      headers: { Accept: "text/csv" },
    });

    expect(blob).toBeInstanceOf(Blob);
    const [path, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(path).toBe("/v1/reports/run-1?format=csv");
    expect(path).not.toContain(SECRET);
    expect(init.method ?? "GET").toBe("GET");
    const headers = init.headers as Record<string, string>;
    expect(headers.Authorization).toBe(`Bearer ${SECRET}`);
    expect(headers.Accept).toBe("text/csv");
    expect(createObjectURL).toHaveBeenCalledTimes(1);
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:report");
    expect(click).toHaveBeenCalledTimes(1);
  });

  it("sanitizes download filenames", () => {
    expect(sanitizeFilename("report-run 1.csv")).toBe("report-run_1.csv");
    expect(sanitizeFilename("../secret/report.csv")).toBe("report.csv");
    expect(sanitizeFilename("....")).toBe("download");
  });
});

describe("share links", () => {
  beforeEach(() => {
    sessionStorage.clear();
    sessionStorage.setItem("pingce.apiKey", SECRET);
  });

  it("builds absolute URLs without credentials", () => {
    const url = absoluteShareUrl("/v1/reports/share/abc", "https://app.example.com");
    expect(url).toBe("https://app.example.com/v1/reports/share/abc");
    expect(url).not.toContain(SECRET);
    expect(url).not.toContain("apiKey");

    expect(absoluteShareUrl("https://cdn.example.com/report", "https://app.example.com")).toBe(
      "https://cdn.example.com/report",
    );
    expect(absoluteShareUrl("", "https://app.example.com")).toBe("");
  });
});
