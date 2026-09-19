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
});
