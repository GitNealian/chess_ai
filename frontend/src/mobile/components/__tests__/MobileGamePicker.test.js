import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import MobileGamePicker from "../MobileGamePicker.vue";

vi.mock("../../../api", () => ({
  api: { listGames: vi.fn(), listCollections: vi.fn(), listEvents: vi.fn(), reviewQueue: vi.fn() },
}));

import { api } from "../../../api";

const game = (id, name) => ({ id, name, red_player: "", black_player: "" });

describe("MobileGamePicker", () => {
  beforeEach(() => {
    api.listGames.mockReset();
    api.listCollections.mockReset();
    api.listEvents.mockReset();
    api.reviewQueue.mockReset();
  });

  it("初始显示分类按钮且不加载列表", () => {
    const wrapper = mount(MobileGamePicker);
    expect(wrapper.find("[data-test='menu-collection']").text()).toContain("棋谱");
    expect(wrapper.find("[data-test='menu-tournament']").text()).toContain("赛事");
    expect(wrapper.find("[data-test='menu-other']").text()).toContain("其它");
    expect(wrapper.find("[data-test='picker-cancel']").text()).toContain("返回");
    expect(api.listGames).not.toHaveBeenCalled();
    expect(api.listCollections).not.toHaveBeenCalled();
    expect(api.listEvents).not.toHaveBeenCalled();
  });

  it("进入棋谱分类先显示棋谱集", async () => {
    api.listCollections.mockResolvedValue({
      items: [{ name: "桔中秘", count: 3 }],
      total: 1,
    });
    const wrapper = mount(MobileGamePicker);
    await wrapper.find("[data-test='menu-collection']").trigger("click");
    await flushPromises();
    expect(api.listCollections).toHaveBeenCalledWith({ page: 1, page_size: 20 });
    expect(wrapper.find("[data-collection='桔中秘']").exists()).toBe(true);
  });

  it("点集名进入集内棋谱并可选择", async () => {
    api.listCollections.mockResolvedValue({
      items: [{ name: "桔中秘", count: 1 }],
      total: 1,
    });
    api.listGames.mockResolvedValue({ items: [game(7, "开局")], total: 1 });
    const wrapper = mount(MobileGamePicker);
    await wrapper.find("[data-test='menu-collection']").trigger("click");
    await flushPromises();
    await wrapper.find("[data-collection='桔中秘']").trigger("click");
    await flushPromises();
    expect(api.listGames).toHaveBeenCalledWith(
      expect.objectContaining({
        scope: "collection",
        collection: "桔中秘",
        sort: "created_desc",
        page: 1,
      })
    );
    await wrapper.find("[data-game='7']").trigger("click");
    expect(wrapper.emitted("select")[0][0]).toMatchObject({ id: 7 });
  });

  it("赛事先按赛事名分组，点入后显示棋谱", async () => {
    api.listEvents.mockResolvedValue({ items: [{ name: "联赛", count: 5 }], total: 1 });
    api.listGames.mockResolvedValue({ items: [game(9, "赛事局")], total: 1 });
    const wrapper = mount(MobileGamePicker);
    await wrapper.find("[data-test='menu-tournament']").trigger("click");
    await flushPromises();
    expect(api.listEvents).toHaveBeenCalledWith({ page: 1, page_size: 20 });
    expect(wrapper.find("[data-event='联赛']").exists()).toBe(true);
    await wrapper.find("[data-event='联赛']").trigger("click");
    await flushPromises();
    expect(api.listGames).toHaveBeenCalledWith(
      expect.objectContaining({ scope: "event", event: "联赛", page: 1 })
    );
    expect(wrapper.find("[data-game='9']").exists()).toBe(true);
  });

  it("其它分类直接列出棋谱", async () => {
    api.listGames.mockResolvedValue({ items: [], total: 0 });
    const wrapper = mount(MobileGamePicker);
    await wrapper.find("[data-test='menu-other']").trigger("click");
    await flushPromises();
    expect(api.listGames).toHaveBeenCalledWith(expect.objectContaining({ scope: "other" }));
  });

  it("最近分类按打开时间列出棋谱", async () => {
    api.listGames.mockResolvedValue({ items: [game(3, "最近局")], total: 1 });
    const wrapper = mount(MobileGamePicker);
    await wrapper.find("[data-test='menu-recent']").trigger("click");
    await flushPromises();
    expect(api.listGames).toHaveBeenCalledWith(expect.objectContaining({ scope: "recent" }));
    expect(wrapper.find("[data-game='3']").exists()).toBe(true);
  });

  it("收藏分类按收藏时间列出棋谱", async () => {
    api.listGames.mockResolvedValue({ items: [game(4, "收藏局")], total: 1 });
    const wrapper = mount(MobileGamePicker);
    await wrapper.find("[data-test='menu-favorite']").trigger("click");
    await flushPromises();
    expect(api.listGames).toHaveBeenCalledWith(expect.objectContaining({ scope: "favorite" }));
    expect(wrapper.find("[data-game='4']").exists()).toBe(true);
  });

  it("赛事列表下一页请求第二页", async () => {
    api.listEvents.mockResolvedValue({ items: [{ name: "联赛", count: 1 }], total: 40 });
    const wrapper = mount(MobileGamePicker);
    await wrapper.find("[data-test='menu-tournament']").trigger("click");
    await flushPromises();
    await wrapper.find("[data-test='pager-next']").trigger("click");
    await flushPromises();
    expect(api.listEvents).toHaveBeenLastCalledWith({ page: 2, page_size: 20 });
  });

  it("返回：棋谱集内到集列表再到菜单", async () => {
    api.listCollections.mockResolvedValue({
      items: [{ name: "桔中秘", count: 1 }],
      total: 1,
    });
    api.listGames.mockResolvedValue({ items: [game(1, "A")], total: 1 });
    const wrapper = mount(MobileGamePicker);
    await wrapper.find("[data-test='menu-collection']").trigger("click");
    await flushPromises();
    await wrapper.find("[data-collection='桔中秘']").trigger("click");
    await flushPromises();
    await wrapper.find("[data-test='picker-back']").trigger("click");
    await flushPromises();
    expect(wrapper.find("[data-test='menu-collection']").exists()).toBe(false);
    expect(wrapper.find("[data-collection='桔中秘']").exists()).toBe(true);
    await wrapper.find("[data-test='picker-back']").trigger("click");
    await flushPromises();
    expect(wrapper.find("[data-test='menu-collection']").exists()).toBe(true);
  });

  it("返回：赛事集内到赛事列表再到菜单", async () => {
    api.listEvents.mockResolvedValue({ items: [{ name: "联赛", count: 1 }], total: 1 });
    api.listGames.mockResolvedValue({ items: [game(1, "A")], total: 1 });
    const wrapper = mount(MobileGamePicker);
    await wrapper.find("[data-test='menu-tournament']").trigger("click");
    await flushPromises();
    await wrapper.find("[data-event='联赛']").trigger("click");
    await flushPromises();
    await wrapper.find("[data-test='picker-back']").trigger("click");
    await flushPromises();
    expect(wrapper.find("[data-event='联赛']").exists()).toBe(true);
    await wrapper.find("[data-test='picker-back']").trigger("click");
    await flushPromises();
    expect(wrapper.find("[data-test='menu-tournament']").exists()).toBe(true);
  });

  it("点取消发出 cancel", async () => {
    const wrapper = mount(MobileGamePicker);
    await wrapper.find("[data-test='picker-cancel']").trigger("click");
    expect(wrapper.emitted("cancel")).toHaveLength(1);
  });

  it("复习入口加载待复习棋谱并携带来源", async () => {
    api.reviewQueue.mockResolvedValue({
      items: [
        {
          game: { id: 5, name: "待复习局", red_player: "红甲", black_player: "黑乙" },
          due_date: "2026-09-29",
          is_new: false,
        },
      ],
      count: 1,
    });
    const wrapper = mount(MobileGamePicker);
    await wrapper.find("[data-test='menu-review']").trigger("click");
    await flushPromises();
    expect(api.reviewQueue).toHaveBeenCalledWith({ limit: 200 });
    expect(wrapper.find("[data-review='5']").exists()).toBe(true);
    await wrapper.find("[data-review='5']").trigger("click");
    expect(wrapper.emitted("select")[0][1]).toEqual({ type: "review" });
  });

  it("复习空队列显示空态", async () => {
    api.reviewQueue.mockResolvedValue({ items: [], count: 0 });
    const wrapper = mount(MobileGamePicker);
    await wrapper.find("[data-test='menu-review']").trigger("click");
    await flushPromises();
    expect(wrapper.find("[data-test='picker-empty']").exists()).toBe(true);
  });

  it("棋谱选择携带来源", async () => {
    api.listGames.mockResolvedValue({ items: [game(7, "开局")], total: 1 });
    const wrapper = mount(MobileGamePicker);
    await wrapper.find("[data-test='menu-other']").trigger("click");
    await flushPromises();
    await wrapper.find("[data-game='7']").trigger("click");
    expect(wrapper.emitted("select")[0][1]).toMatchObject({ type: "other" });
  });
});
