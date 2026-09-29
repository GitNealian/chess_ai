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

  it("需要认证且未登录时访问根路径被重定向到 /login 且带来源", async () => {
    api.authMe.mockResolvedValue({ auth_required: true, authenticated: false });
    await router.push("/");
    expect(router.currentRoute.value.path).toBe("/login");
    expect(router.currentRoute.value.query.redirect).toBe("/");
  });

  it("认证关闭时 /login 重定向到根路径", async () => {
    api.authMe.mockResolvedValue({ auth_required: false, authenticated: false });
    await router.push(`/login?t=${Date.now()}`);
    expect(router.currentRoute.value.path).toBe("/");
  });

  it("访问旧路径 /m 会被重定向到根路径", async () => {
    api.authMe.mockResolvedValue({ auth_required: false, authenticated: false });
    await router.push(`/m?t=${Date.now()}`);
    expect(router.currentRoute.value.path).toBe("/");
  });
});
