import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { nextTick } from "vue";
import { createPinia } from "pinia";
import App from "../../../App.vue";
import router from "../../../router";
import ChessBoard from "../../../components/ChessBoard.vue";
import MobileBoardEditor from "../../components/MobileBoardEditor.vue";
import MobileScanDialog from "../../components/MobileScanDialog.vue";
import MobileGamePicker from "../../components/MobileGamePicker.vue";
import { analyzeStream, api, intentStream } from "../../../api";
import { INITIAL_FEN } from "../../../utils/chess";
import MobileHomeView from "../MobileHomeView.vue";

vi.mock("../../../api", () => ({
  api: {
    listGames: vi.fn().mockResolvedValue({ items: [] }),
    listCollections: vi.fn().mockResolvedValue({ items: [] }),
    listEvents: vi.fn().mockResolvedValue({ items: [] }),
    reviewQueue: vi.fn().mockResolvedValue({ items: [] }),
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
    validateMove: vi.fn(),
    bestMove: vi.fn(),
    recognize: vi.fn(),
    checkMove: vi.fn(),
    submitReview: vi.fn().mockResolvedValue({}),
    variationChildren: vi
      .fn()
      .mockResolvedValue({ branchable: false, plies: null, branches: [] }),
    getGame: vi.fn(),
  },
  analyzeStream: vi.fn(),
  intentStream: vi.fn(),
}));

