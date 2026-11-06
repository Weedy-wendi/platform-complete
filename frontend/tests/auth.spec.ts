import { beforeEach, describe, expect, it } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { useAuthStore } from "@/stores/auth";

describe("auth store", () => {
  beforeEach(() => {
    sessionStorage.clear();
    setActivePinia(createPinia());
  });

  it("stores the API key only in sessionStorage", () => {
    const auth = useAuthStore();
    auth.login("pk_test_abc", "tenant-a");
    expect(auth.hasKey).toBe(true);
    expect(sessionStorage.getItem("pingce.apiKey")).toBe("pk_test_abc");
    expect(localStorage.getItem("pingce.apiKey")).toBeNull();
    expect(document.cookie).not.toContain("pk_test_abc");
  });

  it("clears credentials on logout", () => {
    const auth = useAuthStore();
    auth.login("pk_test_abc");
    auth.logout();
    expect(auth.hasKey).toBe(false);
    expect(sessionStorage.getItem("pingce.apiKey")).toBeNull();
  });
});
