import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import MobileGamePicker from "../MobileGamePicker.vue";

vi.mock("../../../api", () => ({ api: { listGames: vi.fn() } }));

import { api } from "../../../api";

describe("MobileGamePicker", () => {
  beforeEach(() => {
    api.listGames.mockReset();
  });

  it("加载并渲染棋谱列表", async () => {
    api.listGames.mockResolvedValue({
      items: [
        { id: 1, name: "对局一", red_player: "甲", black_player: "乙" },
        { id: 2, name: "对局二" },
      ],
    });
    const wrapper = mount(MobileGamePicker);
    await flushPromises();
    expect(wrapper.findAll("[data-game]")).toHaveLength(2);
    expect(wrapper.text()).toContain("对局一");
  });

  it("点击棋谱发出 select", async () => {
    api.listGames.mockResolvedValue({
      items: [{ id: 7, name: "测试局", red_player: "", black_player: "" }],
    });
    const wrapper = mount(MobileGamePicker);
    await flushPromises();
    await wrapper.find("[data-game='7']").trigger("click");
    expect(wrapper.emitted("select")[0][0]).toMatchObject({ id: 7, name: "测试局" });
  });

  it("空列表显示提示", async () => {
    api.listGames.mockResolvedValue({ items: [] });
    const wrapper = mount(MobileGamePicker);
    await flushPromises();
    expect(wrapper.find("[data-test='picker-empty']").exists()).toBe(true);
  });

  it("点取消发出 cancel", async () => {
    api.listGames.mockResolvedValue({ items: [] });
    const wrapper = mount(MobileGamePicker);
    await flushPromises();
    await wrapper.find("[data-test='picker-cancel']").trigger("click");
    expect(wrapper.emitted("cancel")).toHaveLength(1);
  });
});
