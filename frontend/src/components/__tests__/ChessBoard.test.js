import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import ChessBoard from "../ChessBoard.vue";

const position = { pieces: [{ x: 4, y: 0, side: "red", kind: "K", label: "帅" }] };

describe("ChessBoard", () => {
  it("渲染棋子", () => {
    const wrapper = mount(ChessBoard, { props: { position } });
    expect(wrapper.text()).toContain("帅");
  });

  it("点击格子发出 cell-click 事件", async () => {
    const wrapper = mount(ChessBoard, { props: { position } });
    await wrapper.find("[data-cell='0-0']").trigger("click");
    expect(wrapper.emitted("cell-click")[0]).toEqual([0, 0]);
  });

  it("点击不同格子发出对应坐标", async () => {
    const wrapper = mount(ChessBoard, { props: { position } });
    await wrapper.find("[data-cell='8-9']").trigger("click");
    expect(wrapper.emitted("cell-click")[0]).toEqual([8, 9]);
  });

  it("渲染恰好 90 个热区", () => {
    const wrapper = mount(ChessBoard, { props: { position } });
    expect(wrapper.findAll("[data-cell]")).toHaveLength(90);
  });

  it("渲染多枚棋子并可点击其坐标", async () => {
    const multi = {
      pieces: [
        { x: 4, y: 0, side: "red", kind: "K", label: "帅" },
        { x: 4, y: 9, side: "black", kind: "k", label: "将" },
        { x: 1, y: 2, side: "red", kind: "C", label: "炮" },
      ],
    };
    const wrapper = mount(ChessBoard, { props: { position: multi } });
    expect(wrapper.text()).toContain("帅");
    expect(wrapper.text()).toContain("将");
    expect(wrapper.text()).toContain("炮");

    await wrapper.find("[data-cell='4-9']").trigger("click");
    expect(wrapper.emitted("cell-click")[0]).toEqual([4, 9]);
  });

  it("渲染 legalTargets 绿点标记", () => {
    const wrapper = mount(ChessBoard, {
      props: {
        position,
        legalTargets: [
          { x: 3, y: 0 },
          { x: 5, y: 0 },
        ],
      },
    });
    const dots = wrapper.findAll('circle[fill="rgba(40,140,60,0.55)"]');
    expect(dots).toHaveLength(2);
  });

  it("渲染 selected 选中高亮", () => {
    const wrapper = mount(ChessBoard, {
      props: { position, selected: { x: 4, y: 0 } },
    });
    expect(wrapper.findAll(".selected")).toHaveLength(1);
    expect(wrapper.html()).toContain("rgba(212,160,23,0.25)");
  });
});
