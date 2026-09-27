import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { nextTick } from "vue";
import MobileInferenceDialog from "../MobileInferenceDialog.vue";

vi.mock("../../../api", () => ({
  api: { validateMove: vi.fn() },
  analyzeStream: vi.fn(),
  intentStream: vi.fn(),
}));

import { analyzeStream, api } from "../../../api";

const FEN = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1";
const baseMoves = [{ x1: 0, y1: 0, x2: 0, y2: 1, chinese: "车九进一" }];

function mountDialog(props = {}) {
  return mount(MobileInferenceDialog, {
    props: { initialFen: FEN, baseMoves, ...props },
  });
}

describe("MobileInferenceDialog", () => {
  beforeEach(() => {
    api.validateMove.mockReset();
    analyzeStream.mockReset();
  });

  it("以快照局面发起评分，moves 为 baseMoves", () => {
    mountDialog();
    expect(analyzeStream).toHaveBeenCalledTimes(1);
    const payload = analyzeStream.mock.calls[0][0];
    expect(payload.initial_fen).toBe(FEN);
    expect(payload.moves).toEqual([{ x1: 0, y1: 0, x2: 0, y2: 1 }]);
  });

  it("弹窗内走子经 validateMove 校验，参数含快照与推演着法", async () => {
    api.validateMove.mockResolvedValue({ legal: true, chinese: "车1进1", check: false });
    const wrapper = mountDialog();
    // 快照走完一步后轮到黑方，黑车在 (0,9)
    await wrapper.find("[data-cell='0-9']").trigger("click");
    await wrapper.find("[data-cell='0-8']").trigger("click");
    await flushPromises();
    expect(api.validateMove).toHaveBeenCalledTimes(1);
    const payload = api.validateMove.mock.calls[0][0];
    expect(payload.initial_fen).toBe(FEN);
    expect(payload.moves).toEqual([{ x1: 0, y1: 0, x2: 0, y2: 1 }]);
    expect(payload.move).toEqual({ x1: 0, y1: 9, x2: 0, y2: 8 });
  });

  it("悔棋撤销一步推演", async () => {
    api.validateMove.mockResolvedValue({ legal: true, chinese: "车1进1", check: false });
    const wrapper = mountDialog();
    await wrapper.find("[data-cell='0-9']").trigger("click");
    await wrapper.find("[data-cell='0-8']").trigger("click");
    await flushPromises();
    expect(analyzeStream.mock.calls.at(-1)[0].moves).toHaveLength(2);
    await wrapper.find("[data-test='infer-undo']").trigger("click");
    await nextTick();
    await flushPromises();
    expect(analyzeStream.mock.calls.at(-1)[0].moves).toEqual([
      { x1: 0, y1: 0, x2: 0, y2: 1 },
    ]);
  });

  it("关闭按钮发出 close", async () => {
    const wrapper = mountDialog();
    await wrapper.find("[data-test='infer-close']").trigger("click");
    expect(wrapper.emitted("close")).toHaveLength(1);
  });

  it("非法着法显示提示且不追加", async () => {
    api.validateMove.mockResolvedValue({ legal: false, reason: "着法不合法" });
    const wrapper = mountDialog();
    await wrapper.find("[data-cell='0-9']").trigger("click");
    await wrapper.find("[data-cell='1-8']").trigger("click");
    await flushPromises();
    expect(wrapper.find("[data-test='infer-hint']").text()).toContain("着法不合法");
  });
});
