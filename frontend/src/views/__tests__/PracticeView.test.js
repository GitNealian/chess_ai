import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { nextTick } from "vue";
import PracticeView from "../PracticeView.vue";
import { analyzeStream, api } from "../../api";

const { route, push } = vi.hoisted(() => ({
  route: { params: { id: "1" } },
  push: vi.fn(),
}));

vi.mock("../../api", () => ({
  api: {
    getGame: vi.fn(),
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
  props: ["position", "selected", "legalTargets", "arrows"],
  emits: ["cell-click"],
  template: '<div class="board-stub" />',
};

function mountView() {
  return mount(PracticeView, {
    global: { stubs: { ChessBoard: BoardStub } },
  });
}

function boardPieces(wrapper) {
  return wrapper.findComponent(BoardStub).props("position").pieces;
}

function button(wrapper, test) {
  return wrapper.find(`[data-test="${test}"]`);
}

const moves = [
  { x1: 0, y1: 9, x2: 0, y2: 6 },
  { x1: 1, y1: 0, x2: 2, y2: 2 },
  { x1: 0, y1: 6, x2: 0, y2: 5 },
  { x1: 8, y1: 0, x2: 8, y2: 1 },
];

let streams = [];

function emitResult(index, payload) {
  streams[index].handlers.onResult(payload);
}

function emitDone(index, payload = {}) {
  streams[index].handlers.onDone(payload);
}

function emitError(index, error) {
  streams[index].handlers.onError(error);
}

function analysisItems(wrapper) {
  return wrapper.findAll('[data-test="analysis-item"]');
}

beforeEach(() => {
  vi.clearAllMocks();
  push.mockClear();
  route.params = { id: "1" };
  streams = [];
  analyzeStream.mockImplementation((payload, handlers = {}) => {
    streams.push({ payload, handlers });
    return Promise.resolve();
  });
  api.getGame.mockResolvedValue({
    id: 1,
    name: "测试棋谱",
    initial_fen: INITIAL_FEN,
    moves,
  });
});

describe("PracticeView", () => {
  it("加载后显示棋谱名与总步数", async () => {
    const wrapper = mountView();
    await flushPromises();

    expect(api.getGame).toHaveBeenCalledWith("1");
    expect(wrapper.text()).toContain("测试棋谱");
    expect(wrapper.find(".ply-info").text()).toContain("当前第 0 / 4 步");
    expect(wrapper.findAll(".moves li")).toHaveLength(4);
    expect(wrapper.find(".moves").text()).toContain("1. (0,9)→(0,6)");
  });

  it("初始 ply=0，棋盘为初始局面 32 子", async () => {
    const wrapper = mountView();
    await flushPromises();

    expect(boardPieces(wrapper)).toHaveLength(32);
    expect(wrapper.find(".ply-info").text()).toContain("当前第 0 / 4 步");
    expect(wrapper.find(".moves .active").exists()).toBe(false);
  });

  it("点击「下一步」后 ply 增加、高亮与棋盘同步", async () => {
    const wrapper = mountView();
    await flushPromises();

    await button(wrapper, "next").trigger("click");
    await nextTick();

    expect(wrapper.find(".ply-info").text()).toContain("当前第 1 / 4 步");
    expect(wrapper.find(".moves .active").text()).toContain("1. (0,9)→(0,6)");
    expect(boardPieces(wrapper)).toHaveLength(31);
    expect(boardPieces(wrapper).some((p) => p.x === 0 && p.y === 6)).toBe(true);
  });

  it("点击 >| 到末尾，|< 回到 0", async () => {
    const wrapper = mountView();
    await flushPromises();

    await button(wrapper, "last").trigger("click");
    await nextTick();
    expect(wrapper.find(".ply-info").text()).toContain("当前第 4 / 4 步");
    expect(wrapper.find(".moves .active").text()).toContain("4.");

    await button(wrapper, "first").trigger("click");
    await nextTick();
    expect(wrapper.find(".ply-info").text()).toContain("当前第 0 / 4 步");
    expect(boardPieces(wrapper)).toHaveLength(32);
  });

  it("点击着法列表第 3 项跳到 ply=3", async () => {
    const wrapper = mountView();
    await flushPromises();

    await wrapper.findAll(".moves li")[2].trigger("click");
    await nextTick();

    expect(wrapper.find(".ply-info").text()).toContain("当前第 3 / 4 步");
    expect(wrapper.find(".moves .active").text()).toContain("3. (0,6)→(0,5)");
  });

  it("ply 不越界：0 时上一步仍为 0，末尾时下一步不超出", async () => {
    const wrapper = mountView();
    await flushPromises();

    await button(wrapper, "prev").trigger("click");
    await nextTick();
    expect(wrapper.find(".ply-info").text()).toContain("当前第 0 / 4 步");

    await button(wrapper, "last").trigger("click");
    await nextTick();
    await button(wrapper, "next").trigger("click");
    await nextTick();
    expect(wrapper.find(".ply-info").text()).toContain("当前第 4 / 4 步");
  });

  it("加载失败时显示错误提示与重试按钮", async () => {
    api.getGame.mockRejectedValueOnce(new Error("boom"));
    const wrapper = mountView();
    await flushPromises();

    expect(wrapper.text()).toContain("加载失败");
    expect(wrapper.find('[data-test="retry"]').exists()).toBe(true);
    expect(wrapper.find(".moves").exists()).toBe(false);
  });

  it("点击重试重新调用 getGame，成功后显示棋谱名", async () => {
    api.getGame.mockRejectedValueOnce(new Error("boom"));
    const wrapper = mountView();
    await flushPromises();
    expect(wrapper.text()).toContain("加载失败");

    api.getGame.mockResolvedValueOnce({
      id: 1,
      name: "重试成功棋谱",
      initial_fen: INITIAL_FEN,
      moves,
    });
    await wrapper.find('[data-test="retry"]').trigger("click");
    await flushPromises();

    expect(api.getGame).toHaveBeenCalledTimes(2);
    expect(wrapper.text()).toContain("重试成功棋谱");
    expect(wrapper.find('[data-test="retry"]').exists()).toBe(false);
  });

  it("点击从此处开始对弈跳转 /play 携带 game 与 ply", async () => {
    const wrapper = mountView();
    await flushPromises();

    await button(wrapper, "next").trigger("click");
    await nextTick();
    await button(wrapper, "start-play").trigger("click");

    expect(push).toHaveBeenCalledWith({ path: "/play", query: { game: 1, ply: 1 } });
  });
});

describe("PracticeView AI 分析", () => {
  it("首屏加载完成后自动分析当前局面", async () => {
    api.getGame.mockResolvedValueOnce({
      id: 1,
      name: "两步棋谱",
      initial_fen: INITIAL_FEN,
      moves: moves.slice(0, 2),
    });
    const wrapper = mountView();
    await flushPromises();

    expect(analyzeStream).toHaveBeenCalledTimes(1);
    expect(streams[0].payload).toEqual({
      initial_fen: INITIAL_FEN,
      moves: moves.slice(0, 2),
      ply: 0,
    });
    expect(wrapper.find('[data-test="analysis-status"]').text()).toContain("分析中");
  });

  it("结果渐进展示，最新一层在最上方", async () => {
    const wrapper = mountView();
    await flushPromises();

    emitResult(0, {
      depth: 6,
      score_red: 120,
      mate: null,
      pv: [{ x1: 7, y1: 2, x2: 4, y2: 2, chinese: "炮二平五" }],
      time_ms: 50,
    });
    await nextTick();

    expect(wrapper.find('[data-test="score"]').text()).toContain("红优");
    expect(analysisItems(wrapper)).toHaveLength(1);
    expect(analysisItems(wrapper)[0].text()).toContain("第 6 层");
    expect(analysisItems(wrapper)[0].text()).toContain("炮二平五");
    expect(analysisItems(wrapper)[0].text()).toContain("50ms");

    emitResult(0, {
      depth: 7,
      score_red: 135,
      mate: null,
      pv: [{ x1: 7, y1: 2, x2: 4, y2: 2, chinese: "炮二平五" }],
      time_ms: 80,
    });
    await nextTick();

    expect(analysisItems(wrapper)).toHaveLength(2);
    expect(analysisItems(wrapper)[0].text()).toContain("第 7 层");
    expect(analysisItems(wrapper)[1].text()).toContain("第 6 层");
    expect(wrapper.find('[data-test="score"]').text()).toContain("+135");
  });

  it("翻步立即重新分析并中止旧请求", async () => {
    const wrapper = mountView();
    await flushPromises();

    expect(streams).toHaveLength(1);
    expect(streams[0].handlers.signal.aborted).toBe(false);

    await button(wrapper, "next").trigger("click");
    await nextTick();

    expect(streams).toHaveLength(2);
    expect(streams[0].handlers.signal.aborted).toBe(true);
    expect(streams[1].payload.ply).toBe(1);
    expect(streams[1].handlers.signal.aborted).toBe(false);
  });

  it("旧分析的迟到结果不会污染新分析", async () => {
    const wrapper = mountView();
    await flushPromises();

    await button(wrapper, "next").trigger("click");
    await nextTick();

    emitResult(0, {
      depth: 8,
      score_red: 320,
      mate: null,
      pv: [{ x1: 7, y1: 2, x2: 4, y2: 2, chinese: "炮二平五" }],
      time_ms: 5,
    });
    emitDone(0);
    await nextTick();

    expect(wrapper.find('[data-test="score"]').text()).not.toContain("红优");
    expect(analysisItems(wrapper)).toHaveLength(0);
    expect(wrapper.find('[data-test="analysis-status"]').text()).toContain("分析中");

    emitResult(1, { depth: 4, score_red: 30, mate: null, pv: [], time_ms: 9 });
    await nextTick();
    expect(analysisItems(wrapper)).toHaveLength(1);
    expect(analysisItems(wrapper)[0].text()).toContain("第 4 层");
  });

  it("黑优显示绝对值且不带负号", async () => {
    const wrapper = mountView();
    await flushPromises();

    emitResult(0, { depth: 6, score_red: -85, mate: null, pv: [], time_ms: 12 });
    await nextTick();

    const text = wrapper.find('[data-test="score"]').text();
    expect(text).toContain("黑优 85");
    expect(text).not.toContain("-");
  });

  it("分数接近 0 时显示均势", async () => {
    const wrapper = mountView();
    await flushPromises();

    emitResult(0, { depth: 6, score_red: 0, mate: null, pv: [], time_ms: 12 });
    await nextTick();

    expect(wrapper.find('[data-test="score"]').text()).toContain("均势");
  });

  it("mate 非空时按优势方显示杀棋步数", async () => {
    const wrapper = mountView();
    await flushPromises();

    emitResult(0, { depth: 6, score_red: 31000, mate: 1, pv: [], time_ms: 12 });
    await nextTick();
    expect(wrapper.find('[data-test="score"]').text()).toContain("红方 1 步杀");

    emitResult(0, { depth: 7, score_red: -31000, mate: 2, pv: [], time_ms: 15 });
    await nextTick();
    expect(wrapper.find('[data-test="score"]').text()).toContain("黑方 2 步杀");
  });

  it("最佳着法与对方应着作为箭头传给棋盘", async () => {
    const wrapper = mountView();
    await flushPromises();

    emitResult(0, {
      depth: 6,
      score_red: 40,
      mate: null,
      pv: [
        { x1: 7, y1: 2, x2: 4, y2: 2, iccs: "h2e2", chinese: "炮二平五" },
        { x1: 1, y1: 7, x2: 4, y2: 7, iccs: "b7e7", chinese: "炮八平五" },
      ],
      time_ms: 20,
    });
    await nextTick();

    const arrows = wrapper.findComponent(BoardStub).props("arrows");
    expect(arrows).toHaveLength(2);
    expect(arrows[0]).toMatchObject({ x1: 7, y1: 2, x2: 4, y2: 2, kind: "best" });
    expect(arrows[1]).toMatchObject({ x1: 1, y1: 7, x2: 4, y2: 7, kind: "reply" });
  });

  it("分析失败时显示失败原因", async () => {
    const wrapper = mountView();
    await flushPromises();

    emitError(0, new Error("引擎不可用"));
    await nextTick();

    const status = wrapper.find('[data-test="analysis-status"]').text();
    expect(status).toContain("分析失败");
    expect(status).toContain("引擎不可用");
  });

  it("分析完成时显示已完成", async () => {
    const wrapper = mountView();
    await flushPromises();

    emitResult(0, { depth: 6, score_red: 10, mate: null, pv: [], time_ms: 30 });
    emitDone(0, { depth: 6, reason: "max_depth" });
    await nextTick();

    expect(wrapper.find('[data-test="analysis-status"]').text()).toContain("已完成");
  });

  it("组件卸载时中止进行中的分析", async () => {
    const wrapper = mountView();
    await flushPromises();

    expect(streams[0].handlers.signal.aborted).toBe(false);
    wrapper.unmount();
    expect(streams[0].handlers.signal.aborted).toBe(true);
  });

  it("加载失败时不发起分析", async () => {
    api.getGame.mockRejectedValueOnce(new Error("boom"));
    mountView();
    await flushPromises();

    expect(analyzeStream).not.toHaveBeenCalled();
  });

  it("重试成功后对当前局面发起分析", async () => {
    api.getGame.mockRejectedValueOnce(new Error("boom"));
    const wrapper = mountView();
    await flushPromises();
    expect(analyzeStream).not.toHaveBeenCalled();

    api.getGame.mockResolvedValueOnce({
      id: 1,
      name: "重试棋谱",
      initial_fen: INITIAL_FEN,
      moves: moves.slice(0, 2),
    });
    await button(wrapper, "retry").trigger("click");
    await flushPromises();

    expect(analyzeStream).toHaveBeenCalledTimes(1);
    expect(streams[0].payload).toEqual({
      initial_fen: INITIAL_FEN,
      moves: moves.slice(0, 2),
      ply: 0,
    });
  });
});
