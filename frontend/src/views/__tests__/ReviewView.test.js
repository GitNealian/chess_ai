import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { nextTick } from "vue";
import ReviewView from "../ReviewView.vue";
import { api } from "../../api";

vi.mock("../../api", () => ({
  api: {
    reviewQueue: vi.fn(),
    submitReview: vi.fn(),
  },
}));

const BoardStub = {
  name: "ChessBoard",
  props: ["position", "selected", "legalTargets"],
  emits: ["cell-click"],
  template: '<div class="board-stub" />',
};

const INITIAL_FEN = "4k4/9/9/9/9/9/9/9/9/4K4 w - - 0 1";

function item(overrides = {}) {
  return {
    due_date: "2026-01-01",
    is_new: false,
    game: {
      id: 1,
      name: "测试默写棋谱",
      initial_fen: INITIAL_FEN,
      practice_side: "both",
      moves: [{ x1: 4, y1: 0, x2: 4, y2: 1 }],
      ...overrides,
    },
  };
}

function mountView() {
  return mount(ReviewView, {
    global: { stubs: { ChessBoard: BoardStub } },
  });
}

async function clickCells(board, ...coords) {
  for (const [x, y] of coords) {
    board.vm.$emit("cell-click", x, y);
    await nextTick();
  }
}

