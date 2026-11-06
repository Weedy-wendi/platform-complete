export type TokenType = "apiKey" | "jwt";

export const API_KEY_STORAGE_KEY = "pingce.apiKey";
export const TENANT_STORAGE_KEY = "pingce.tenant";
export const TOKEN_TYPE_STORAGE_KEY = "pingce.tokenType";
export const SCOPES_STORAGE_KEY = "pingce.scopes";
export const ROLES_STORAGE_KEY = "pingce.roles";

export const DEFAULT_API_KEY_SCOPES = [
  "projects:read",
  "datasets:read",
  "runs:read",
  "runs:write",
  "evaluators:read",
  "evaluators:write",
  "gates:read",
  "reports:read",
  "badcases:read",
  "functional:read",
  "settings:read",
] as const;

export const DEFAULT_API_KEY_ROLES = ["evaluator"] as const;

export function isTokenType(value: unknown): value is TokenType {
  return value === "apiKey" || value === "jwt";
}

export function readStoredList(key: string): string[] {
  try {
    const raw = sessionStorage.getItem(key);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === "string") : [];
  } catch {
    return [];
  }
}

export function writeStoredList(key: string, values: readonly string[]): void {
  sessionStorage.setItem(key, JSON.stringify([...values]));
}

/**
 * Removes every credential and authorization artefact from session storage.
 * Used by logout and by the API client on 401.
 */
export function clearStoredCredentials(): void {
  sessionStorage.removeItem(API_KEY_STORAGE_KEY);
  sessionStorage.removeItem(TENANT_STORAGE_KEY);
  sessionStorage.removeItem(TOKEN_TYPE_STORAGE_KEY);
  sessionStorage.removeItem(SCOPES_STORAGE_KEY);
  sessionStorage.removeItem(ROLES_STORAGE_KEY);
}

/**
 * Scope matching supports exact scopes, module wildcards ("runs:*") and the
 * global wildcard ("*").
 */
export function scopeGranted(granted: readonly string[], scope: string): boolean {
  if (!scope) return true;
  if (granted.includes("*") || granted.includes(scope)) return true;
  const [module] = scope.split(":");
  return module ? granted.includes(`${module}:*`) : false;
}
