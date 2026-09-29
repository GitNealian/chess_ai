import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import BoardControls from "../BoardControls.vue";

describe("BoardControls", () => {
  it("渲染 7 个控制按钮", () => {
    const wrapper = mount(BoardControls);
    const buttons = wrapper.findAll(".board-controls__track button");
    expect(buttons).toHaveLength(7);
    expect(buttons.map((b) => b.text())).toEqual([
      "开局",
      "后退",
      "前进",
      "终局",
      "翻转",
      "编辑",
      "扫描",
    ]);
  });

  it("点击翻转发出 flip 事件", async () => {
    const wrapper = mount(BoardControls);
    await wrapper.find("[data-test='ctrl-flip']").trigger("click");
    expect(wrapper.emitted("flip")).toHaveLength(1);
  });

  it("canXxx 为 false 时对应按钮禁用", () => {
    const wrapper = mount(BoardControls);
    for (const key of ["start", "prev", "next", "end", "edit", "scan"]) {
      expect(wrapper.find(`[data-test='ctrl-${key}']`).attributes("disabled")).toBeDefined();
    }
  });

  it("canXxx 为 true 时点击发出对应事件", async () => {
    const wrapper = mount(BoardControls, {
      props: {
        canStart: true,
        canPrev: true,
        canNext: true,
        canEnd: true,
        canEdit: true,
        canScan: true,
      },
    });
    for (const key of ["start", "prev", "next", "end", "edit", "scan"]) {
      await wrapper.find(`[data-test='ctrl-${key}']`).trigger("click");
      expect(wrapper.emitted(key)).toHaveLength(1);
    }
  });

  it("flipped 为 true 时翻转按钮 aria-pressed 为 true", () => {
    const wrapper = mount(BoardControls, { props: { flipped: true } });
    expect(wrapper.find("[data-test='ctrl-flip']").attributes("aria-pressed")).toBe("true");
  });

  it("showInfer 为 true 时额外渲染推演按钮并发出 infer", async () => {
    const wrapper = mount(BoardControls, { props: { showInfer: true, canInfer: true } });
    const infer = wrapper.find("[data-test='ctrl-infer']");
    expect(infer.exists()).toBe(true);
    await infer.trigger("click");
    expect(wrapper.emitted("infer")).toHaveLength(1);
  });

  it("showInfer 缺省不渲染推演按钮", () => {
    const wrapper = mount(BoardControls);
    expect(wrapper.find("[data-test='ctrl-infer']").exists()).toBe(false);
  });

  it("showNav 为 true 时渲染上一盘/下一盘并发出事件", async () => {
    const wrapper = mount(BoardControls, { props: { showNav: true } });
    const prev = wrapper.find("[data-test='ctrl-prev-game']");
    const next = wrapper.find("[data-test='ctrl-next-game']");
    expect(prev.exists()).toBe(true);
    expect(next.exists()).toBe(true);
    await prev.trigger("click");
    await next.trigger("click");
    expect(wrapper.emitted("prev-game")).toHaveLength(1);
    expect(wrapper.emitted("next-game")).toHaveLength(1);
  });

  it("showNav 缺省不渲染上一盘/下一盘", () => {
    const wrapper = mount(BoardControls);
    expect(wrapper.find("[data-test='ctrl-prev-game']").exists()).toBe(false);
    expect(wrapper.find("[data-test='ctrl-next-game']").exists()).toBe(false);
  });

  it("showRecite 为 true 时渲染背谱按钮并发出 recite", async () => {
    const wrapper = mount(BoardControls, { props: { showRecite: true } });
    const recite = wrapper.find("[data-test='ctrl-recite']");
    expect(recite.exists()).toBe(true);
    await recite.trigger("click");
    expect(wrapper.emitted("recite")).toHaveLength(1);
  });

  it("showRecite 缺省不渲染背谱按钮", () => {
    const wrapper = mount(BoardControls);
    expect(wrapper.find("[data-test='ctrl-recite']").exists()).toBe(false);
  });

  it("mode 为 recite 时只渲染导航与背谱操作按钮", async () => {
    const wrapper = mount(BoardControls, { props: { mode: "recite", showNav: true } });
    const buttons = wrapper.findAll(".board-controls__track button");
    expect(buttons.map((b) => b.text())).toEqual([
      "上一盘",
      "下一盘",
      "翻转",
      "看答案",
      "退出背谱",
    ]);
    await wrapper.find("[data-test='ctrl-reveal']").trigger("click");
    await wrapper.find("[data-test='ctrl-exit-recite']").trigger("click");
    expect(wrapper.emitted("reveal")).toHaveLength(1);
    expect(wrapper.emitted("exit-recite")).toHaveLength(1);
  });
});
