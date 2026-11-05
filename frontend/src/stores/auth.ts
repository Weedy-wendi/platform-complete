import { defineStore } from "pinia";
import {
  API_KEY_STORAGE_KEY,
  DEFAULT_API_KEY_ROLES,
  DEFAULT_API_KEY_SCOPES,
  isTokenType,
  clearStoredCredentials,
  readStoredList,
  ROLES_STORAGE_KEY,
  SCOPES_STORAGE_KEY,
  scopeGranted,
  TENANT_STORAGE_KEY,
  TOKEN_TYPE_STORAGE_KEY,
  writeStoredList,
  type TokenType,
} from "@/auth/session";

export interface LoginOptions {
  scopes?: readonly string[];
  roles?: readonly string[];
  tokenType?: TokenType;
}

function initialTokenType(): TokenType {
  const stored = sessionStorage.getItem(TOKEN_TYPE_STORAGE_KEY);
  return isTokenType(stored) ? stored : "apiKey";
}

export const useAuthStore = defineStore("auth", {
  state: () => ({
    apiKey: sessionStorage.getItem(API_KEY_STORAGE_KEY) ?? "",
    tenantId: sessionStorage.getItem(TENANT_STORAGE_KEY) ?? "",
    tokenType: initialTokenType(),
    scopes: readStoredList(SCOPES_STORAGE_KEY) as string[],
    roles: readStoredList(ROLES_STORAGE_KEY) as string[],
  }),
  getters: {
    hasKey: (state) => state.apiKey.length > 0,
    isJwt: (state) => state.tokenType === "jwt",
    can: (state) => (scope: string) => scopeGranted(state.scopes, scope),
    isAdmin: (state) => scopeGranted(state.scopes, "admin:read"),
  },
  actions: {
    login(apiKey: string, tenantId = "", options: LoginOptions = {}) {
      this.apiKey = apiKey.trim();
      this.tenantId = tenantId.trim();
      this.tokenType = options.tokenType ?? "apiKey";
      this.scopes = [...(options.scopes ?? DEFAULT_API_KEY_SCOPES)];
      this.roles = [...(options.roles ?? DEFAULT_API_KEY_ROLES)];

      sessionStorage.setItem(API_KEY_STORAGE_KEY, this.apiKey);
      sessionStorage.setItem(TOKEN_TYPE_STORAGE_KEY, this.tokenType);
      writeStoredList(SCOPES_STORAGE_KEY, this.scopes);
      writeStoredList(ROLES_STORAGE_KEY, this.roles);
      if (this.tenantId) sessionStorage.setItem(TENANT_STORAGE_KEY, this.tenantId);
      else sessionStorage.removeItem(TENANT_STORAGE_KEY);
    },
    /**
     * JWT/OIDC placeholder path. Token validation and scope resolution are
     * server-side concerns; the client only stores the bearer token in memory
     * and sessionStorage.
     */
    loginWithJwt(token: string, tenantId = "", options: Omit<LoginOptions, "tokenType"> = {}) {
      this.login(token, tenantId, {
        ...options,
        tokenType: "jwt",
        scopes: options.scopes ?? [],
        roles: options.roles ?? [],
      });
    },
    grantScope(scope: string) {
      if (this.scopes.includes(scope)) return;
      this.scopes = [...this.scopes, scope];
      writeStoredList(SCOPES_STORAGE_KEY, this.scopes);
    },
    revokeScope(scope: string) {
      this.scopes = this.scopes.filter((item) => item !== scope);
      writeStoredList(SCOPES_STORAGE_KEY, this.scopes);
    },
    logout() {
      this.apiKey = "";
      this.tenantId = "";
      this.tokenType = "apiKey";
      this.scopes = [];
      this.roles = [];
      clearStoredCredentials();
    },
  },
});
