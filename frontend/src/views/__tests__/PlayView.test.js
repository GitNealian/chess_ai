import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { nextTick } from "vue";
import PlayView from "../PlayView.vue";
import { analyzeStream, api } from "../../api";

const { route, push } = vi.hoisted(() => ({
  route: { query: {} },
  push: vi.fn(),
}));

vi.mock("../../api", () => ({
  api: {
    getGame: vi.fn(),
    validateMove: vi.fn(),
    createGame: vi.fn(),
  },
  analyzeStream: vi.fn(),
}));

vi.mock("vue-router", () => ({
  useRoute: () => route,
  useRouter: () => ({ push }),
}));

const INITIAL_FEN = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1";

const BoardStub = {
  name: "ChessBoard",
  props: ["position", "selected", "legalTargets", "arrows", "flipped"],
  emits: ["cell-click"],
  template: '<div class="board-stub" />',
};

function mountView() {
  return mount(PlayView, { global: { stubs: { ChessBoard: BoardStub } } });
}

function board(wrapper) {
  return wrapper.findComponent(BoardStub);
}

async function clickCells(wrapper, ...coords) {
  for (const [x, y] of coords) {
    board(wrapper).vm.$emit("cell-click", x, y);
    await nextTick();
  }
}

function button(wrapper, test) {
  return wrapper.find(`[data-test="${test}"]`);
}

let streams = [];

function emitResult(index, payload) {
  streams[index].handlers.onResult(payload);
}

function emitDone(index) {
  streams[index].handlers.onDone({});
}

