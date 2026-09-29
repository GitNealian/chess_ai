import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { api } from "../../api";
import LoginView from "../LoginView.vue";

const replace = vi.fn();
let query = {};

vi.mock("../../api", () => ({
  api: { login: vi.fn(), logout: vi.fn(), authMe: vi.fn() },
}));

vi.mock("vue-router", () => ({
  useRouter: () => ({ replace }),
  useRoute: () => ({ query }),
}));

async function submit(password = "pw") {
  const wrapper = mount(LoginView);
  await wrapper.find('[data-test="password"]').setValue(password);
  await wrapper.find("form").trigger("submit");
  await flushPromises();
  return wrapper;
}

describe("LoginView 登录后回跳", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    query = {};
    setActivePinia(createPinia());
    api.login.mockResolvedValue({ ok: true });
  });

  it("有合法 redirect 时回跳该站内路径", async () => {
    query = { redirect: "/m" };
    await submit();
    expect(api.login).toHaveBeenCalledWith("pw");
    expect(replace).toHaveBeenCalledWith("/m");
  });

  it("无 redirect 时回退 /", async () => {
    await submit();
    expect(replace).toHaveBeenCalledWith("/");
  });

  it("redirect 为 //evil.com 等非法值时回退 /", async () => {
    query = { redirect: "//evil.com" };
    await submit();
    expect(replace).toHaveBeenCalledWith("/");
  });

  it("redirect 为绝对外链时回退 /", async () => {
    query = { redirect: "https://evil.com" };
    await submit();
    expect(replace).toHaveBeenCalledWith("/");
  });

  it("登录失败显示错误且不跳转", async () => {
    api.login.mockRejectedValueOnce({ response: { data: { detail: "密码错误" } } });
    const wrapper = await submit("bad");
    expect(replace).not.toHaveBeenCalled();
    expect(wrapper.find('[data-test="error"]').text()).toBe("密码错误");
  });
});
