import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { nextTick } from "vue";
import PracticeView from "../PracticeView.vue";
import { api } from "../../api";

const { route } = vi.hoisted(() => ({ route: { params: { id: "1" } } }));

vi.mock("../../api", () => ({
  api: {
    getGame: vi.fn(),
  },
}));

vi.mock("vue-router", () => ({
  useRoute: () => route,
}));

const INITIAL_FEN = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1";

const BoardStub = {
  name: "ChessBoard",
  props: ["position", "selected", "legalTargets"],
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

describe("PracticeView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    route.params = { id: "1" };
    api.getGame.mockResolvedValue({
      id: 1,
      name: "测试棋谱",
      initial_fen: INITIAL_FEN,
      moves,
    });
  });

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
});
