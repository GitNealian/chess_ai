import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import ChessBoard from "../../../components/ChessBoard.vue";
import MobileBoardEditor from "../MobileBoardEditor.vue";
import { INITIAL_FEN, fenToPieces } from "../../../utils/chess";

vi.mock("../../../api", () => ({
  api: { validatePosition: vi.fn() },
}));

import { api } from "../../../api";

const initialPieces = () => fenToPieces(INITIAL_FEN);
const onlyRedKing = () => [{ x: 4, y: 0, side: "red", kind: "K", label: "帅" }];

describe("MobileBoardEditor", () => {
  beforeEach(() => {
    api.validatePosition.mockReset();
  });

  it("渲染弹窗并复制初始局面", () => {
    const wrapper = mount(MobileBoardEditor, { props: { pieces: initialPieces() } });
    expect(wrapper.find("[data-test='editor-card']").exists()).toBe(true);
    expect(wrapper.findAll("g")).toHaveLength(32);
  });

  it("点棋盘棋子后选中", async () => {
    const wrapper = mount(MobileBoardEditor, { props: { pieces: initialPieces() } });
    await wrapper.find("[data-cell='4-0']").trigger("click");
    expect(wrapper.findComponent(ChessBoard).props("selected")).toEqual({ x: 4, y: 0 });
  });

  it("再点选中的棋子自己删除它", async () => {
    const wrapper = mount(MobileBoardEditor, { props: { pieces: initialPieces() } });
    await wrapper.find("[data-cell='4-0']").trigger("click");
    await wrapper.find("[data-cell='4-0']").trigger("click");
    expect(wrapper.findAll("g")).toHaveLength(31);
  });

  it("选中棋子后点空格完成移动", async () => {
    const wrapper = mount(MobileBoardEditor, { props: { pieces: initialPieces() } });
    await wrapper.find("[data-cell='4-0']").trigger("click");
    await wrapper.find("[data-cell='4-1']").trigger("click");
    const pieces = wrapper.findComponent(ChessBoard).props("position").pieces;
    expect(pieces.find((p) => p.x === 4 && p.y === 1)).toMatchObject({
      side: "red",
      kind: "K",
    });
    expect(pieces.find((p) => p.x === 4 && p.y === 0)).toBeUndefined();
  });

  it("选中候选棋子后点空格放置", async () => {
    const wrapper = mount(MobileBoardEditor, { props: { pieces: onlyRedKing() } });
    await wrapper.find("[data-piece='black-R']").trigger("click");
    await wrapper.find("[data-cell='0-4']").trigger("click");
    const pieces = wrapper.findComponent(ChessBoard).props("position").pieces;
    expect(pieces.find((p) => p.x === 0 && p.y === 4)).toMatchObject({
      side: "black",
      kind: "R",
    });
  });

  it("行棋方用单选，默认红先且可切换黑先", async () => {
    const wrapper = mount(MobileBoardEditor, { props: { pieces: initialPieces() } });
    const red = wrapper.find("[data-test='editor-side-red']");
    const black = wrapper.find("[data-test='editor-side-black']");
    expect(red.element.checked).toBe(true);
    await black.setValue();
    expect(black.element.checked).toBe(true);
    expect(red.element.checked).toBe(false);
  });

  it("切换黑先后提交 side_to_move=black", async () => {
    api.validatePosition.mockResolvedValue({ valid: true });
    const wrapper = mount(MobileBoardEditor, { props: { pieces: onlyRedKing() } });
    await wrapper.find("[data-test='editor-side-black']").setValue();
    await wrapper.find("[data-test='editor-apply']").trigger("click");
    await flushPromises();
    expect(api.validatePosition).toHaveBeenCalledWith(
      expect.objectContaining({ side_to_move: "black" })
    );
  });

  it("点清空按钮清空棋盘", async () => {
    const wrapper = mount(MobileBoardEditor, { props: { pieces: initialPieces() } });
    await wrapper.find("[data-test='editor-clear']").trigger("click");
    expect(wrapper.findAll("g")).toHaveLength(0);
  });

  it("点取消发出 cancel", async () => {
    const wrapper = mount(MobileBoardEditor, { props: { pieces: initialPieces() } });
    await wrapper.find("[data-test='editor-cancel']").trigger("click");
    expect(wrapper.emitted("cancel")).toHaveLength(1);
  });

  it("校验不合法时显示错误且不应用", async () => {
    api.validatePosition.mockResolvedValue({
      valid: false,
      errors: ["红方必须有且仅有一个帅"],
    });
    const wrapper = mount(MobileBoardEditor, { props: { pieces: initialPieces() } });
    await wrapper.find("[data-test='editor-apply']").trigger("click");
    await flushPromises();
    expect(wrapper.find("[data-test='editor-error']").text()).toContain("红方必须有且仅有一个帅");
    expect(wrapper.emitted("apply")).toBeUndefined();
  });

  it("校验合法时发出 apply 并带当前棋子", async () => {
    api.validatePosition.mockResolvedValue({ valid: true });
    const wrapper = mount(MobileBoardEditor, { props: { pieces: onlyRedKing() } });
    await wrapper.find("[data-test='editor-apply']").trigger("click");
    await flushPromises();
    const payload = wrapper.emitted("apply")[0][0];
    expect(payload).toHaveLength(1);
    expect(payload[0]).toMatchObject({ x: 4, y: 0, side: "red", kind: "K" });
  });

  it("校验合法时透传返回的 fen", async () => {
    api.validatePosition.mockResolvedValue({ valid: true, fen: "custom-fen" });
    const wrapper = mount(MobileBoardEditor, { props: { pieces: onlyRedKing() } });
    await wrapper.find("[data-test='editor-apply']").trigger("click");
    await flushPromises();
    expect(wrapper.emitted("apply")[0][1]).toBe("custom-fen");
  });

  it("默认标题为编辑局面且无提示", () => {
    const wrapper = mount(MobileBoardEditor, { props: { pieces: onlyRedKing() } });
    expect(wrapper.find(".editor-title").text()).toBe("编辑局面");
    expect(wrapper.find("[data-test='editor-notice']").exists()).toBe(false);
  });

  it("可自定义标题与提示", () => {
    const wrapper = mount(MobileBoardEditor, {
      props: {
        pieces: onlyRedKing(),
        title: "识别结果",
        notice: "识别可能有误，请核对后确认",
      },
    });
    expect(wrapper.find(".editor-title").text()).toBe("识别结果");
    expect(wrapper.find("[data-test='editor-notice']").text()).toBe("识别可能有误，请核对后确认");
  });
});
