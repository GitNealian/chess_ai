import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import PiecePalette from "../PiecePalette.vue";

function findPiece(wrapper, side, kind) {
  return wrapper.find(`[data-piece="${side}-${kind}"]`);
}

describe("PiecePalette", () => {
  it("渲染红黑各 7 种棋子", () => {
    const wrapper = mount(PiecePalette);
    expect(wrapper.findAll("[data-piece]")).toHaveLength(14);
  });

  it("点击棋子发出 select 事件", async () => {
    const wrapper = mount(PiecePalette);
    await findPiece(wrapper, "red", "R").trigger("click");
    expect(wrapper.emitted("select")[0]).toEqual([{ side: "red", kind: "R" }]);
  });

  it("选中项带高亮样式", () => {
    const wrapper = mount(PiecePalette, {
      props: { selected: { side: "black", kind: "C" } },
    });
    expect(findPiece(wrapper, "black", "C").classes()).toContain("active");
  });

  it("清空与标准开局按钮发出事件", async () => {
    const wrapper = mount(PiecePalette);
    await wrapper.find('[data-test="palette-clear"]').trigger("click");
    await wrapper.find('[data-test="palette-initial"]').trigger("click");
    expect(wrapper.emitted("clear")).toHaveLength(1);
    expect(wrapper.emitted("initial")).toHaveLength(1);
  });
});