describe("PlayView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    streams = [];
    analyzeStream.mockImplementation((payload, handlers = {}) => {
      streams.push({ payload, handlers });
      return Promise.resolve();
    });
    route.query = {};
    api.validateMove.mockResolvedValue({
      legal: true,
      fen: INITIAL_FEN,
      side_to_move: "black",
      chinese: "炮二平五",
      check: false,
      game_over: null,
    });
  });

  it("空白开局显示 32 子与红方走棋", async () => {
    const wrapper = mountView();
    await flushPromises();
    expect(board(wrapper).props("position").pieces).toHaveLength(32);
    expect(wrapper.find('[data-test="turn"]').text()).toContain("红方走棋");
  });

  it("选中棋子传给棋盘，合法走子后更新轮次与着法列表", async () => {
    const wrapper = mountView();
    await flushPromises();

    await clickCells(wrapper, [1, 2]);
    expect(board(wrapper).props("selected")).toEqual({ x: 1, y: 2 });

    await clickCells(wrapper, [4, 2]);
    await flushPromises();

    expect(api.validateMove).toHaveBeenCalledWith({
      initial_fen: INITIAL_FEN,
      moves: [],
      move: { x1: 1, y1: 2, x2: 4, y2: 2 },
    });
    expect(wrapper.find('[data-test="turn"]').text()).toContain("黑方走棋");
    expect(wrapper.find('[data-test="move-list"]').text()).toContain("1. 炮二平五");
  });

  it("非法着法显示提示且不改变局面", async () => {
    api.validateMove.mockResolvedValue({ legal: false, reason: "该棋子不能这样走" });
    const wrapper = mountView();
    await flushPromises();

    await clickCells(wrapper, [1, 2], [1, 3]);
    await flushPromises();

    expect(wrapper.find('[data-test="hint"]').text()).toBe("该棋子不能这样走");
    expect(wrapper.find('[data-test="turn"]').text()).toContain("红方走棋");
  });

  it("悔棋回退一步", async () => {
    const wrapper = mountView();
    await flushPromises();
    await clickCells(wrapper, [1, 2], [4, 2]);
    await flushPromises();
    expect(button(wrapper, "undo").attributes("disabled")).toBeUndefined();

    await button(wrapper, "undo").trigger("click");
    await flushPromises();
    expect(wrapper.find('[data-test="turn"]').text()).toContain("红方走棋");
    expect(wrapper.find('[data-test="move-list"]').exists()).toBe(false);
  });

  it("翻转按钮切换 flipped", async () => {
    const wrapper = mountView();
    await flushPromises();
    expect(board(wrapper).props("flipped")).toBe(false);
    await button(wrapper, "flip").trigger("click");
    expect(board(wrapper).props("flipped")).toBe(true);
  });

  it("终局显示结果并锁定棋盘", async () => {
    api.validateMove.mockResolvedValue({
      legal: true,
      fen: INITIAL_FEN,
      side_to_move: "black",
      chinese: "车二进九",
      check: true,
      game_over: { winner: "red", reason: "checkmate" },
    });
    const wrapper = mountView();
    await flushPromises();
    await clickCells(wrapper, [1, 2], [4, 2]);
    await flushPromises();

    expect(wrapper.find('[data-test="game-over"]').text()).toContain("红方胜");
    await clickCells(wrapper, [1, 9]);
    expect(api.validateMove).toHaveBeenCalledTimes(1);
  });

  it("从棋谱终局步载入时显示结果并锁定棋盘", async () => {
    route.query = { game: "7", ply: "2" };
    api.getGame.mockResolvedValue({
      id: 7,
      name: "终局棋谱",
      initial_fen: INITIAL_FEN,
      moves: [
        { x1: 1, y1: 2, x2: 4, y2: 2 },
        { x1: 7, y1: 9, x2: 6, y2: 7 },
      ],
    });
    api.validateMove.mockResolvedValue({
      legal: true,
      fen: INITIAL_FEN,
      side_to_move: "red",
      chinese: "马8进7",
      check: true,
      game_over: { winner: "red", reason: "checkmate" },
    });
    const wrapper = mountView();
    await flushPromises();

    expect(api.validateMove).toHaveBeenCalledWith({
      initial_fen: INITIAL_FEN,
      moves: [{ x1: 1, y1: 2, x2: 4, y2: 2 }],
      move: { x1: 7, y1: 9, x2: 6, y2: 7 },
    });
    expect(wrapper.find('[data-test="game-over"]').text()).toContain("红方胜");
    await clickCells(wrapper, [0, 0]);
    expect(api.validateMove).toHaveBeenCalledTimes(1);
  });

  it("加载失败显示错误并可重试", async () => {
    route.query = { game: "7" };
    api.getGame.mockRejectedValueOnce(new Error("boom"));
    const wrapper = mountView();
    await flushPromises();

    expect(wrapper.text()).toContain("加载失败");
    expect(board(wrapper).exists()).toBe(false);

    api.getGame.mockResolvedValue({
      id: 7,
      name: "恢复",
      initial_fen: INITIAL_FEN,
      moves: [],
    });
    await button(wrapper, "retry").trigger("click");
    await flushPromises();
    expect(board(wrapper).exists()).toBe(true);
    expect(wrapper.find('[data-test="move-list"]').exists()).toBe(false);
    expect(wrapper.find('[data-test="turn"]').text()).toContain("红方走棋");
  });

  it("初始悔棋按钮禁用", async () => {
    const wrapper = mountView();
    await flushPromises();
    expect(button(wrapper, "undo").attributes("disabled")).toBeDefined();
  });

  it("ply 非数字或超界时安全截断", async () => {
    const moves = [
      { x1: 1, y1: 2, x2: 4, y2: 2 },
      { x1: 7, y1: 9, x2: 6, y2: 7 },
      { x1: 0, y1: 9, x2: 0, y2: 8 },
    ];
    route.query = { game: "7", ply: "abc" };
    api.getGame.mockResolvedValue({ id: 7, name: "x", initial_fen: INITIAL_FEN, moves });
    const first = mountView();
    await flushPromises();
    expect(first.findAll('[data-test="move-list"] li')).toHaveLength(0);

    route.query = { game: "7", ply: "99" };
    const second = mountView();
    await flushPromises();
    expect(second.findAll('[data-test="move-list"] li')).toHaveLength(3);
  });

  it("URL 带 game/ply 时载入棋谱前 N 步", async () => {
    route.query = { game: "7", ply: "2" };
    api.getGame.mockResolvedValue({
      id: 7,
      name: "库内棋谱",
      initial_fen: INITIAL_FEN,
      moves: [
        { x1: 1, y1: 2, x2: 4, y2: 2 },
        { x1: 7, y1: 9, x2: 6, y2: 7 },
        { x1: 0, y1: 9, x2: 0, y2: 8 },
      ],
    });
    const wrapper = mountView();
    await flushPromises();
    expect(api.getGame).toHaveBeenCalledWith("7");
    expect(wrapper.find('[data-test="turn"]').text()).toContain("红方走棋");
    expect(wrapper.findAll('[data-test="move-list"] li')).toHaveLength(2);
  });

  it("进入页面自动分析当前局面", async () => {
    const wrapper = mountView();
    await flushPromises();

    expect(analyzeStream).toHaveBeenCalledTimes(1);
    expect(streams[0].payload.initial_fen).toBe(INITIAL_FEN);
    expect(streams[0].payload.moves).toEqual([]);
  });

  it("走子后重新分析并展示分数与箭头", async () => {
    const wrapper = mountView();
    await flushPromises();
    await clickCells(wrapper, [1, 2], [4, 2]);
    await flushPromises();

    expect(analyzeStream).toHaveBeenCalledTimes(2);
    expect(streams[1].payload.moves).toEqual([{ x1: 1, y1: 2, x2: 4, y2: 2 }]);

    emitResult(1, {
      depth: 8,
      score_red: 135,
      mate: null,
      time_ms: 100,
      pv: [
        { x1: 3, y1: 0, x2: 4, y2: 2, chinese: "炮二平五", iccs: "c0e2" },
        { x1: 1, y1: 9, x2: 2, y2: 7, chinese: "马8进7", iccs: "b9c7" },
      ],
    });
    await nextTick();

    expect(wrapper.find('[data-test="score"]').text()).toContain("+135");
    const arrows = board(wrapper).props("arrows");
    expect(arrows).toHaveLength(2);
    expect(arrows[0]).toMatchObject({ kind: "best" });
    expect(arrows[1]).toMatchObject({ kind: "reply" });
  });

  it("悔棋后重新分析", async () => {
    const wrapper = mountView();
    await flushPromises();
    await clickCells(wrapper, [1, 2], [4, 2]);
    await flushPromises();

    await button(wrapper, "undo").trigger("click");
    await flushPromises();
    expect(analyzeStream).toHaveBeenCalledTimes(3);
    expect(streams[2].payload.moves).toEqual([]);
  });

  it("分析完成时显示已完成", async () => {
    const wrapper = mountView();
    await flushPromises();
    emitDone(0);
    await nextTick();
    expect(wrapper.find('[data-test="analysis-status"]').text()).toContain("已完成");
  });

  it("走子后旧分析流被中止且迟到结果不污染", async () => {
    const wrapper = mountView();
    await flushPromises();
    await clickCells(wrapper, [1, 2], [4, 2]);
    await flushPromises();

    expect(streams[0].handlers.signal.aborted).toBe(true);

    emitResult(0, { depth: 8, score_red: 999, mate: null, time_ms: 10, pv: [] });
    emitDone(0);
    await nextTick();

    expect(wrapper.find('[data-test="score"]').text()).not.toContain("+999");
    expect(wrapper.findAll('[data-test="analysis-item"]')).toHaveLength(0);
    expect(wrapper.find('[data-test="analysis-status"]').text()).toContain("分析中");
  });

  it("组件卸载时中止进行中的分析", async () => {
    const wrapper = mountView();
    await flushPromises();
    wrapper.unmount();
    expect(streams[0].handlers.signal.aborted).toBe(true);
  });

  it("分析失败时显示失败原因", async () => {
    const wrapper = mountView();
    await flushPromises();
    streams[0].handlers.onError(new Error("引擎不可用"));
    await nextTick();
    expect(wrapper.find('[data-test="analysis-status"]').text()).toContain("分析失败");
    expect(wrapper.find('[data-test="analysis-status"]').text()).toContain("引擎不可用");
  });

  it("getGame 未返回时卸载，resolve 后不再发起分析", async () => {
    route.query = { game: "7" };
    let resolveGame;
    api.getGame.mockReturnValue(new Promise((r) => { resolveGame = r; }));
    const wrapper = mountView();
    wrapper.unmount();
    resolveGame({ id: 7, name: "x", initial_fen: INITIAL_FEN, moves: [] });
    await flushPromises();
    expect(analyzeStream).not.toHaveBeenCalled();
  });

  it("getGame 未返回时卸载，resolve 后不发起 probe 与分析", async () => {
    route.query = { game: "7", ply: "1" };
    let resolveGame;
    api.getGame.mockReturnValue(new Promise((r) => { resolveGame = r; }));
    const wrapper = mountView();
    wrapper.unmount();
    resolveGame({
      id: 7,
      name: "x",
      initial_fen: INITIAL_FEN,
      moves: [{ x1: 1, y1: 2, x2: 4, y2: 2 }],
    });
    await flushPromises();
    expect(api.validateMove).not.toHaveBeenCalled();
    expect(analyzeStream).not.toHaveBeenCalled();
  });

  it("probe 进行中卸载，resolve 后不再发起分析", async () => {
    route.query = { game: "7", ply: "1" };
    api.getGame.mockResolvedValue({
      id: 7, name: "终局棋谱", initial_fen: INITIAL_FEN,
      moves: [{ x1: 1, y1: 2, x2: 4, y2: 2 }],
    });
    let resolveProbe;
    api.validateMove.mockReturnValue(new Promise((r) => { resolveProbe = r; }));
    const wrapper = mountView();
    await flushPromises();
    expect(api.validateMove).toHaveBeenCalledTimes(1);
    wrapper.unmount();
    resolveProbe({ legal: true, check: false, game_over: null });
    await flushPromises();
    expect(analyzeStream).not.toHaveBeenCalled();
  });
});