describe("MobileHomeView", () => {
  beforeEach(() => {
    localStorage.clear();
    analyzeStream.mockReset();
    intentStream.mockReset();
    api.validateMove.mockReset();
    api.bestMove.mockReset();
    api.recognize.mockReset();
    api.variationChildren.mockReset();
    api.variationChildren.mockResolvedValue({
      branchable: false,
      plies: null,
      branches: [],
    });
    api.getGame.mockReset();
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
    const labels = wrapper.findAll(".board-controls button").map((b) => b.text());
    expect(labels).toEqual(["开局", "后退", "前进", "终局", "翻转", "悔棋", "编辑", "扫描"]);
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

  it("点扫描打开扫描弹窗", async () => {
    const wrapper = mount(MobileHomeView);
    expect(wrapper.find("[data-test='scan-card']").exists()).toBe(false);
    await wrapper.find("[data-test='ctrl-scan']").trigger("click");
    expect(wrapper.find("[data-test='scan-card']").exists()).toBe(true);
  });

  it("扫描应用后首页棋盘更新并关闭弹窗", async () => {
    const wrapper = mount(MobileHomeView);
    await wrapper.find("[data-test='ctrl-scan']").trigger("click");
    await wrapper.findComponent(MobileScanDialog).vm.$emit("apply", []);
    expect(wrapper.findComponent(ChessBoard).props("position").pieces).toHaveLength(0);
    expect(wrapper.find("[data-test='scan-card']").exists()).toBe(false);
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

  function captureFavoriteStates() {
    const events = [];
    const listener = (e) => events.push(e.detail);
    window.addEventListener("mobile-favorite-state", listener);
    return events;
  }

  it("未打开棋谱时不发布收藏状态", () => {
    const events = captureFavoriteStates();
    mount(MobileHomeView);
    expect(events).toHaveLength(0);
  });

  it("载入棋谱后发布收藏状态并记录打开", async () => {
    const events = captureFavoriteStates();
    const wrapper = mount(MobileHomeView);
    await loadGame(wrapper, {
      id: 5,
      name: "局",
      initial_fen: INITIAL_FEN,
      moves: [],
      favorited: false,
    });
    expect(api.openGame).toHaveBeenCalledWith(5);
    expect(events.at(-1)).toEqual({ shown: true, filled: false });
  });

  it("古谱集到达分叉局面点前进弹出变着选择", async () => {
    api.listGames.mockResolvedValueOnce({
      items: [
        {
          id: 11,
          name: "甲",
          category: "古谱 · 测试集",
          initial_fen: INITIAL_FEN,
          moves: [
            { x1: 0, y1: 0, x2: 0, y2: 1 },
            { x1: 0, y1: 9, x2: 0, y2: 8 },
          ],
        },
      ],
    });
    api.variationChildren.mockResolvedValue({
      fen: INITIAL_FEN,
      branchable: true,
      plies: { min: 5, max: 5 },
      branches: [
        {
          move: { x1: 0, y1: 0, x2: 0, y2: 1, chinese: "车九进一" },
          to_fen: "a",
          games: [{ id: 11, name: "甲" }],
          end_games: [],
        },
        {
          move: { x1: 0, y1: 9, x2: 0, y2: 8, chinese: "车1进1" },
          to_fen: "b",
          games: [{ id: 12, name: "乙" }],
          end_games: [],
        },
      ],
    });
    const wrapper = mount(MobileHomeView);
    await openPicker();
    await wrapper.find("[data-test='menu-other']").trigger("click");
    await flushPromises();
    await wrapper.find("[data-game='11']").trigger("click");
    await flushPromises();

    expect(api.variationChildren).toHaveBeenCalled();
    expect(wrapper.find("[data-test='ctrl-variation']").exists()).toBe(false);
    await wrapper.find("[data-test='ctrl-next']").trigger("click");
    await flushPromises();
    expect(wrapper.find("[data-test='variation-card']").exists()).toBe(true);

    await wrapper.find("[data-variation='1']").trigger("click");
    await flushPromises();
    expect(wrapper.find("[data-test='variation-card']").exists()).toBe(false);
    expect(wrapper.find("[data-test='ctrl-prev']").attributes("disabled")).toBeUndefined();
  });

  it("非棋谱集点前进不弹变着", async () => {
    api.listGames.mockResolvedValueOnce({
      items: [
        {
          id: 21,
          name: "普通",
          initial_fen: INITIAL_FEN,
          moves: [{ x1: 0, y1: 0, x2: 0, y2: 1 }],
        },
      ],
    });
    const wrapper = mount(MobileHomeView);
    await openPicker();
    await wrapper.find("[data-test='menu-other']").trigger("click");
    await flushPromises();
    await wrapper.find("[data-game='21']").trigger("click");
    await flushPromises();
    expect(api.variationChildren).not.toHaveBeenCalled();
    await wrapper.find("[data-test='ctrl-next']").trigger("click");
    await flushPromises();
    expect(wrapper.find("[data-test='variation-card']").exists()).toBe(false);
  });

  it("已收藏的棋谱发布 filled=true", async () => {
    api.openGame.mockResolvedValueOnce({ last_opened_at: "2026", favorited: true });
    const events = captureFavoriteStates();
    const wrapper = mount(MobileHomeView);
    await loadGame(wrapper, {
      id: 6,
      name: "藏",
      initial_fen: INITIAL_FEN,
      moves: [],
      favorited: true,
    });
    expect(events.at(-1)).toEqual({ shown: true, filled: true });
  });

  it("顶栏收藏事件触发收藏切换", async () => {
    const wrapper = mount(MobileHomeView);
    await loadGame(wrapper, {
      id: 7,
      name: "局",
      initial_fen: INITIAL_FEN,
      moves: [],
      favorited: false,
    });
    api.favoriteGame.mockResolvedValueOnce({ favorited: true, favorited_at: "2026" });
    window.dispatchEvent(new CustomEvent("mobile-toggle-favorite"));
    await flushPromises();
    expect(api.favoriteGame).toHaveBeenCalledWith(7);
  });

  it("设置开关持久化到 localStorage", async () => {
    const wrapper = mount(MobileHomeView);
    await openSettings();
    await wrapper.find("[data-test='setting-score']").setValue(true);
    expect(JSON.parse(localStorage.getItem("chess:mobile-settings"))).toEqual({
      score: true,
      intent: false,
      level: "normal",
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

  it("关闭评分后棋盘箭头清除（意图仍开启）", async () => {
    localStorage.setItem(
      "chess:mobile-settings",
      JSON.stringify({ score: true, intent: true, level: "normal" })
    );
    intentStream.mockImplementation((payload, { onDone }) => onDone());
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
    expect(wrapper.findComponent(ChessBoard).props("arrows")).toHaveLength(2);
    await openSettings();
    await wrapper.find("[data-test='setting-score']").setValue(false);
    await flushPromises();
    expect(wrapper.findComponent(ChessBoard).props("arrows")).toEqual([]);
  });

  it("设置中可选引擎执子与思考程度", async () => {
    const wrapper = mount(MobileHomeView);
    await openSettings();
    expect(wrapper.find("[data-test='engine-none']").element.checked).toBe(true);
    expect(wrapper.find("[data-test='level-normal']").element.checked).toBe(true);
    await wrapper.find("[data-test='level-hard']").setValue();
    expect(JSON.parse(localStorage.getItem("chess:mobile-settings")).level).toBe("hard");
  });

  it("选择引擎执红后引擎自动走子，玩家走子经校验", async () => {
    api.bestMove.mockResolvedValue({
      legal: true,
      move: { x1: 0, y1: 3, x2: 0, y2: 4 },
      check: false,
      game_over: null,
    });
    api.validateMove.mockResolvedValue({ legal: true, chinese: "车九进一", check: false });
    const wrapper = mount(MobileHomeView);
    await openSettings();
    await wrapper.find("[data-test='engine-red']").setValue();
    await flushPromises();
    expect(api.bestMove).toHaveBeenCalledTimes(1);
    expect(api.bestMove.mock.calls[0][0]).toMatchObject({ level: "normal" });
    const board = wrapper.findComponent(ChessBoard);
    expect(board.props("lastMove")).toMatchObject({ x2: 0, y2: 4 });
    expect(wrapper.find("[data-test='status']").exists()).toBe(false);
    await wrapper.find("[data-cell='0-9']").trigger("click");
    await wrapper.find("[data-cell='0-8']").trigger("click");
    await flushPromises();
    expect(api.validateMove).toHaveBeenCalledTimes(1);
  });

  it("对弈中可悔棋，撤销到玩家回合", async () => {
    api.bestMove.mockResolvedValue({
      legal: true,
      move: { x1: 0, y1: 3, x2: 0, y2: 4 },
      check: false,
      game_over: null,
    });
    const wrapper = mount(MobileHomeView);
    await openSettings();
    await wrapper.find("[data-test='engine-red']").setValue();
    await flushPromises();
    expect(wrapper.find("[data-test='ctrl-undo']").exists()).toBe(true);
    await wrapper.find("[data-test='ctrl-undo']").trigger("click");
    expect(wrapper.findComponent(ChessBoard).props("lastMove")).toBeFalsy();
  });

  it("打开新棋谱后引擎执子重置为不启用", async () => {
    api.bestMove.mockResolvedValue({
      legal: true,
      move: { x1: 0, y1: 3, x2: 0, y2: 4 },
      check: false,
      game_over: null,
    });
    const wrapper = mount(MobileHomeView);
    await openSettings();
    await wrapper.find("[data-test='engine-red']").setValue();
    await flushPromises();
    expect(wrapper.find("[data-test='ctrl-undo']").exists()).toBe(true);
    await wrapper.find("[data-test='settings-close']").trigger("click");
    api.listGames.mockResolvedValueOnce({
      items: [{ id: 1, name: "局", initial_fen: INITIAL_FEN, moves: [] }],
    });
    await openPicker();
    await flushPromises();
    await wrapper.find("[data-test='menu-other']").trigger("click");
    await flushPromises();
    await wrapper.find("[data-game='1']").trigger("click");
    await flushPromises();
    expect(wrapper.find("[data-test='ctrl-undo']").exists()).toBe(false);
    expect(wrapper.find("[data-test='status']").exists()).toBe(false);
  });

  it("未打开棋谱时 engineSide 为 none 也可自定义走子", async () => {
    api.validateMove.mockResolvedValue({ legal: true, chinese: "车九进一", check: false });
    const wrapper = mount(MobileHomeView);
    await wrapper.find("[data-cell='0-0']").trigger("click");
    await wrapper.find("[data-cell='0-1']").trigger("click");
    await flushPromises();
    expect(api.validateMove).toHaveBeenCalledTimes(1);
  });

  it("打开棋谱后棋盘只读且显示推演按钮", async () => {
    api.validateMove.mockResolvedValue({ legal: true, chinese: "车九进一", check: false });
    const wrapper = mount(MobileHomeView);
    await loadGame(wrapper, { id: 9, name: "局", initial_fen: INITIAL_FEN, moves: [] });
    expect(wrapper.find("[data-test='ctrl-infer']").exists()).toBe(true);
    await wrapper.find("[data-cell='0-9']").trigger("click");
    await wrapper.find("[data-cell='0-8']").trigger("click");
    await flushPromises();
    expect(api.validateMove).not.toHaveBeenCalled();
  });

  it("棋谱模式下点推演打开推演弹窗", async () => {
    const wrapper = mount(MobileHomeView);
    await loadGame(wrapper, { id: 10, name: "局", initial_fen: INITIAL_FEN, moves: [] });
    await wrapper.find("[data-test='ctrl-infer']").trigger("click");
    expect(wrapper.find("[data-test='infer-card']").exists()).toBe(true);
  });
});

const RECITE_GAME = {
  id: 1,
  name: "测试谱",
  initial_fen: INITIAL_FEN,
  moves: [
    { x1: 0, y1: 3, x2: 0, y2: 4 },
    { x1: 0, y1: 6, x2: 0, y2: 5 },
  ],
  red_player: "红方甲",
  black_player: "黑方乙",
  event: "测试赛",
  result: "红胜",
  category: "古谱 · 测试",
  favorited: false,
};

const ENGINE_GAME = {
  ...RECITE_GAME,
  moves: [
    { x1: 0, y1: 3, x2: 0, y2: 4 },
    { x1: 0, y1: 6, x2: 0, y2: 5 },
    { x1: 0, y1: 4, x2: 0, y2: 5 },
  ],
};

async function openGameWithSource(
  wrapper,
  game = RECITE_GAME,
  source = { type: "collection", collection: "测试" }
) {
  window.dispatchEvent(new CustomEvent("mobile-open"));
  await flushPromises();
  wrapper.findComponent(MobileGamePicker).vm.$emit("select", game, source);
  await flushPromises();
}

describe("MobileHomeView 背谱", () => {
  beforeEach(() => {
    localStorage.clear();
    api.checkMove.mockReset();
    api.submitReview.mockReset();
    api.submitReview.mockResolvedValue({});
    api.reviewQueue.mockReset();
    api.listGames.mockReset();
  });

  it("打开棋谱后显示背谱按钮，点击弹出确认条", async () => {
    const wrapper = mount(MobileHomeView);
    await openGameWithSource(wrapper);
    const recite = wrapper.find("[data-test='ctrl-recite']");
    expect(recite.exists()).toBe(true);
    await recite.trigger("click");
    expect(wrapper.find("[data-test='recite-confirm']").exists()).toBe(true);
    expect(wrapper.find("[data-test='recite-meta']").text()).toContain("红方甲");
    expect(wrapper.find("[data-test='recite-meta']").text()).toContain("测试赛");
  });

  it("取消确认条不进入背谱", async () => {
    const wrapper = mount(MobileHomeView);
    await openGameWithSource(wrapper);
    await wrapper.find("[data-test='ctrl-recite']").trigger("click");
    await wrapper.find("[data-test='recite-cancel']").trigger("click");
    expect(wrapper.find("[data-test='recite-confirm']").exists()).toBe(false);
    expect(wrapper.find("[data-test='ctrl-reveal']").exists()).toBe(false);
  });

  it("从头背进入背谱态，控制栏切换为背谱按钮组", async () => {
    const wrapper = mount(MobileHomeView);
    await openGameWithSource(wrapper);
    await wrapper.find("[data-test='ctrl-next']").trigger("click");
    await wrapper.find("[data-test='ctrl-recite']").trigger("click");
    await wrapper.find("[data-test='recite-from-start']").trigger("click");
    expect(wrapper.find("[data-test='ctrl-reveal']").exists()).toBe(true);
    expect(wrapper.find("[data-test='ctrl-exit-recite']").exists()).toBe(true);
    expect(wrapper.find("[data-test='ctrl-start']").exists()).toBe(false);
  });

  it("翻到终局后背谱按钮不显示", async () => {
    const wrapper = mount(MobileHomeView);
    await openGameWithSource(wrapper);
    await wrapper.find("[data-test='ctrl-end']").trigger("click");
    expect(wrapper.find("[data-test='ctrl-recite']").exists()).toBe(false);
  });

  it("进入背谱态清空残留分析箭头", async () => {
    const wrapper = mount(MobileHomeView);
    await openGameWithSource(wrapper);
    wrapper.vm.$.setupState.analysisArrows = [{ from: { x: 0, y: 0 }, to: { x: 0, y: 1 } }];
    await wrapper.find("[data-test='ctrl-recite']").trigger("click");
    await wrapper.find("[data-test='recite-from-here']").trigger("click");
    expect(wrapper.vm.$.setupState.analysisArrows).toEqual([]);
    expect(wrapper.findComponent(ChessBoard).props("arrows")).toEqual([]);
  });

  it("最近来源的有分类棋谱转换为棋谱集来源并显示导航", async () => {
    const wrapper = mount(MobileHomeView);
    await openGameWithSource(wrapper, RECITE_GAME, { type: "recent" });
    expect(wrapper.vm.$.setupState.navSource).toEqual({
      type: "collection",
      collection: "测试",
    });
    expect(wrapper.find("[data-test='ctrl-next-game']").exists()).toBe(true);
  });

  it("最近来源的有赛事棋谱转换为赛事来源并显示导航", async () => {
    const wrapper = mount(MobileHomeView);
    await openGameWithSource(wrapper, { ...RECITE_GAME, category: "", event: "联赛" }, { type: "recent" });
    expect(wrapper.vm.$.setupState.navSource).toEqual({ type: "event", event: "联赛" });
    expect(wrapper.find("[data-test='ctrl-next-game']").exists()).toBe(true);
  });

  it("最近来源的无分类棋谱不显示导航", async () => {
    const wrapper = mount(MobileHomeView);
    await openGameWithSource(
      wrapper,
      { ...RECITE_GAME, category: "", event: "" },
      { type: "recent" }
    );
    expect(wrapper.vm.$.setupState.navSource).toBe(null);
    expect(wrapper.find("[data-test='ctrl-next-game']").exists()).toBe(false);
  });

  it("背谱走对推进一步", async () => {
    api.checkMove.mockResolvedValue({ correct: true });
    const wrapper = mount(MobileHomeView);
    await openGameWithSource(wrapper);
    await wrapper.find("[data-test='ctrl-recite']").trigger("click");
    await wrapper.find("[data-test='recite-from-here']").trigger("click");
    const board = wrapper.findComponent(ChessBoard);
    board.vm.$emit("cell-click", 0, 3);
    board.vm.$emit("cell-click", 0, 4);
    await flushPromises();
    expect(api.checkMove).toHaveBeenCalledWith(1, {
      ply: 0,
      move: { x1: 0, y1: 3, x2: 0, y2: 4 },
    });
    expect(wrapper.vm.$.setupState.ply).toBe(1);
  });

  it("背谱走错不推进且提示错误", async () => {
    api.checkMove.mockResolvedValue({ correct: false });
    const wrapper = mount(MobileHomeView);
    await openGameWithSource(wrapper);
    await wrapper.find("[data-test='ctrl-recite']").trigger("click");
    await wrapper.find("[data-test='recite-from-here']").trigger("click");
    const board = wrapper.findComponent(ChessBoard);
    board.vm.$emit("cell-click", 0, 3);
    board.vm.$emit("cell-click", 0, 5);
    await flushPromises();
    expect(wrapper.find("[data-test='hint']").text()).toContain("错误");
    expect(wrapper.vm.$.setupState.ply).toBe(0);
    expect(wrapper.vm.$.setupState.reciteMistakes).toBe(1);
  });

  it("背谱走子网络失败提示且不计错", async () => {
    api.checkMove.mockRejectedValue({ response: { data: { error: "校验失败" } } });
    const wrapper = mount(MobileHomeView);
    await openGameWithSource(wrapper);
    await wrapper.find("[data-test='ctrl-recite']").trigger("click");
    await wrapper.find("[data-test='recite-from-here']").trigger("click");
    const board = wrapper.findComponent(ChessBoard);
    board.vm.$emit("cell-click", 0, 3);
    board.vm.$emit("cell-click", 0, 4);
    await flushPromises();
    expect(wrapper.find("[data-test='hint']").exists()).toBe(true);
    expect(wrapper.vm.$.setupState.ply).toBe(0);
    expect(wrapper.vm.$.setupState.reciteMistakes).toBe(0);
  });

  it("走完整条棋谱提交 SRS 且错误数为 0", async () => {
    api.checkMove.mockResolvedValue({ correct: true });
    const wrapper = mount(MobileHomeView);
    await openGameWithSource(wrapper);
    await wrapper.find("[data-test='ctrl-recite']").trigger("click");
    await wrapper.find("[data-test='recite-from-here']").trigger("click");
    const board = wrapper.findComponent(ChessBoard);
    board.vm.$emit("cell-click", 0, 3);
    board.vm.$emit("cell-click", 0, 4);
    await flushPromises();
    board.vm.$emit("cell-click", 0, 6);
    board.vm.$emit("cell-click", 0, 5);
    await flushPromises();
    expect(api.submitReview).toHaveBeenCalledWith(1, {
      mistake_count: 0,
      duration_ms: expect.any(Number),
      revealed: false,
    });
    expect(wrapper.vm.$.setupState.reciteMode).toBe(false);
  });

  it("看答案标记 revealed 并推进至完成", async () => {
    const wrapper = mount(MobileHomeView);
    await openGameWithSource(wrapper);
    await wrapper.find("[data-test='ctrl-recite']").trigger("click");
    await wrapper.find("[data-test='recite-from-here']").trigger("click");
    await wrapper.find("[data-test='ctrl-reveal']").trigger("click");
    await flushPromises();
    await wrapper.find("[data-test='ctrl-reveal']").trigger("click");
    await flushPromises();
    expect(api.submitReview).toHaveBeenCalledWith(1, {
      mistake_count: 0,
      duration_ms: expect.any(Number),
      revealed: true,
    });
  });

  it("中途退出背谱不提交 SRS", async () => {
    const wrapper = mount(MobileHomeView);
    await openGameWithSource(wrapper);
    await wrapper.find("[data-test='ctrl-recite']").trigger("click");
    await wrapper.find("[data-test='recite-from-here']").trigger("click");
    await wrapper.find("[data-test='ctrl-exit-recite']").trigger("click");
    expect(api.submitReview).not.toHaveBeenCalled();
    expect(wrapper.vm.$.setupState.reciteMode).toBe(false);
  });

  it("背谱态切换执子不会截断棋谱", async () => {
    const wrapper = mount(MobileHomeView);
    await openGameWithSource(wrapper);
    await wrapper.find("[data-test='ctrl-recite']").trigger("click");
    await wrapper.find("[data-test='recite-from-here']").trigger("click");
    const before = wrapper.vm.$.setupState.moves.length;
    window.dispatchEvent(new CustomEvent("mobile-settings"));
    await flushPromises();
    await wrapper.find("[data-test='engine-red']").setValue();
    expect(wrapper.vm.$.setupState.moves.length).toBe(before);
  });

  it("校验进行中时看答案不生效", async () => {
    let resolveCheck;
    api.checkMove.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveCheck = resolve;
        })
    );
    const wrapper = mount(MobileHomeView);
    await openGameWithSource(wrapper);
    await wrapper.find("[data-test='ctrl-recite']").trigger("click");
    await wrapper.find("[data-test='recite-from-here']").trigger("click");
    const board = wrapper.findComponent(ChessBoard);
    board.vm.$emit("cell-click", 0, 3);
    board.vm.$emit("cell-click", 0, 4);
    await Promise.resolve();
    await wrapper.find("[data-test='ctrl-reveal']").trigger("click");
    expect(wrapper.vm.$.setupState.ply).toBe(0);
    resolveCheck({ correct: true });
    await flushPromises();
    expect(wrapper.vm.$.setupState.ply).toBe(1);
  });

  it("下一盘切换到来源列表的下一条", async () => {
    api.listGames.mockResolvedValue({
      items: [RECITE_GAME, { ...RECITE_GAME, id: 2, name: "第二谱" }],
      total: 2,
    });
    const wrapper = mount(MobileHomeView);
    await openGameWithSource(wrapper);
    await wrapper.find("[data-test='ctrl-next-game']").trigger("click");
    await flushPromises();
    expect(api.listGames).toHaveBeenCalledWith(
      expect.objectContaining({ scope: "collection", collection: "测试", page: 1 })
    );
    expect(api.openGame).toHaveBeenLastCalledWith(2);
  });

  it("已是最后一盘时提示", async () => {
    api.listGames.mockResolvedValue({ items: [RECITE_GAME], total: 1 });
    const wrapper = mount(MobileHomeView);
    await openGameWithSource(wrapper);
    await wrapper.find("[data-test='ctrl-next-game']").trigger("click");
    await flushPromises();
    expect(wrapper.find("[data-test='hint']").text()).toContain("最后一盘");
  });

  it("背谱未完成时切换先弹确认，确认后不提交 SRS 并切换", async () => {
    api.listGames.mockResolvedValue({
      items: [RECITE_GAME, { ...RECITE_GAME, id: 2, name: "第二谱" }],
      total: 2,
    });
    const wrapper = mount(MobileHomeView);
    await openGameWithSource(wrapper);
    await wrapper.find("[data-test='ctrl-recite']").trigger("click");
    await wrapper.find("[data-test='recite-from-here']").trigger("click");
    await wrapper.find("[data-test='ctrl-next-game']").trigger("click");
    expect(wrapper.find("[data-test='nav-confirm']").exists()).toBe(true);
    await wrapper.find("[data-test='nav-confirm-ok']").trigger("click");
    await flushPromises();
    expect(api.submitReview).not.toHaveBeenCalled();
    expect(api.openGame).toHaveBeenLastCalledWith(2);
    expect(wrapper.vm.$.setupState.reciteMode).toBe(false);
  });

  it("复习来源的下一盘来自复习队列", async () => {
    api.reviewQueue.mockResolvedValue({
      items: [
        { game: RECITE_GAME, due_date: "2026-09-29", is_new: false },
        {
          game: { ...RECITE_GAME, id: 9, name: "复习第二盘" },
          due_date: "2026-09-29",
          is_new: true,
        },
      ],
      count: 2,
    });
    const wrapper = mount(MobileHomeView);
    await openGameWithSource(wrapper, RECITE_GAME, { type: "review" });
    await wrapper.find("[data-test='ctrl-next-game']").trigger("click");
    await flushPromises();
    expect(api.reviewQueue).toHaveBeenCalledWith({ limit: 200 });
    expect(api.openGame).toHaveBeenLastCalledWith(9);
  });

  it("来源列表跨页时请求后续页定位下一盘", async () => {
    const all = Array.from({ length: 250 }, (_, i) => ({ ...RECITE_GAME, id: i + 1 }));
    api.listGames.mockImplementation(({ page }) =>
      Promise.resolve({ items: all.slice((page - 1) * 100, page * 100), total: 250 })
    );
    const wrapper = mount(MobileHomeView);
    await openGameWithSource(wrapper, all[149]);
    await wrapper.find("[data-test='ctrl-next-game']").trigger("click");
    await flushPromises();
    expect(api.listGames).toHaveBeenCalledTimes(3);
    expect(api.openGame).toHaveBeenLastCalledWith(151);
  });

  it("快速连点下一盘只加载一次目标", async () => {
    api.listGames.mockResolvedValue({
      items: [
        RECITE_GAME,
        { ...RECITE_GAME, id: 2, name: "第二谱" },
        { ...RECITE_GAME, id: 3, name: "第三谱" },
      ],
      total: 3,
    });
    const wrapper = mount(MobileHomeView);
    await openGameWithSource(wrapper);
    const next = wrapper.find("[data-test='ctrl-next-game']");
    next.trigger("click");
    next.trigger("click");
    await flushPromises();
    expect(api.openGame).toHaveBeenCalledTimes(2);
    expect(api.openGame).toHaveBeenLastCalledWith(2);
  });

  it("导航在途时打开其他棋谱不被旧导航覆盖", async () => {
    const list = {
      items: [
        RECITE_GAME,
        { ...RECITE_GAME, id: 2, name: "第二谱" },
        { ...RECITE_GAME, id: 3, name: "第三谱" },
      ],
      total: 3,
    };
    api.listGames.mockResolvedValue(list);
    const wrapper = mount(MobileHomeView);
    await openGameWithSource(wrapper);
    let resolveNav;
    api.listGames.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveNav = resolve;
        })
    );
    wrapper.find("[data-test='ctrl-next-game']").trigger("click");
    await flushPromises();
    await openGameWithSource(wrapper, { ...RECITE_GAME, id: 3, name: "手动打开" });
    expect(wrapper.vm.$.setupState.currentGame.id).toBe(3);
    resolveNav(list);
    await flushPromises();
    expect(wrapper.vm.$.setupState.currentGame.id).toBe(3);
    expect(api.openGame).toHaveBeenLastCalledWith(3);
  });
});

describe("MobileHomeView 背谱引擎执子", () => {
  beforeEach(() => {
    localStorage.clear();
    api.checkMove.mockReset();
    api.checkMove.mockResolvedValue({ correct: true });
    api.submitReview.mockReset();
    api.submitReview.mockResolvedValue({});
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  async function enterRecite(wrapper) {
    await wrapper.find("[data-test='ctrl-recite']").trigger("click");
    await wrapper.find("[data-test='recite-from-here']").trigger("click");
  }

  it("确认条显示引擎执子提示", async () => {
    const wrapper = mount(MobileHomeView);
    await openGameWithSource(wrapper);
    wrapper.vm.$.setupState.engineSide = "red";
    await wrapper.find("[data-test='ctrl-recite']").trigger("click");
    expect(wrapper.find("[data-test='recite-engine-side']").text()).toBe("引擎执红 · 你背黑方");
    wrapper.vm.$.setupState.engineSide = "black";
    await nextTick();
    expect(wrapper.find("[data-test='recite-engine-side']").text()).toBe("引擎执黑 · 你背红方");
  });

  it("执子不启用时确认条不显示引擎提示", async () => {
    const wrapper = mount(MobileHomeView);
    await openGameWithSource(wrapper);
    await wrapper.find("[data-test='ctrl-recite']").trigger("click");
    expect(wrapper.find("[data-test='recite-engine-side']").exists()).toBe(false);
  });

  it("引擎执红时进入背谱自动走第一步且不计错", async () => {
    const wrapper = mount(MobileHomeView);
    await openGameWithSource(wrapper);
    wrapper.vm.$.setupState.engineSide = "red";
    await enterRecite(wrapper);
    expect(wrapper.vm.$.setupState.ply).toBe(0);
    vi.advanceTimersByTime(500);
    await nextTick();
    expect(wrapper.vm.$.setupState.ply).toBe(1);
    expect(wrapper.vm.$.setupState.reciteMistakes).toBe(0);
    expect(api.checkMove).not.toHaveBeenCalled();
    expect(wrapper.findComponent(ChessBoard).props("lastMove")).toMatchObject({ x2: 0, y2: 4 });
  });

  it("引擎执红时用户走对后引擎自动接走最后一步并提交 SRS", async () => {
    const wrapper = mount(MobileHomeView);
    await openGameWithSource(wrapper, ENGINE_GAME);
    wrapper.vm.$.setupState.engineSide = "red";
    await enterRecite(wrapper);
    vi.advanceTimersByTime(500);
    await nextTick();
    expect(wrapper.vm.$.setupState.ply).toBe(1);
    const board = wrapper.findComponent(ChessBoard);
    board.vm.$emit("cell-click", 0, 6);
    board.vm.$emit("cell-click", 0, 5);
    await flushPromises();
    expect(api.checkMove).toHaveBeenCalledWith(1, {
      ply: 1,
      move: { x1: 0, y1: 6, x2: 0, y2: 5 },
    });
    expect(wrapper.vm.$.setupState.ply).toBe(2);
    vi.advanceTimersByTime(500);
    await nextTick();
    expect(wrapper.vm.$.setupState.ply).toBe(3);
    expect(api.submitReview).toHaveBeenCalledWith(1, {
      mistake_count: 0,
      duration_ms: expect.any(Number),
      revealed: false,
    });
    expect(wrapper.vm.$.setupState.reciteMode).toBe(false);
  });

  it("引擎执黑时用户走完后引擎自动走完并提交 SRS", async () => {
    const wrapper = mount(MobileHomeView);
    await openGameWithSource(wrapper);
    wrapper.vm.$.setupState.engineSide = "black";
    await enterRecite(wrapper);
    const board = wrapper.findComponent(ChessBoard);
    board.vm.$emit("cell-click", 0, 3);
    board.vm.$emit("cell-click", 0, 4);
    await flushPromises();
    expect(wrapper.vm.$.setupState.ply).toBe(1);
    vi.advanceTimersByTime(500);
    await nextTick();
    expect(wrapper.vm.$.setupState.ply).toBe(2);
    expect(api.submitReview).toHaveBeenCalledWith(1, {
      mistake_count: 0,
      duration_ms: expect.any(Number),
      revealed: false,
    });
    expect(wrapper.vm.$.setupState.reciteMode).toBe(false);
  });

  it("引擎回合点看答案不生效，引擎随后自动落子", async () => {
    const wrapper = mount(MobileHomeView);
    await openGameWithSource(wrapper);
    wrapper.vm.$.setupState.engineSide = "red";
    await enterRecite(wrapper);
    await wrapper.find("[data-test='ctrl-reveal']").trigger("click");
    expect(wrapper.vm.$.setupState.ply).toBe(0);
    expect(wrapper.vm.$.setupState.reciteRevealed).toBe(false);
    vi.advanceTimersByTime(500);
    await nextTick();
    expect(wrapper.vm.$.setupState.ply).toBe(1);
  });

  it("引擎等待期间卸载组件不再自动落子", async () => {
    const wrapper = mount(MobileHomeView);
    await openGameWithSource(wrapper);
    wrapper.vm.$.setupState.engineSide = "black";
    await enterRecite(wrapper);
    const board = wrapper.findComponent(ChessBoard);
    board.vm.$emit("cell-click", 0, 3);
    board.vm.$emit("cell-click", 0, 4);
    await flushPromises();
    expect(wrapper.vm.$.setupState.ply).toBe(1);
    wrapper.unmount();
    vi.advanceTimersByTime(1000);
    expect(api.submitReview).not.toHaveBeenCalled();
  });

  it("引擎走子延迟期间退出背谱不再自动落子", async () => {
    const wrapper = mount(MobileHomeView);
    await openGameWithSource(wrapper);
    wrapper.vm.$.setupState.engineSide = "red";
    await enterRecite(wrapper);
    await wrapper.find("[data-test='ctrl-exit-recite']").trigger("click");
    vi.advanceTimersByTime(1000);
    await nextTick();
    expect(wrapper.vm.$.setupState.ply).toBe(0);
    expect(wrapper.vm.$.setupState.reciteMode).toBe(false);
  });

  it("引擎回合点击棋盘不选中也不走子", async () => {
    const wrapper = mount(MobileHomeView);
    await openGameWithSource(wrapper);
    wrapper.vm.$.setupState.engineSide = "red";
    await enterRecite(wrapper);
    const board = wrapper.findComponent(ChessBoard);
    board.vm.$emit("cell-click", 0, 3);
    board.vm.$emit("cell-click", 0, 4);
    expect(wrapper.vm.$.setupState.selected).toBe(null);
    expect(api.checkMove).not.toHaveBeenCalled();
  });

  it("引擎等待期退出后立即重进，引擎按新周期落子", async () => {
    const wrapper = mount(MobileHomeView);
    await openGameWithSource(wrapper);
    wrapper.vm.$.setupState.engineSide = "red";
    await enterRecite(wrapper);
    vi.advanceTimersByTime(200);
    await wrapper.find("[data-test='ctrl-exit-recite']").trigger("click");
    await enterRecite(wrapper);
    vi.advanceTimersByTime(300);
    expect(wrapper.vm.$.setupState.ply).toBe(0);
    vi.advanceTimersByTime(200);
    expect(wrapper.vm.$.setupState.ply).toBe(1);
  });

  it("用户回合看答案后引擎自动接走并提交 SRS", async () => {
    const wrapper = mount(MobileHomeView);
    await openGameWithSource(wrapper, ENGINE_GAME);
    wrapper.vm.$.setupState.engineSide = "red";
    await enterRecite(wrapper);
    vi.advanceTimersByTime(500);
    await nextTick();
    expect(wrapper.vm.$.setupState.ply).toBe(1);
    await wrapper.find("[data-test='ctrl-reveal']").trigger("click");
    expect(wrapper.vm.$.setupState.ply).toBe(2);
    expect(wrapper.vm.$.setupState.reciteRevealed).toBe(true);
    vi.advanceTimersByTime(500);
    await nextTick();
    expect(wrapper.vm.$.setupState.ply).toBe(3);
    expect(api.submitReview).toHaveBeenCalledWith(1, {
      mistake_count: 0,
      duration_ms: expect.any(Number),
      revealed: true,
    });
  });
});

describe("移动端路由", () => {
  it("/ 解析到移动端布局与首页", () => {
    const resolved = router.resolve("/");
    expect(resolved.matched).toHaveLength(2);
  });

  it("未知路径回落到 /", async () => {
    await router.push(`/unknown?t=${Date.now()}`);
    expect(router.currentRoute.value.path).toBe("/");
  });

  it("旧路径 /m 重定向到 /", async () => {
    await router.push(`/m?t=${Date.now()}`);
    expect(router.currentRoute.value.path).toBe("/");
  });
});

describe("App 渲染移动端 shell", () => {
  it("/ 下只渲染移动端 shell，不渲染旧 topbar/tabbar", async () => {
    await router.push(`/?t=${Date.now()}`);
    await router.isReady();
    const wrapper = mount(App, {
      global: { plugins: [createPinia(), router] },
    });
    await flushPromises();

    expect(wrapper.find(".mobile-topbar").exists()).toBe(true);
    expect(wrapper.find(".topbar").exists()).toBe(false);
    expect(wrapper.find(".tabbar").exists()).toBe(false);
  });
});
