export const UTC_TIME_ZONE = "UTC";

export type DateInput = string | number | Date | null | undefined;

function toDate(value: DateInput): Date | null {
  if (value === null || value === undefined || value === "") return null;
  const date = value instanceof Date ? value : new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

/**
 * Render a timestamp in UTC with an explicit "UTC" suffix so operators never
 * mistake a localized clock for a timezone conversion.
 */
export function formatUtcTimestamp(value: DateInput, locale: string): string {
  const date = toDate(value);
  if (!date) return String(value ?? "");
  const formatted = new Intl.DateTimeFormat(locale, {
    timeZone: UTC_TIME_ZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(date);
  return `${formatted} UTC`;
}

export function formatNumber(
  value: number | null | undefined,
  locale: string,
  options: Intl.NumberFormatOptions = {},
): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return new Intl.NumberFormat(locale, options).format(value);
}

export function formatCurrency(
  value: number | null | undefined,
  locale: string,
  currency = "USD",
): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency,
    maximumFractionDigits: 4,
  }).format(value);
}

export function formatPercent(
  value: number | null | undefined,
  locale: string,
  fractionDigits = 1,
): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return new Intl.NumberFormat(locale, {
    style: "percent",
    minimumFractionDigits: 0,
    maximumFractionDigits: fractionDigits,
  }).format(value);
}
