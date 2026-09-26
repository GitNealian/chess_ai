import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import MobilePieceChooser from "../MobilePieceChooser.vue";

const piece = (side, kind, x, y) => ({ x, y, side, kind });

describe("MobilePieceChooser", () => {
  it("渲染两行共 14 个候选按钮", () => {
    const wrapper = mount(MobilePieceChooser);
    expect(wrapper.findAll("button")).toHaveLength(14);
  });

  it("点击候选发出 select 事件", async () => {
    const wrapper = mount(MobilePieceChooser);
    await wrapper.find("[data-piece='black-R']").trigger("click");
    expect(wrapper.emitted("select")[0]).toEqual([{ side: "black", kind: "R" }]);
  });

  it("上方黑方、下方红方，且顺序为帅士兵马车炮兵", () => {
    const wrapper = mount(MobilePieceChooser);
    const black = wrapper.find("[data-row='black']");
    const red = wrapper.find("[data-row='red']");
    expect(black.findAll("button").map((b) => b.text())).toEqual([
      "将",
      "士",
      "象",
      "马",
      "车",
      "炮",
      "卒",
    ]);
    expect(red.findAll("button").map((b) => b.text())).toEqual([
      "帅",
      "仕",
      "相",
      "马",
      "车",
      "炮",
      "兵",
    ]);
  });

  it("棋子达到上限时对应按钮禁用", () => {
    const wrapper = mount(MobilePieceChooser, {
      props: {
        pieces: [piece("black", "R", 0, 0), piece("black", "R", 1, 0)],
      },
    });
    expect(wrapper.find("[data-piece='black-R']").attributes("disabled")).toBeDefined();
  });

  it("棋子未达上限时对应按钮可点", () => {
    const wrapper = mount(MobilePieceChooser, {
      props: { pieces: [piece("black", "R", 0, 0)] },
    });
    expect(wrapper.find("[data-piece='black-R']").attributes("disabled")).toBeUndefined();
  });

  it("选中项高亮", () => {
    const wrapper = mount(MobilePieceChooser, {
      props: { selected: { side: "black", kind: "R" } },
    });
    expect(wrapper.find("[data-piece='black-R']").classes()).toContain("active");
  });
});
