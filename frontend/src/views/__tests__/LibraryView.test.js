import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createPinia } from "pinia";
import { nextTick } from "vue";
import LibraryView from "../LibraryView.vue";
import { useLibraryStore } from "../../stores/library";
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
    review: null,
  },
  {
    id: 2,
    name: "顺炮直车",
    category: "开局",
    practice_side: "red",
    review: { due_date: "2026-03-01", interval: 6, repetitions: 1, lapses: 0 },
  },
  {
    id: 3,
    name: "列手炮",
    category: "残局",
    practice_side: "black",
    review: { due_date: "2026-04-01", interval: 16, repetitions: 3, lapses: 0 },
  },
];

function mountView() {
  return mount(LibraryView, {
    global: {
      plugins: [createPinia()],
      stubs: {
        RouterLink: { props: ["to"], template: '<a :href="to"><slot /></a>' },
      },
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

  it("按 review 展示掌握度与下次复习日期", async () => {
    const wrapper = mountView();
    await flushPromises();

    const rows = wrapper.findAll("tbody tr");
    expect(rows[0].findAll("td")[3].text()).toBe("新");
    expect(rows[0].findAll("td")[4].text()).toBe("今日");
    expect(rows[1].findAll("td")[3].text()).toBe("学习中");
    expect(rows[1].findAll("td")[4].text()).toBe("2026-03-01");
    expect(rows[2].findAll("td")[3].text()).toBe("已掌握");
    expect(rows[2].findAll("td")[4].text()).toBe("2026-04-01");
  });

  it("每行提供默写入口链接", async () => {
    const wrapper = mountView();
    await flushPromises();

    const rows = wrapper.findAll("tbody tr");
    expect(rows[0].text()).toContain("默写");
    expect(rows[0].find('a[href="/review?game=1"]').exists()).toBe(true);
    expect(rows[1].find('a[href="/review?game=2"]').exists()).toBe(true);
    expect(rows[2].find('a[href="/review?game=3"]').exists()).toBe(true);
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

    expect(api.listGames).toHaveBeenLastCalledWith({
      keyword: "顺炮",
      category: undefined,
      page: 1,
      page_size: 20,
    });
  });

  it("分页控件显示页码并支持翻页", async () => {
    api.listGames.mockResolvedValue({ items: games, total: 45, page: 1, page_size: 20 });
    const wrapper = mountView();
    await flushPromises();

    const info = wrapper.find('[data-test="page-info"]');
    expect(info.text()).toContain("第 1 / 3 页");
    expect(info.text()).toContain("共 45 条");

    await wrapper.find('[data-test="next-page"]').trigger("click");
    await flushPromises();
    expect(api.listGames).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 }));
  });

  it("搜索变化时重置回第一页", async () => {
    api.listGames.mockResolvedValue({ items: games, total: 45, page: 1, page_size: 20 });
    const wrapper = mountView();
    await flushPromises();

    await wrapper.find('[data-test="next-page"]').trigger("click");
    await flushPromises();
    expect(api.listGames).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 }));

    await wrapper.find("input[placeholder='搜索棋谱名']").setValue("顺炮");
    await flushPromises();
    expect(api.listGames).toHaveBeenLastCalledWith(expect.objectContaining({ page: 1 }));
  });

  it("总数不超过一页时不显示分页控件", async () => {
    api.listGames.mockResolvedValue({ items: games, total: 3, page: 1, page_size: 20 });
    const wrapper = mountView();
    await flushPromises();

    expect(wrapper.find('[data-test="page-info"]').exists()).toBe(false);
  });

  it("点击删除调用 store.remove 并移除行", async () => {
    const wrapper = mountView();
    await flushPromises();

    vi.spyOn(window, "confirm").mockReturnValue(true);
    await wrapper.findAll("tbody tr")[0].find("button").trigger("click");
    await flushPromises();

    expect(api.deleteGame).toHaveBeenCalledWith(1);
    expect(wrapper.findAll("tbody tr")).toHaveLength(2);
    expect(wrapper.text()).not.toContain("中炮对屏风马");
  });

  it("确认框取消时不调用删除接口", async () => {
    const wrapper = mountView();
    await flushPromises();

    vi.spyOn(window, "confirm").mockReturnValue(false);
    await wrapper.findAll("tbody tr")[0].find("button").trigger("click");
    await flushPromises();

    expect(api.deleteGame).not.toHaveBeenCalled();
    expect(wrapper.findAll("tbody tr")).toHaveLength(3);
  });

  it("确认删除后刷新统计", async () => {
    const wrapper = mountView();
    await flushPromises();

    api.stats.mockClear();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    await wrapper.findAll("tbody tr")[0].find("button").trigger("click");
    await flushPromises();

    expect(api.deleteGame).toHaveBeenCalledWith(1);
    expect(api.stats).toHaveBeenCalled();
  });

  it("删除失败时行仍保留", async () => {
    const wrapper = mountView();
    await flushPromises();

    api.deleteGame.mockRejectedValue(new Error("boom"));
    vi.spyOn(window, "confirm").mockReturnValue(true);
    await wrapper.findAll("tbody tr")[0].find("button").trigger("click");
    await flushPromises();

    expect(wrapper.findAll("tbody tr")).toHaveLength(3);
    expect(wrapper.text()).toContain("中炮对屏风马");
  });

  it("加载中显示加载态文案", async () => {
    const wrapper = mountView();
    await flushPromises();

    const store = useLibraryStore();
    store.loading = true;
    await nextTick();

    expect(wrapper.text()).toContain("加载中…");
  });
});
