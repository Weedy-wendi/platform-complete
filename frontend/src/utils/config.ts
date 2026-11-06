export interface ConfigItem {
  id: string;
  name: string;
  description: string;
  version: string;
  kind?: string;
  config?: unknown;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function asText(value: unknown): string {
  if (typeof value === "string") return value;
  if (typeof value === "number") return String(value);
  return "";
}

export function normalizeConfigItems(payload: unknown): ConfigItem[] {
  const source = Array.isArray(payload)
    ? payload
    : isRecord(payload) && Array.isArray(payload.items)
      ? payload.items
      : [];
  return source
    .filter((entry): entry is Record<string, unknown> => isRecord(entry))
    .map((entry, index) => ({
      id: asText(entry.id ?? entry.suite_id ?? entry.target_id) || `#${index + 1}`,
      name: asText(entry.name ?? entry.title ?? entry.id),
      description: asText(entry.description),
      version: asText(entry.version),
      kind: asText(entry.kind) || undefined,
      config: entry.config,
    }));
}

export function configText(value: unknown): string {
  if (value === undefined || value === null) return "";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return "";
  }
}

export function parseConfigText(text: string): { ok: true; value: unknown } | { ok: false } {
  if (!text.trim()) return { ok: true, value: undefined };
  try {
    return { ok: true, value: JSON.parse(text) as unknown };
  } catch {
    return { ok: false };
  }
}
