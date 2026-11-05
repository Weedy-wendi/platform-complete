import { beforeEach, describe, expect, it } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { mount } from "@vue/test-utils";
import { nextTick } from "vue";
import PermissionGate from "@/components/PermissionGate.vue";
import { useAuthStore } from "@/stores/auth";
import { scopeGranted } from "@/auth/session";

describe("scope matching", () => {
  it("matches exact scopes, module wildcards and the global wildcard", () => {
    expect(scopeGranted(["runs:read"], "runs:read")).toBe(true);
    expect(scopeGranted(["runs:read"], "runs:write")).toBe(false);
    expect(scopeGranted(["runs:*"], "runs:write")).toBe(true);
    expect(scopeGranted(["*"], "admin:read")).toBe(true);
    expect(scopeGranted([], "projects:read")).toBe(false);
    expect(scopeGranted([], "")).toBe(true);
  });
});

describe("auth store permissions", () => {
  beforeEach(() => {
    sessionStorage.clear();
    localStorage.clear();
    setActivePinia(createPinia());
  });

  it("grants the default demo API-key scope set but not admin", () => {
    const auth = useAuthStore();
    auth.login("pk_test_abc");

    expect(auth.roles).toContain("evaluator");
    expect(auth.can("projects:read")).toBe(true);
    expect(auth.can("runs:write")).toBe(true);
    expect(auth.can("admin:read")).toBe(false);
    expect(auth.isAdmin).toBe(false);
  });

  it("supports granting and revoking scopes, persisted in sessionStorage", () => {
    const auth = useAuthStore();
    auth.login("pk_test_abc");
    auth.grantScope("admin:read");
    expect(auth.can("admin:read")).toBe(true);
    expect(JSON.parse(sessionStorage.getItem("pingce.scopes") ?? "[]")).toContain("admin:read");

    auth.revokeScope("admin:read");
    expect(auth.can("admin:read")).toBe(false);
  });

  it("stores the JWT placeholder token with tokenType jwt and no demo scopes", () => {
    const auth = useAuthStore();
    auth.loginWithJwt("eyJhbGciOiJIUzI1NiJ9.payload.signature", "tenant-j", {
      roles: ["viewer"],
    });

    expect(auth.tokenType).toBe("jwt");
    expect(auth.hasKey).toBe(true);
    expect(auth.can("runs:write")).toBe(false);
    expect(auth.roles).toEqual(["viewer"]);

    auth.logout();
    expect(auth.tokenType).toBe("apiKey");
    expect(sessionStorage.getItem("pingce.tokenType")).toBeNull();
  });
});

describe("PermissionGate", () => {
  beforeEach(() => {
    sessionStorage.clear();
    setActivePinia(createPinia());
  });

  it("hides content and renders the fallback when the scope is missing", () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    const auth = useAuthStore(pinia);
    auth.login("pk_test_abc");

    const wrapper = mount(PermissionGate, {
      props: { scope: "admin:read" },
      global: { plugins: [pinia] },
      slots: {
        default: "<button>admin action</button>",
        fallback: "<span class=\"denied\">denied</span>",
      },
    });

    expect(wrapper.find("button").exists()).toBe(false);
    expect(wrapper.find(".denied").exists()).toBe(true);
  });

  it("disables content without removing it when mode is disable", async () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    const auth = useAuthStore(pinia);
    auth.login("pk_test_abc");

    const wrapper = mount(PermissionGate, {
      props: { scope: "admin:read", mode: "disable" },
      global: { plugins: [pinia] },
      slots: { default: "<button>admin action</button>" },
    });

    expect(wrapper.find("button").exists()).toBe(true);
    expect(wrapper.find("[aria-disabled='true']").exists()).toBe(true);

    auth.grantScope("admin:read");
    await nextTick();
    expect(wrapper.find("[aria-disabled='true']").exists()).toBe(false);
  });
});
