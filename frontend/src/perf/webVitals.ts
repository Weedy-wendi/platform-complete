export const LCP_BUDGET_MS = 2500;

export interface LcpReport {
  metric: "LCP";
  value: number;
  budget: number;
  status: "good" | "over-budget";
}

export function evaluateLcp(value: number, budget: number = LCP_BUDGET_MS): LcpReport {
  const safeValue = Number.isFinite(value) && value >= 0 ? value : 0;
  return {
    metric: "LCP",
    value: safeValue,
    budget,
    status: safeValue <= budget ? "good" : "over-budget",
  };
}

export function describeLcp(report: LcpReport): string {
  return `LCP ${Math.round(report.value)}ms / budget ${report.budget}ms (${report.status})`;
}

function defaultReporter(report: LcpReport): void {
  if (report.status === "over-budget" && import.meta.env.DEV) {
    // Budget diagnostics only: no URL, query string, or user data is logged.
    console.warn(`[pingce] ${describeLcp(report)}`);
  }
}

/**
 * Observe Largest Contentful Paint via PerformanceObserver. Returns a cleanup
 * function, or undefined when the API is unavailable (SSR, older browsers, jsdom).
 */
export function observeLcp(reporter: (report: LcpReport) => void = defaultReporter): (() => void) | undefined {
  if (typeof PerformanceObserver === "undefined") return undefined;
  const supported = PerformanceObserver.supportedEntryTypes;
  if (!Array.isArray(supported) || !supported.includes("largest-contentful-paint")) {
    return undefined;
  }

  let lastEntry: PerformanceEntry | undefined;
  let observer: PerformanceObserver;
  try {
    observer = new PerformanceObserver((list) => {
      const entries = list.getEntries();
      lastEntry = entries[entries.length - 1] ?? lastEntry;
    });
    observer.observe({ type: "largest-contentful-paint", buffered: true });
  } catch {
    return undefined;
  }

  const flush = () => {
    if (lastEntry) reporter(evaluateLcp(lastEntry.startTime));
  };
  if (typeof document !== "undefined" && typeof document.addEventListener === "function") {
    document.addEventListener("visibilitychange", flush);
  }

  return () => {
    observer.disconnect();
    if (typeof document !== "undefined" && typeof document.removeEventListener === "function") {
      document.removeEventListener("visibilitychange", flush);
    }
  };
}
