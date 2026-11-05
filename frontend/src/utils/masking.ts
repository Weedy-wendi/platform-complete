export const MASKED_VALUE = "***";

const SECRET_KEY = /(password|passwd|secret|token|api[_-]?key|authorization|credential)/i;
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const PHONE = /^\+?[\d\s().-]{7,}$/;
const ISO_DATE = /^\d{4}-\d{2}-\d{2}(?:[T\s].*)?$/;

export function isSecretKey(key: string): boolean {
  return SECRET_KEY.test(key);
}

function isPhoneLike(value: string): boolean {
  if (ISO_DATE.test(value)) return false;
  if (!PHONE.test(value)) return false;
  const digits = value.replace(/\D/g, "");
  return digits.length >= 7 && digits.length <= 15;
}

/**
 * Mask PII before a sample is rendered. Values are masked by shape, not by
 * field name, so identifiers embedded in free text are still protected.
 */
export function maskValue(value: unknown): unknown {
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (EMAIL.test(trimmed)) {
      const [local, domain] = trimmed.split("@");
      return `${local.slice(0, 1)}***@${domain}`;
    }
    if (isPhoneLike(trimmed)) {
      const digits = trimmed.replace(/\D/g, "");
      const prefix = trimmed.startsWith("+") ? `+${digits.slice(0, 2)}` : digits.slice(0, 3);
      return `${prefix}****${digits.slice(-4)}`;
    }
    if (trimmed.length > 32) return `${trimmed.slice(0, 8)}…${trimmed.slice(-4)}`;
    return value;
  }
  if (Array.isArray(value)) return value.map((item) => maskValue(item));
  if (value && typeof value === "object") {
    return maskRecord(value as Record<string, unknown>);
  }
  return value;
}

export function maskRecord(record: Record<string, unknown>): Record<string, unknown> {
  const masked: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(record)) {
    masked[key] = isSecretKey(key) ? MASKED_VALUE : maskValue(value);
  }
  return masked;
}
