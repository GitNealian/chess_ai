import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { useAuthStore } from "../auth";
import { api } from "../../api";

vi.mock("../../api", () => ({
  api: { login: vi.fn(), logout: vi.fn(), authMe: vi.fn() },
}));

describe("auth store", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setActivePinia(createPinia());
  });

  it("ensureReady 只拉一次 me", async () => {
    api.authMe.mockResolvedValue({ auth_required: true, authenticated: false });
    const store = useAuthStore();
    await store.ensureReady();
    await store.ensureReady();
    expect(api.authMe).toHaveBeenCalledTimes(1);
    expect(store.authRequired).toBe(true);
  });

  it("login 成功置位，失败保持未登录", async () => {
    api.login.mockResolvedValueOnce({ ok: true });
    const store = useAuthStore();
    await store.login("pw");
    expect(store.authenticated).toBe(true);
    api.login.mockRejectedValueOnce(new Error("密码错误"));
    await expect(store.login("bad")).rejects.toThrow();
    expect(store.authenticated).toBe(false);
  });

  it("logout 复位", async () => {
    api.logout.mockResolvedValue({ ok: true });
    const store = useAuthStore();
    store.authenticated = true;
    await store.logout();
    expect(store.authenticated).toBe(false);
  });
});
