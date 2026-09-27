import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import BoardControls from "../BoardControls.vue";

describe("BoardControls", () => {
  it("渲染 6 个控制按钮", () => {
    const wrapper = mount(BoardControls);
    const buttons = wrapper.findAll("button");
    expect(buttons).toHaveLength(6);
    expect(buttons.map((b) => b.text())).toEqual([
      "开局",
      "后退",
      "前进",
      "终局",
      "翻转",
      "编辑",
    ]);
  });

  it("点击翻转发出 flip 事件", async () => {
    const wrapper = mount(BoardControls);
    await wrapper.find("[data-test='ctrl-flip']").trigger("click");
    expect(wrapper.emitted("flip")).toHaveLength(1);
  });

  it("canXxx 为 false 时对应按钮禁用", () => {
    const wrapper = mount(BoardControls);
    for (const key of ["start", "prev", "next", "end", "edit"]) {
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
      },
    });
    for (const key of ["start", "prev", "next", "end", "edit"]) {
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
});
