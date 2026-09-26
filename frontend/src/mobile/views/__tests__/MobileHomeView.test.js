import { describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createPinia } from "pinia";
import App from "../../../App.vue";
import router from "../../../router";
import ChessBoard from "../../../components/ChessBoard.vue";
import MobileBoardEditor from "../../components/MobileBoardEditor.vue";
import { api } from "../../../api";
import { INITIAL_FEN } from "../../../utils/chess";
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

  it("棋盘下方渲染控制栏", () => {
    const wrapper = mount(MobileHomeView);
    expect(wrapper.findAll(".board-controls button")).toHaveLength(6);
  });

  it("点击翻转后棋盘翻转", async () => {
    const wrapper = mount(MobileHomeView);
    expect(wrapper.findComponent(ChessBoard).props("flipped")).toBe(false);
    await wrapper.find("[data-test='ctrl-flip']").trigger("click");
    expect(wrapper.findComponent(ChessBoard).props("flipped")).toBe(true);
  });

  it("点编辑打开弹窗", async () => {
    const wrapper = mount(MobileHomeView);
    expect(wrapper.find("[data-test='editor-card']").exists()).toBe(false);
    await wrapper.find("[data-test='ctrl-edit']").trigger("click");
    expect(wrapper.find("[data-test='editor-card']").exists()).toBe(true);
  });

  it("应用编辑后首页棋盘更新并关闭弹窗", async () => {
    const wrapper = mount(MobileHomeView);
    await wrapper.find("[data-test='ctrl-edit']").trigger("click");
    await wrapper.findComponent(MobileBoardEditor).vm.$emit("apply", []);
    expect(wrapper.findComponent(ChessBoard).props("position").pieces).toHaveLength(0);
    expect(wrapper.find("[data-test='editor-card']").exists()).toBe(false);
  });

  it("点打开显示棋谱选择器", async () => {
    const wrapper = mount(MobileHomeView);
    await wrapper.find("[data-test='open']").trigger("click");
    await flushPromises();
    expect(wrapper.find("[data-test='picker-card']").exists()).toBe(true);
  });

  it("选中棋谱后可前进打谱", async () => {
    api.listGames.mockResolvedValueOnce({
      items: [
        {
          id: 1,
          name: "测试局",
          initial_fen: INITIAL_FEN,
          moves: [{ x1: 0, y1: 0, x2: 0, y2: 1 }],
        },
      ],
    });
    const wrapper = mount(MobileHomeView);
    await wrapper.find("[data-test='open']").trigger("click");
    await flushPromises();
    await wrapper.find("[data-game='1']").trigger("click");
    await flushPromises();
    expect(wrapper.find("[data-test='ctrl-next']").attributes("disabled")).toBeUndefined();
    await wrapper.find("[data-test='ctrl-next']").trigger("click");
    const pieces = wrapper.findComponent(ChessBoard).props("position").pieces;
    expect(pieces.find((p) => p.x === 0 && p.y === 1)).toBeTruthy();
  });

  it("点设置显示设置弹窗", async () => {
    const wrapper = mount(MobileHomeView);
    await wrapper.find("[data-test='settings']").trigger("click");
    expect(wrapper.find("[data-test='settings-card']").exists()).toBe(true);
  });

  it("打谱中应用编辑后退出打谱", async () => {
    api.listGames.mockResolvedValueOnce({
      items: [
        {
          id: 1,
          name: "测试局",
          initial_fen: INITIAL_FEN,
          moves: [{ x1: 0, y1: 0, x2: 0, y2: 1 }],
        },
      ],
    });
    const wrapper = mount(MobileHomeView);
    await wrapper.find("[data-test='open']").trigger("click");
    await flushPromises();
    await wrapper.find("[data-game='1']").trigger("click");
    await flushPromises();
    await wrapper.find("[data-test='ctrl-edit']").trigger("click");
    await wrapper.findComponent(MobileBoardEditor).vm.$emit("apply", []);
    await flushPromises();
    expect(wrapper.find("[data-test='ctrl-next']").attributes("disabled")).toBeDefined();
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
    expect(wrapper.find(".mobile-tabbar").exists()).toBe(false);
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
