import { formatNumber } from "@/i18n/format";

export type EvidenceKind = "screenshot" | "console" | "network" | "video" | "trace";

export interface EvidenceLink {
  kind: EvidenceKind;
  ref: string;
  url: string;
}

export interface FunctionalStep {
  id: string;
  name: string;
  status: string;
  durationMs: number | null;
  evidence: EvidenceLink[];
  mismatchRatio: number | null;
  visualPassed: boolean | null;
  visualRef: string;
}

const KIND_ALIASES: Record<string, EvidenceKind> = {
  screenshot: "screenshot",
  screenshots: "screenshot",
  image: "screenshot",
  img: "screenshot",
  console: "console",
  console_log: "console",
  consolelog: "console",
  logs: "console",
  log: "console",
  network: "network",
  network_log: "network",
  har: "network",
  video: "video",
  recording: "video",
  trace: "trace",
  trace_url: "trace",
  playwright_trace: "trace",
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function asText(value: unknown): string {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return "";
}

function asUrl(ref: string): string {
  return /^(https?:\/\/|\/|blob:)/i.test(ref) ? ref : "";
}

function normalizeKind(value: unknown, ref: string): EvidenceKind {
  const key = typeof value === "string" ? value.toLowerCase().replace(/[-\s]+/g, "_") : "";
  if (KIND_ALIASES[key]) return KIND_ALIASES[key];
  if (/\.(png|jpe?g|gif|webp|bmp|svg)(?:$|\?)/i.test(ref)) return "screenshot";
  if (/\.(webm|mp4|mov)(?:$|\?)/i.test(ref)) return "video";
  if (/console|\.log(?:$|\?)/i.test(ref)) return "console";
  if (/network|\.har(?:$|\?)/i.test(ref)) return "network";
  return "trace";
}

function evidenceFrom(value: unknown, kindHint?: string): EvidenceLink | null {
  if (typeof value === "string") {
    if (!value) return null;
    return { kind: normalizeKind(kindHint, value), ref: value, url: asUrl(value) };
  }
  if (!isRecord(value)) return null;
  const ref = asText(value.url ?? value.href ?? value.ref ?? value.path ?? value.evidence_ref);
  if (!ref) return null;
  return {
    kind: normalizeKind(value.kind ?? value.type ?? kindHint, ref),
    ref,
    url: asUrl(ref),
  };
}

function normalizeEvidence(step: Record<string, unknown>): EvidenceLink[] {
  const links: EvidenceLink[] = [];
  const seen = new Set<string>();
  const push = (link: EvidenceLink | null) => {
    if (!link || seen.has(link.ref)) return;
    seen.add(link.ref);
    links.push(link);
  };

  const raw = step.evidence ?? step.evidence_refs ?? step.artifacts;
  if (Array.isArray(raw)) {
    for (const entry of raw) push(evidenceFrom(entry));
  } else if (isRecord(raw)) {
    if (raw.url || raw.href || raw.ref || raw.path) {
      push(evidenceFrom(raw));
    } else {
      for (const [kind, value] of Object.entries(raw)) push(evidenceFrom(value, kind));
    }
  }

  const single = step.evidence_ref ?? step.evidenceRef;
  if (typeof single === "string") push(evidenceFrom(single));
  return links;
}

function asNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function asBoolean(value: unknown): boolean | null {
  if (typeof value === "boolean") return value;
  if (value === "true") return true;
  if (value === "false") return false;
  return null;
}

export function normalizeSteps(payload: unknown): FunctionalStep[] {
  if (!isRecord(payload)) return [];
  const source = payload.steps ?? payload.items;
  if (!Array.isArray(source)) return [];
  return source.map((entry, index) => {
    const step = isRecord(entry) ? entry : {};
    const name = asText(step.name ?? step.title ?? step.step_id ?? step.id) || `#${index + 1}`;
    const visual = isRecord(step.visual_diff)
      ? step.visual_diff
      : isRecord(step.visualDiff)
        ? step.visualDiff
        : {};
    return {
      id: asText(step.step_id ?? step.id) || String(index + 1),
      name,
      status: asText(step.status ?? step.result) || "unknown",
      durationMs: asNumber(step.duration_ms ?? step.durationMs ?? step.duration ?? step.elapsed_ms),
      evidence: normalizeEvidence(step),
      mismatchRatio: asNumber(
        visual.mismatch_ratio ?? visual.mismatchRatio ?? step.mismatch_ratio ?? step.mismatchRatio,
      ),
      visualPassed: asBoolean(visual.passed ?? step.visual_passed ?? step.visualPassed),
      visualRef: asText(
        visual.url ?? visual.ref ?? visual.diff_ref ?? step.visual_diff_ref ?? step.visualDiffRef,
      ),
    };
  });
}

export function statusTagType(status: string): "success" | "danger" | "warning" | "info" {
  switch (status.toLowerCase()) {
    case "passed":
    case "succeeded":
    case "success":
    case "ok":
      return "success";
    case "failed":
    case "error":
    case "timed_out":
      return "danger";
    case "cancelled":
    case "skipped":
      return "warning";
    default:
      return "info";
  }
}

export function formatDuration(ms: number | null, locale: string): string {
  if (ms === null || !Number.isFinite(ms)) return "-";
  if (ms < 1000) return `${formatNumber(ms, locale, { maximumFractionDigits: 0 })} ms`;
  return `${formatNumber(ms / 1000, locale, { maximumFractionDigits: 2 })} s`;
}

export function isPassedVisual(step: FunctionalStep): boolean {
  if (step.visualPassed !== null) return step.visualPassed;
  return step.mismatchRatio !== null && step.mismatchRatio < 0.01;
}
