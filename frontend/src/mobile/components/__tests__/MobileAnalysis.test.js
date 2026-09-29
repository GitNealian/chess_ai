import { beforeEach, describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import { nextTick } from "vue";
import MobileAnalysis from "../MobileAnalysis.vue";

vi.mock("../../../api", () => ({
  analyzeStream: vi.fn(),
  intentStream: vi.fn(),
}));

import { analyzeStream, intentStream } from "../../../api";

const FEN = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1";
const moves = [{ x1: 0, y1: 3, x2: 0, y2: 4, chinese: "炮二平一" }];

function mountAnalysis(props) {
  return mount(MobileAnalysis, {
    props: { initialFen: FEN, moves: [], score: false, intent: false, ...props },
  });
}

describe("MobileAnalysis", () => {
  beforeEach(() => {
    analyzeStream.mockReset();
    intentStream.mockReset();
  });

  it("两个开关都关时不请求也不渲染", () => {
    const wrapper = mountAnalysis({});
    expect(analyzeStream).not.toHaveBeenCalled();
    expect(intentStream).not.toHaveBeenCalled();
    expect(wrapper.find("[data-test='mobile-score']").exists()).toBe(false);
  });

  it("仅开启评分时直接分析并渲染评分条", () => {
    const wrapper = mountAnalysis({ score: true });
    expect(analyzeStream).toHaveBeenCalledTimes(1);
    expect(intentStream).not.toHaveBeenCalled();
    expect(analyzeStream.mock.calls[0][0]).toEqual({ initial_fen: FEN, moves: [] });
    expect(wrapper.find("[data-test='mobile-score']").exists()).toBe(true);
  });

  it("仅开启意图时只推演、不评分", () => {
    const wrapper = mountAnalysis({ intent: true });
    expect(intentStream).toHaveBeenCalledTimes(1);
    expect(analyzeStream).not.toHaveBeenCalled();
    expect(wrapper.find("[data-test='intent-panel']").exists()).toBe(true);
  });

  it("意图完成后才发起评分", () => {
    mountAnalysis({ score: true, intent: true });
    expect(intentStream).toHaveBeenCalledTimes(1);
    expect(analyzeStream).not.toHaveBeenCalled();
    intentStream.mock.calls[0][1].onDone();
    expect(analyzeStream).toHaveBeenCalledTimes(1);
  });

  it("着法以 x1,y1,x2,y2 形式传出", () => {
    mountAnalysis({ score: true, moves });
    expect(analyzeStream.mock.calls[0][0].moves).toEqual([
      { x1: 0, y1: 3, x2: 0, y2: 4 },
    ]);
  });

  it("分析结果逐层展示并抛出最新两着法箭头", async () => {
    analyzeStream.mockImplementation((payload, { onResult }) => {
      onResult({
        depth: 11,
        score_red: 20,
        mate: null,
        pv: [
          { x1: 0, y1: 0, x2: 0, y2: 1, chinese: "炮二平三" },
          { x1: 1, y1: 0, x2: 1, y2: 1, chinese: "马二进三" },
        ],
        time_ms: 12,
      });
    });
    const wrapper = mountAnalysis({ score: true });
    await nextTick();
    const items = wrapper.findAll("[data-test='mobile-analysis-item']");
    expect(items).toHaveLength(1);
    expect(items[0].text()).toContain("第 11 层");
    expect(items[0].text()).toContain("炮二平三");
    const arrows = wrapper.emitted("arrows").at(-1)[0];
    expect(arrows).toEqual([
      { x1: 0, y1: 0, x2: 0, y2: 1, chinese: "炮二平三", kind: "best" },
      { x1: 1, y1: 0, x2: 1, y2: 1, chinese: "马二进三", kind: "reply" },
    ]);
  });

  it("关闭评分后清空棋盘箭头", async () => {
    analyzeStream.mockImplementation((payload, { onResult }) => {
      onResult({
        depth: 11,
        score_red: 20,
        mate: null,
        pv: [
          { x1: 0, y1: 0, x2: 0, y2: 1, chinese: "炮二平三" },
          { x1: 1, y1: 0, x2: 1, y2: 1, chinese: "马二进三" },
        ],
        time_ms: 12,
      });
    });
    const wrapper = mountAnalysis({ score: true });
    await nextTick();
    expect(wrapper.emitted("arrows").at(-1)[0]).toHaveLength(2);
    await wrapper.setProps({ score: false });
    await nextTick();
    expect(wrapper.emitted("arrows").at(-1)[0]).toEqual([]);
  });

  it("意图与评分同开后关闭评分时清空箭头", async () => {
    intentStream.mockImplementation((payload, { onDone }) => onDone());
    analyzeStream.mockImplementation((payload, { onResult }) => {
      onResult({
        depth: 11,
        score_red: 20,
        mate: null,
        pv: [
          { x1: 0, y1: 0, x2: 0, y2: 1, chinese: "炮二平三" },
          { x1: 1, y1: 0, x2: 1, y2: 1, chinese: "马二进三" },
        ],
        time_ms: 12,
      });
    });
    const wrapper = mountAnalysis({ score: true, intent: true });
    await nextTick();
    expect(wrapper.emitted("arrows").at(-1)[0]).toHaveLength(2);
    await wrapper.setProps({ score: false });
    await nextTick();
    expect(wrapper.emitted("arrows").at(-1)[0]).toEqual([]);
  });
});
