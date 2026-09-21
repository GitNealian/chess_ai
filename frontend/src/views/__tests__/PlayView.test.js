import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { nextTick } from "vue";
import PlayView from "../PlayView.vue";
import { api } from "../../api";

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

describe("PlayView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
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
});
