import { maskRecord } from "@/utils/masking";

export interface SchemaField {
  field: string;
  type: string;
  nullable: boolean;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function asBoolean(value: unknown): boolean | undefined {
  if (typeof value === "boolean") return value;
  if (value === "true") return true;
  if (value === "false") return false;
  return undefined;
}

function fieldName(value: Record<string, unknown>): string {
  const candidate = value.field ?? value.name ?? value.key ?? value.column;
  return typeof candidate === "string" ? candidate : "";
}

function fieldType(value: unknown): string {
  if (typeof value === "string") return value;
  if (isRecord(value)) {
    const candidate = value.type ?? value.data_type ?? value.dtype;
    if (typeof candidate === "string") return candidate;
  }
  return "unknown";
}

function fieldNullable(value: Record<string, unknown>, fallback = true): boolean {
  const nullable = asBoolean(value.nullable);
  if (nullable !== undefined) return nullable;
  const required = asBoolean(value.required);
  if (required !== undefined) return !required;
  return fallback;
}

function normalizeEntry(entry: unknown): SchemaField | null {
  if (typeof entry === "string") {
    return { field: entry, type: "unknown", nullable: true };
  }
  if (!isRecord(entry)) return null;
  const name = fieldName(entry);
  if (!name) return null;
  return { field: name, type: fieldType(entry), nullable: fieldNullable(entry) };
}

/**
 * Accepts the shapes returned by the catalog API: a list of field objects, a
 * JSON Schema `properties` map, or a plain `{field: type}` map.
 */
export function normalizeSchema(schema: unknown): SchemaField[] {
  if (!schema) return [];
  if (Array.isArray(schema)) {
    return schema
      .map((entry) => normalizeEntry(entry))
      .filter((entry): entry is SchemaField => entry !== null);
  }
  if (!isRecord(schema)) return [];
  if (Array.isArray(schema.fields)) return normalizeSchema(schema.fields);
  if (isRecord(schema.properties)) {
    const required = new Set(
      Array.isArray(schema.required)
        ? schema.required.filter((item): item is string => typeof item === "string")
        : [],
    );
    return Object.entries(schema.properties).map(([field, definition]) => {
      if (isRecord(definition)) {
        return {
          field,
          type: fieldType(definition),
          nullable: fieldNullable(definition, !required.has(field)),
        };
      }
      return { field, type: fieldType(definition), nullable: !required.has(field) };
    });
  }
  return Object.entries(schema).map(([field, definition]) => {
    if (isRecord(definition)) {
      return { field, type: fieldType(definition), nullable: fieldNullable(definition) };
    }
    return { field, type: fieldType(definition), nullable: true };
  });
}

export function extractSchema(payload: unknown): SchemaField[] {
  if (!isRecord(payload)) return [];
  return normalizeSchema(payload.schema ?? payload.fields);
}

function sampleObject(value: unknown): Record<string, unknown> | null {
  if (!isRecord(value)) return null;
  const nested = value.payload;
  if (isRecord(nested)) {
    const sampleId = value.sample_id ?? value.id;
    return sampleId === undefined ? nested : { sample_id: sampleId, ...nested };
  }
  return value;
}

export function extractSamples(payload: unknown): Record<string, unknown>[] {
  if (!isRecord(payload)) return [];
  const lists = [payload.samples, payload.items, payload.rows, payload.data];
  const list = lists.find((candidate) => Array.isArray(candidate));
  if (!Array.isArray(list)) return [];
  return list
    .map((item) => sampleObject(item))
    .filter((item): item is Record<string, unknown> => item !== null);
}

export interface DatasetPreview {
  schema: SchemaField[];
  rows: Record<string, unknown>[];
  columns: string[];
}

export function buildDatasetPreview(payload: unknown, limit = 10): DatasetPreview {
  const rows = extractSamples(payload)
    .slice(0, limit)
    .map((row) => maskRecord(row));
  const columns: string[] = [];
  const seen = new Set<string>();
  for (const row of rows) {
    for (const key of Object.keys(row)) {
      if (seen.has(key)) continue;
      seen.add(key);
      columns.push(key);
      if (columns.length >= 12) break;
    }
    if (columns.length >= 12) break;
  }
  return { schema: extractSchema(payload), rows, columns };
}

export function displayCell(value: unknown): string {
  if (value === null || value === undefined) return "-";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}
