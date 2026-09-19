import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createPinia } from "pinia";
import LibraryView from "../LibraryView.vue";
import { api } from "../../api";

vi.mock("../../api", () => ({
  api: {
    listGames: vi.fn(),
    stats: vi.fn(),
    deleteGame: vi.fn(),
  },
}));

const games = [
  {
    id: 1,
    name: "中炮对屏风马",
    category: "开局",
    practice_side: "both",
  },
  {
    id: 2,
    name: "顺炮直车",
    category: "开局",
    practice_side: "red",
  },
  {
    id: 3,
    name: "列手炮",
    category: "残局",
    practice_side: "black",
  },
];

function mountView() {
  return mount(LibraryView, {
    global: {
      plugins: [createPinia()],
      stubs: { RouterLink: true },
    },
  });
}

describe("LibraryView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.listGames.mockResolvedValue({ items: games });
    api.stats.mockResolvedValue({ total: 5, reviewed: 1, new: 2, due: 2, mastered: 3 });
    api.deleteGame.mockResolvedValue(undefined);
  });

  it("渲染棋谱名称、分类与阵营文本", async () => {
    const wrapper = mountView();
    await flushPromises();

    const text = wrapper.text();
    expect(text).toContain("中炮对屏风马");
    expect(text).toContain("顺炮直车");
    expect(text).toContain("列手炮");
    expect(text).toContain("双方");
    expect(text).toContain("红方");
    expect(text).toContain("黑方");
    expect(wrapper.findAll("tbody tr")).toHaveLength(3);
  });

  it("渲染统计栏数字", async () => {
    const wrapper = mountView();
    await flushPromises();

    const stats = wrapper.find(".stats").text();
    expect(stats).toContain("共 5");
    expect(stats).toContain("待复习 2");
    expect(stats).toContain("已掌握 3");
  });

  it("无棋谱时显示空态文案", async () => {
    api.listGames.mockResolvedValue({ items: [] });
    const wrapper = mountView();
    await flushPromises();

    expect(wrapper.text()).toContain("暂无棋谱，点击「新建棋谱」开始。");
    expect(wrapper.find("table").exists()).toBe(false);
  });

  it("输入关键字时重新拉取并传参", async () => {
    const wrapper = mountView();
    await flushPromises();

    await wrapper.find("input[placeholder='搜索棋谱名']").setValue("顺炮");
    await flushPromises();

    expect(api.listGames).toHaveBeenLastCalledWith({ keyword: "顺炮", category: undefined });
  });

  it("点击删除调用 store.remove 并移除行", async () => {
    const wrapper = mountView();
    await flushPromises();

    await wrapper.findAll("tbody tr")[0].find("button").trigger("click");
    await flushPromises();

    expect(api.deleteGame).toHaveBeenCalledWith(1);
    expect(wrapper.findAll("tbody tr")).toHaveLength(2);
    expect(wrapper.text()).not.toContain("中炮对屏风马");
  });
});
