import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { nextTick } from "vue";
import { createPinia } from "pinia";
import App from "../../../App.vue";
import router from "../../../router";
import ChessBoard from "../../../components/ChessBoard.vue";
import MobileBoardEditor from "../../components/MobileBoardEditor.vue";
import { analyzeStream, api, intentStream } from "../../../api";
import { INITIAL_FEN } from "../../../utils/chess";
import MobileHomeView from "../MobileHomeView.vue";

vi.mock("../../../api", () => ({
  api: {
    listGames: vi.fn().mockResolvedValue({ items: [] }),
    listCollections: vi.fn().mockResolvedValue({ items: [] }),
    listEvents: vi.fn().mockResolvedValue({ items: [] }),
    openGame: vi.fn().mockResolvedValue({ last_opened_at: "2026", favorited: false }),
    favoriteGame: vi.fn().mockResolvedValue({ favorited: false, favorited_at: null }),
    stats: vi.fn().mockResolvedValue({
      total: 0,
      reviewed: 0,
      new: 0,
      due: 0,
      mastered: 0,
    }),
    deleteGame: vi.fn(),
  },
  analyzeStream: vi.fn(),
  intentStream: vi.fn(),
}));

describe("MobileHomeView", () => {
  beforeEach(() => {
    localStorage.clear();
    analyzeStream.mockReset();
    intentStream.mockReset();
  });

  async function openPicker() {
    window.dispatchEvent(new CustomEvent("mobile-open"));
    await flushPromises();
  }

  async function openSettings() {
    window.dispatchEvent(new CustomEvent("mobile-settings"));
    await flushPromises();
  }

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
    await openPicker();
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
    await openPicker();
    await wrapper.find("[data-test='menu-other']").trigger("click");
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
    await openSettings();
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
    await openPicker();
    await wrapper.find("[data-test='menu-other']").trigger("click");
    await flushPromises();
    await wrapper.find("[data-game='1']").trigger("click");
    await flushPromises();
    await wrapper.find("[data-test='ctrl-edit']").trigger("click");
    await wrapper.findComponent(MobileBoardEditor).vm.$emit("apply", []);
    await flushPromises();
    expect(wrapper.find("[data-test='ctrl-next']").attributes("disabled")).toBeDefined();
  });

  async function loadGame(wrapper, game) {
    api.listGames.mockResolvedValueOnce({ items: [game] });
    await openPicker();
    await wrapper.find("[data-test='menu-other']").trigger("click");
    await flushPromises();
    await wrapper.find(`[data-game='${game.id}']`).trigger("click");
    await flushPromises();
  }

  it("未打开棋谱时不显示收藏按钮", () => {
    const wrapper = mount(MobileHomeView);
    expect(wrapper.find("[data-test='favorite']").exists()).toBe(false);
  });

  it("载入棋谱后显示空心星标并记录打开", async () => {
    const wrapper = mount(MobileHomeView);
    await loadGame(wrapper, {
      id: 5,
      name: "局",
      initial_fen: INITIAL_FEN,
      moves: [],
      favorited: false,
    });
    expect(api.openGame).toHaveBeenCalledWith(5);
    expect(wrapper.find("[data-test='favorite']").text()).toContain("☆");
  });

  it("已收藏的棋谱显示实心星标", async () => {
    api.openGame.mockResolvedValueOnce({ last_opened_at: "2026", favorited: true });
    const wrapper = mount(MobileHomeView);
    await loadGame(wrapper, {
      id: 6,
      name: "藏",
      initial_fen: INITIAL_FEN,
      moves: [],
      favorited: true,
    });
    expect(wrapper.find("[data-test='favorite']").text()).toContain("★");
  });

  it("点击星标切换为已收藏", async () => {
    const wrapper = mount(MobileHomeView);
    await loadGame(wrapper, {
      id: 7,
      name: "局",
      initial_fen: INITIAL_FEN,
      moves: [],
      favorited: false,
    });
    api.favoriteGame.mockResolvedValueOnce({ favorited: true, favorited_at: "2026" });
    await wrapper.find("[data-test='favorite']").trigger("click");
    await flushPromises();
    expect(api.favoriteGame).toHaveBeenCalledWith(7);
    expect(wrapper.find("[data-test='favorite']").text()).toContain("★");
  });

  it("设置开关持久化到 localStorage", async () => {
    const wrapper = mount(MobileHomeView);
    await openSettings();
    await wrapper.find("[data-test='setting-score']").setValue(true);
    expect(JSON.parse(localStorage.getItem("chess:mobile-settings"))).toEqual({
      score: true,
      intent: false,
    });
  });

  it("开启评分后显示评分条", () => {
    localStorage.setItem("chess:mobile-settings", JSON.stringify({ score: true, intent: false }));
    const wrapper = mount(MobileHomeView);
    expect(wrapper.find("[data-test='mobile-score']").exists()).toBe(true);
  });

  it("分析结果在棋盘上展示最新两着法箭头", async () => {
    localStorage.setItem("chess:mobile-settings", JSON.stringify({ score: true, intent: false }));
    analyzeStream.mockImplementation((payload, { onResult }) => {
      onResult({
        depth: 9,
        score_red: 5,
        mate: null,
        pv: [
          { x1: 0, y1: 0, x2: 0, y2: 1 },
          { x1: 1, y1: 0, x2: 1, y2: 1 },
        ],
        time_ms: 3,
      });
    });
    const wrapper = mount(MobileHomeView);
    await nextTick();
    const arrows = wrapper.findComponent(ChessBoard).props("arrows");
    expect(arrows).toHaveLength(2);
    expect(arrows.map((a) => a.kind)).toEqual(["best", "reply"]);
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