describe("ReviewView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.reviewQueue.mockResolvedValue({ items: [item()], count: 1 });
    api.submitReview.mockResolvedValue({ quality: 1, review: {} });
  });

  it("队列为空时显示完成文案", async () => {
    api.reviewQueue.mockResolvedValue({ items: [], count: 0 });
    const wrapper = mountView();
    await flushPromises();

    expect(wrapper.find('[data-test="empty"]').exists()).toBe(true);
    expect(wrapper.text()).toContain("今日复习已全部完成");
  });

  it("队列有棋谱时显示棋谱名与进度", async () => {
    const wrapper = mountView();
    await flushPromises();

    expect(wrapper.text()).toContain("测试默写棋谱");
    expect(wrapper.find('[data-test="progress"]').text()).toContain("1 / 1");
  });

  it("走对着法后进入完成态，且棋盘同步移动", async () => {
    const wrapper = mountView();
    await flushPromises();

    await clickCells(wrapper.findComponent(BoardStub), [4, 0], [4, 1]);
    await nextTick();

    expect(wrapper.find('[data-test="done"]').text()).toContain("完成！共错 0 次");

    const board = wrapper.findComponent(BoardStub);
    const pieces = board.props("position").pieces;
    expect(pieces.some((p) => p.x === 4 && p.y === 1 && p.side === "red")).toBe(true);
    expect(pieces.some((p) => p.x === 4 && p.y === 0)).toBe(false);
  });

  it("practice_side=black 时自动跳过红方并提示黑方着法", async () => {
    api.reviewQueue.mockResolvedValue({
      items: [
        item({
          practice_side: "black",
          moves: [
            { x1: 4, y1: 0, x2: 4, y2: 1 },
            { x1: 4, y1: 9, x2: 4, y2: 8 },
          ],
        }),
      ],
      count: 1,
    });
    const wrapper = mountView();
    await flushPromises();

    expect(wrapper.find('[data-test="prompt"]').text()).toContain("黑方");
    await clickCells(wrapper.findComponent(BoardStub), [4, 9], [4, 8]);
    await nextTick();
    expect(wrapper.find('[data-test="done"]').text()).toContain("完成！共错 0 次");
  });

  it("走错后错误计数增加且不前进", async () => {
    const wrapper = mountView();
    await flushPromises();

    await clickCells(wrapper.findComponent(BoardStub), [4, 0], [3, 0]);
    await nextTick();

    expect(wrapper.text()).toContain("错误 1 次");
    expect(wrapper.find('[data-test="done"]').exists()).toBe(false);
  });

  it("点看答案后显示已看答案", async () => {
    api.reviewQueue.mockResolvedValue({
      items: [
        item({
          moves: [
            { x1: 4, y1: 0, x2: 4, y2: 1 },
            { x1: 4, y1: 9, x2: 4, y2: 8 },
          ],
        }),
      ],
      count: 1,
    });
    const wrapper = mountView();
    await flushPromises();

    await wrapper.find('[data-test="reveal"]').trigger("click");
    await nextTick();

    expect(wrapper.find('[data-test="revealed-hint"]').exists()).toBe(true);
    expect(wrapper.text()).toContain("已看答案");
  });

  it("提交调用 submitReview 且参数含 mistake_count", async () => {
    const wrapper = mountView();
    await flushPromises();
    const board = wrapper.findComponent(BoardStub);

    await clickCells(board, [4, 0], [3, 0]);
    await clickCells(board, [4, 0], [4, 1]);
    await nextTick();

    await wrapper.find('[data-test="submit"]').trigger("click");
    await flushPromises();

    expect(api.submitReview).toHaveBeenCalledWith(
      1,
      expect.objectContaining({ mistake_count: 1, revealed: false })
    );
  });

  it("计时器随时间递增显示用时", async () => {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
    try {
      const wrapper = mountView();
      await flushPromises();
      expect(wrapper.text()).toContain("用时 0 秒");

      vi.advanceTimersByTime(3000);
      await nextTick();
      expect(wrapper.text()).toContain("用时 3 秒");

      vi.advanceTimersByTime(2000);
      await nextTick();
      expect(wrapper.text()).toContain("用时 5 秒");
      wrapper.unmount();
    } finally {
      vi.useRealTimers();
    }
  });

  it("卸载后清除计时器且不再累加用时", async () => {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
    const clearSpy = vi.spyOn(globalThis, "clearInterval");
    try {
      const wrapper = mountView();
      await flushPromises();
      vi.advanceTimersByTime(2000);
      await nextTick();
      expect(wrapper.text()).toContain("用时 2 秒");

      wrapper.unmount();
      expect(clearSpy).toHaveBeenCalled();
      expect(vi.getTimerCount()).toBe(0);

      vi.advanceTimersByTime(5000);
      expect(vi.getTimerCount()).toBe(0);
    } finally {
      clearSpy.mockRestore();
      vi.useRealTimers();
    }
  });

  it("第一题提交后进入第二题并重置错误与用时", async () => {
    api.reviewQueue.mockResolvedValue({
      items: [item({ id: 1, name: "第一题" }), item({ id: 2, name: "第二题" })],
      count: 2,
    });
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
    try {
      const wrapper = mountView();
      await flushPromises();
      expect(wrapper.text()).toContain("第一题");
      expect(wrapper.find('[data-test="progress"]').text()).toContain("1 / 2");

      const board = wrapper.findComponent(BoardStub);
      vi.advanceTimersByTime(4000);
      await nextTick();
      expect(wrapper.text()).toContain("用时 4 秒");

      await clickCells(board, [4, 0], [3, 0]);
      await clickCells(board, [4, 0], [4, 1]);
      await nextTick();
      expect(wrapper.text()).toContain("错误 1 次");

      await wrapper.find('[data-test="submit"]').trigger("click");
      await flushPromises();

      expect(wrapper.text()).toContain("第二题");
      expect(wrapper.find('[data-test="progress"]').text()).toContain("2 / 2");
      expect(wrapper.text()).toContain("错误 0 次");
      expect(wrapper.text()).toContain("用时 0 秒");
      expect(wrapper.find('[data-test="done"]').exists()).toBe(false);
      wrapper.unmount();
    } finally {
      vi.useRealTimers();
    }
  });

  it("both 模式下不能选中非当前方棋子", async () => {
    const wrapper = mountView();
    await flushPromises();
    const board = wrapper.findComponent(BoardStub);

    await clickCells(board, [4, 9]);
    expect(board.props("selected")).toBeNull();

    await clickCells(board, [4, 0]);
    expect(board.props("selected")).toEqual({ x: 4, y: 0 });
  });

  it("完成态冻结用时", async () => {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
    try {
      const wrapper = mountView();
      await flushPromises();
      const board = wrapper.findComponent(BoardStub);

      vi.advanceTimersByTime(2000);
      await nextTick();
      expect(wrapper.text()).toContain("用时 2 秒");

      await clickCells(board, [4, 0], [4, 1]);
      await nextTick();
      expect(wrapper.find('[data-test="done"]').exists()).toBe(true);

      vi.advanceTimersByTime(5000);
      await nextTick();
      expect(wrapper.text()).toContain("用时 2 秒");
      wrapper.unmount();
    } finally {
      vi.useRealTimers();
    }
  });
});
