import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { api } from "../../api";
import router from "../index";

vi.mock("../../api", () => ({
  api: { authMe: vi.fn(), login: vi.fn(), logout: vi.fn() },
}));

describe("auth 路由守卫", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setActivePinia(createPinia());
  });

  it("authMe 失败进入 error 态时 /login 可达，不被重定向", async () => {
    api.authMe.mockRejectedValue(new Error("network"));
    await router.push(`/login?t=${Date.now()}`);
    expect(router.currentRoute.value.path).toBe("/login");
  });

  it("需要认证且未登录时访问 /library 被重定向到 /login", async () => {
    api.authMe.mockResolvedValue({ auth_required: true, authenticated: false });
    await router.push(`/library?t=${Date.now()}`);
    expect(router.currentRoute.value.path).toBe("/login");
  });

  it("认证关闭时 /login 重定向到 /library", async () => {
    api.authMe.mockResolvedValue({ auth_required: false, authenticated: false });
    await router.push(`/login?t=${Date.now()}`);
    expect(router.currentRoute.value.path).toBe("/library");
  });
});
