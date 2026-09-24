import { describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createPinia } from "pinia";
import App from "../../../App.vue";
import router from "../../../router";
import MobileHomeView from "../MobileHomeView.vue";

vi.mock("../../../api", () => ({
  api: {
    listGames: vi.fn().mockResolvedValue({ items: [] }),
    stats: vi.fn().mockResolvedValue({
      total: 0,
      reviewed: 0,
      new: 0,
      due: 0,
      mastered: 0,
    }),
    deleteGame: vi.fn(),
  },
}));

describe("MobileHomeView", () => {
  it("渲染移动端占位内容", () => {
    const wrapper = mount(MobileHomeView);
    expect(wrapper.text()).toContain("移动端界面");
  });

  it("上方渲染初始局面的棋盘", () => {
    const wrapper = mount(MobileHomeView);
    expect(wrapper.find("svg.chess-board").exists()).toBe(true);
    expect(wrapper.findAll("g")).toHaveLength(32);
  });
});

describe("移动端路由", () => {
  it("/m 解析到移动端布局与首页", () => {
    const resolved = router.resolve("/m");
    expect(resolved.matched).toHaveLength(2);
  });

  it("/m 下的未知路径回落到 /m", async () => {
    await router.push("/m/unknown");
    expect(router.currentRoute.value.path).toBe("/m");
  });
});

describe("App 按路由前缀分流 shell", () => {
  it("/m 下只渲染移动端 shell，不渲染旧 topbar/tabbar", async () => {
    await router.push("/m");
    await router.isReady();
    const wrapper = mount(App, {
      global: { plugins: [createPinia(), router] },
    });
    await flushPromises();

    expect(wrapper.find(".mobile-topbar").exists()).toBe(true);
    expect(wrapper.find(".topbar").exists()).toBe(false);
    expect(wrapper.find(".tabbar").exists()).toBe(false);
  });

  it("非 /m 路径仍渲染旧 topbar/tabbar", async () => {
    await router.push("/library");
    await router.isReady();
    const wrapper = mount(App, {
      global: { plugins: [createPinia(), router] },
    });
    await flushPromises();

    expect(wrapper.find(".topbar").exists()).toBe(true);
    expect(wrapper.find(".tabbar").exists()).toBe(true);
    expect(wrapper.find(".mobile-topbar").exists()).toBe(false);
  });
});
