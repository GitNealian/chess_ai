import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import MobileVariationPicker from "../MobileVariationPicker.vue";

const branches = [
  {
    move: { x1: 1, y1: 2, x2: 4, y2: 2, chinese: "炮二平五" },
    to_fen: "a",
    games: [{ id: 1, name: "甲" }],
    end_games: [],
  },
  {
    move: { x1: 7, y1: 9, x2: 6, y2: 7, chinese: "马8进7" },
    to_fen: "b",
    games: [{ id: 2, name: "乙" }],
    end_games: [{ id: 2, name: "乙" }],
  },
];

describe("MobileVariationPicker", () => {
  it("渲染各分支着法、来源谱与末步标记", () => {
    const wrapper = mount(MobileVariationPicker, {
      props: { branches, plies: { min: 5, max: 5 } },
    });
    const items = wrapper.findAll(".variation-item");
    expect(items).toHaveLength(2);
    expect(items[0].text()).toContain("炮二平五");
    expect(items[0].text()).toContain("甲");
    expect(items[1].text()).toContain("末步");
    expect(wrapper.find("[data-test='variation-plies']").text()).toContain("5 着");
  });

  it("无中文时回退坐标展示", () => {
    const wrapper = mount(MobileVariationPicker, {
      props: { branches: [{ move: { x1: 0, y1: 0, x2: 0, y2: 1 }, games: [] }] },
    });
    expect(wrapper.find(".variation-item").text()).toContain("0,0");
  });

  it("点击分支 emit select", async () => {
    const wrapper = mount(MobileVariationPicker, { props: { branches, plies: null } });
    await wrapper.find("[data-variation='0']").trigger("click");
    expect(wrapper.emitted("select")[0][0]).toEqual(branches[0]);
  });

  it("取消 emit cancel", async () => {
    const wrapper = mount(MobileVariationPicker, { props: { branches, plies: null } });
    await wrapper.find("[data-test='variation-cancel']").trigger("click");
    expect(wrapper.emitted("cancel")).toBeTruthy();
  });
});
