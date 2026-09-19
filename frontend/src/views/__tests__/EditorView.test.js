import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { nextTick } from "vue";
import EditorView from "../EditorView.vue";
import { api } from "../../api";

const { push, route } = vi.hoisted(() => ({ push: vi.fn(), route: { params: {} } }));

vi.mock("../../api", () => ({
  api: {
    getGame: vi.fn(),
    createGame: vi.fn(),
    updateGame: vi.fn(),
    parse: vi.fn(),
    importPgn: vi.fn(),
  },
}));

vi.mock("vue-router", () => ({
  useRoute: () => route,
  useRouter: () => ({ push }),
}));

const BoardStub = {
  name: "ChessBoard",
  props: ["position", "selected", "legalTargets"],
  emits: ["cell-click"],
  template: '<div class="board-stub" />',
};

function mountView() {
  return mount(EditorView, {
    global: { stubs: { ChessBoard: BoardStub } },
  });
}

function boardPieces(wrapper) {
  return wrapper.findComponent(BoardStub).props("position").pieces;
}

function buttonByText(wrapper, text) {
  return wrapper.findAll("button").find((btn) => btn.text() === text);
}

async function clickCell(wrapper, x, y) {
  wrapper.findComponent(BoardStub).vm.$emit("cell-click", x, y);
  await nextTick();
}

describe("EditorView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    route.params = {};
    api.createGame.mockResolvedValue({ id: 1 });
    api.updateGame.mockResolvedValue({ id: 1 });
    api.parse.mockResolvedValue({ moves: [] });
    api.importPgn.mockResolvedValue({ created: 1 });
    api.getGame.mockResolvedValue({
      id: 1,
      name: "测试棋谱",
      moves: [],
      initial_fen: "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1",
    });
    vi.spyOn(window, "alert").mockImplementation(() => {});
  });

  it("挂载后棋盘为初始 32 子", () => {
    const wrapper = mountView();
    expect(boardPieces(wrapper)).toHaveLength(32);
    expect(wrapper.text()).toContain("新建棋谱");
  });

  it("点击两个格子后着法增加并显示坐标", async () => {
    const wrapper = mountView();
    await clickCell(wrapper, 0, 9);
    await clickCell(wrapper, 0, 8);

    expect(wrapper.findAll(".moves li")).toHaveLength(1);
    expect(wrapper.find(".moves").text()).toContain("(0,9)→(0,8)");
  });

  it("悔棋后着法减少且被吃棋子恢复", async () => {
    const wrapper = mountView();
    await clickCell(wrapper, 1, 7);
    await clickCell(wrapper, 0, 3);

    expect(boardPieces(wrapper)).toHaveLength(31);
    expect(wrapper.findAll(".moves li")).toHaveLength(1);

    await buttonByText(wrapper, "悔棋").trigger("click");
    await nextTick();

    expect(boardPieces(wrapper)).toHaveLength(32);
    expect(wrapper.findAll(".moves li")).toHaveLength(0);
  });

  it("解析预览成功后 moves 与棋盘同步", async () => {
    api.parse.mockResolvedValue({
      moves: [
        { x1: 0, y1: 9, x2: 0, y2: 8 },
        { x1: 0, y1: 8, x2: 0, y2: 7 },
      ],
    });
    const wrapper = mountView();
    await wrapper.find("textarea").setValue("车九进一 车九进一");
    await buttonByText(wrapper, "解析预览").trigger("click");
    await flushPromises();

    expect(api.parse).toHaveBeenCalledWith({
      text: "车九进一 车九进一",
      initial_fen: expect.any(String),
    });
    expect(wrapper.findAll(".moves li")).toHaveLength(2);
  });

  it("保存时调用 createGame 并携带 moves，成功后跳转 /library", async () => {
    const wrapper = mountView();
    await wrapper.find(".form-area input").setValue("我的棋谱");
    await clickCell(wrapper, 0, 9);
    await clickCell(wrapper, 0, 8);
    await wrapper.find("button.save").trigger("click");
    await flushPromises();

    expect(api.createGame).toHaveBeenCalledTimes(1);
    const payload = api.createGame.mock.calls[0][0];
    expect(payload.name).toBe("我的棋谱");
    expect(payload.moves).toHaveLength(1);
    expect(push).toHaveBeenCalledWith("/library");
  });

  it("名称为空时保存不调用接口", async () => {
    const wrapper = mountView();
    await wrapper.find("button.save").trigger("click");
    await flushPromises();

    expect(api.createGame).not.toHaveBeenCalled();
    expect(window.alert).toHaveBeenCalledWith("请填写棋谱名称");
    expect(push).not.toHaveBeenCalled();
  });

  it("编辑模式加载棋谱并回放棋盘", async () => {
    route.params = { id: "7" };
    api.getGame.mockResolvedValue({
      id: 7,
      name: "已存棋谱",
      category: "开局",
      practice_side: "red",
      initial_fen: "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1",
      moves: [
        { x1: 1, y: 7, x2: 4, y: 7 },
        { x1: 7, y: 2, x2: 4, y: 2 },
      ],
    });

    const wrapper = mountView();
    await flushPromises();

    expect(api.getGame).toHaveBeenCalledWith(7);
    expect(wrapper.text()).toContain("编辑棋谱");
    expect(wrapper.find(".form-area input").element.value).toBe("已存棋谱");
    expect(wrapper.findAll(".moves li")).toHaveLength(2);
    expect(boardPieces(wrapper)).toHaveLength(32);
  });
});
