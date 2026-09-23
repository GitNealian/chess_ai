import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPlaySession } from "../play";
import { api } from "../../api";
import { INITIAL_FEN } from "../../utils/chess";

vi.mock("../../api", () => ({
  api: { validateMove: vi.fn() },
}));

function legalResponse(overrides = {}) {
  return {
    legal: true,
    fen: INITIAL_FEN,
    side_to_move: "black",
    chinese: "炮八平五",
    check: false,
    game_over: null,
    ...overrides,
  };
}

describe("createPlaySession", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("空白开局为红方走棋、32 子", () => {
    const session = createPlaySession({});
    expect(session.state.initialFen).toBe(INITIAL_FEN);
    expect(session.state.pieces).toHaveLength(32);
    expect(session.state.sideToMove).toBe("red");
  });

  it("选中己方棋子与切换选中", async () => {
    const session = createPlaySession({});
    await session.click(1, 2);
    expect(session.state.selected).toEqual({ x: 1, y: 2 });
    await session.click(1, 2);
    expect(session.state.selected).toBeNull();
  });

  it("点击目标格提交校验，合法则走子并记录中文记谱", async () => {
    api.validateMove.mockResolvedValue(legalResponse());
    const session = createPlaySession({});
    await session.click(1, 2);
    const ok = await session.click(4, 2);
    expect(ok).toBe(true);
    expect(api.validateMove).toHaveBeenCalledWith({
      initial_fen: INITIAL_FEN,
      moves: [],
      move: { x1: 1, y1: 2, x2: 4, y2: 2 },
    });
    expect(session.state.moves).toEqual([
      { x1: 1, y1: 2, x2: 4, y2: 2, chinese: "炮八平五", check: false, gameOver: null },
    ]);
    expect(session.state.sideToMove).toBe("black");
    expect(session.state.selected).toBeNull();
  });

  it("非法着法保留局面并给出提示", async () => {
    api.validateMove.mockResolvedValue({ legal: false, reason: "该棋子不能这样走" });
    const session = createPlaySession({});
    await session.click(1, 2);
    const ok = await session.click(1, 3);
    expect(ok).toBe(false);
    expect(session.state.moves).toHaveLength(0);
    expect(session.state.hint).toBe("该棋子不能这样走");
    expect(session.state.selected).toEqual({ x: 1, y: 2 });
  });

  it("校验请求失败时提示重试", async () => {
    api.validateMove.mockRejectedValue(new Error("network"));
    const session = createPlaySession({});
    await session.click(1, 2);
    await session.click(4, 2);
    expect(session.state.hint).toBe("校验失败，请重试");
  });

  it("后端 400 时优先显示 detail", async () => {
    api.validateMove.mockRejectedValue({
      response: { data: { error: "重放着法不合法", detail: "第 1 步不合法" } },
    });
    const session = createPlaySession({});
    await session.click(1, 2);
    await session.click(4, 2);
    expect(session.state.hint).toBe("第 1 步不合法");
  });

  it("终局后锁定不再提交", async () => {
    api.validateMove.mockResolvedValue(
      legalResponse({ game_over: { winner: "red", reason: "checkmate" } })
    );
    const session = createPlaySession({});
    await session.click(1, 2);
    await session.click(4, 2);
    expect(session.state.gameOver).toEqual({ winner: "red", reason: "checkmate" });
    await session.click(1, 9);
    expect(session.state.selected).toBeNull();
    expect(api.validateMove).toHaveBeenCalledTimes(1);
  });

  it("悔棋回退一步并恢复行棋方", async () => {
    api.validateMove.mockResolvedValue(legalResponse());
    const session = createPlaySession({});
    await session.click(1, 2);
    await session.click(4, 2);
    session.undo();
    expect(session.state.moves).toHaveLength(0);
    expect(session.state.sideToMove).toBe("red");
    expect(session.state.pieces).toHaveLength(32);
  });

  it("从棋谱续下：载入前 N 步与行棋方", () => {
    const moves = [
      { x1: 1, y1: 2, x2: 4, y2: 2 },
      { x1: 7, y1: 9, x2: 6, y2: 7 },
    ];
    const session = createPlaySession({ initial_fen: INITIAL_FEN, moves });
    expect(session.state.moves).toHaveLength(2);
    expect(session.state.sideToMove).toBe("red");
    expect(session.state.pieces).toHaveLength(32);
  });

  it("走子后棋子真的移动到目标格", async () => {
    api.validateMove.mockResolvedValue(legalResponse());
    const session = createPlaySession({});
    await session.click(1, 2);
    await session.click(4, 2);
    expect(session.state.pieces.some((p) => p.x === 4 && p.y === 2)).toBe(true);
    expect(session.state.pieces.some((p) => p.x === 1 && p.y === 2)).toBe(false);
  });

  it("黑先局面由 initial_fen 推导行棋方", () => {
    const blackFirst = INITIAL_FEN.replace(" w ", " b ");
    const session = createPlaySession({ initial_fen: blackFirst });
    expect(session.state.sideToMove).toBe("black");
    expect(session.state.pieces).toHaveLength(32);
  });

  it("续下奇数步时为黑方走棋", () => {
    const moves = [{ x1: 1, y1: 2, x2: 4, y2: 2 }];
    const session = createPlaySession({ initial_fen: INITIAL_FEN, moves });
    expect(session.state.sideToMove).toBe("black");
  });

  it("payload 会剥离 chinese/check/gameOver 字段", async () => {
    api.validateMove.mockResolvedValue(legalResponse());
    const moves = [
      { x1: 1, y1: 2, x2: 4, y2: 2, chinese: "炮八平五", check: false, gameOver: null },
    ];
    const session = createPlaySession({ initial_fen: INITIAL_FEN, moves });
    await session.click(7, 9);
    await session.click(6, 7);
    const payload = api.validateMove.mock.calls[0][0];
    expect(payload.moves).toEqual([{ x1: 1, y1: 2, x2: 4, y2: 2 }]);
  });

  it("悔棋恢复上一层的将军与终局状态", async () => {
    api.validateMove
      .mockResolvedValueOnce(legalResponse({ check: true }))
      .mockResolvedValueOnce(
        legalResponse({ check: false, game_over: { winner: "red", reason: "checkmate" } })
      );
    const session = createPlaySession({});
    await session.click(1, 2);
    await session.click(4, 2);
    expect(session.state.check).toBe(true);
    expect(session.state.gameOver).toBeNull();

    await session.click(7, 9);
    await session.click(6, 7);
    expect(session.state.gameOver).toEqual({ winner: "red", reason: "checkmate" });

    session.undo();
    expect(session.state.gameOver).toBeNull();
    expect(session.state.check).toBe(true);
  });

  it("终局后仍可悔棋解除锁定并继续", async () => {
    api.validateMove.mockResolvedValue(
      legalResponse({ game_over: { winner: "red", reason: "checkmate" } })
    );
    const session = createPlaySession({});
    await session.click(1, 2);
    await session.click(4, 2);
    expect(session.state.gameOver).not.toBeNull();
    await session.click(7, 9);
    expect(session.state.selected).toBeNull();

    session.undo();
    await session.click(7, 2);
    expect(session.state.selected).toEqual({ x: 7, y: 2 });
  });

  it("提交飞行中重复点击只发一次请求", async () => {
    let resolve;
    api.validateMove.mockImplementation(
      () => new Promise((r) => { resolve = r; })
    );
    const session = createPlaySession({});
    await session.click(1, 2);
    const first = session.click(4, 2);
    const second = session.click(4, 2);
    resolve(legalResponse());
    await first;
    await second;
    expect(api.validateMove).toHaveBeenCalledTimes(1);
    expect(session.state.moves).toHaveLength(1);
  });

  it("提交飞行中悔棋会丢弃过期响应", async () => {
    api.validateMove.mockResolvedValueOnce(legalResponse());
    const session = createPlaySession({});
    await session.click(1, 2);
    await session.click(4, 2);
    expect(session.state.moves).toHaveLength(1);

    let resolve;
    api.validateMove.mockImplementation(
      () => new Promise((r) => { resolve = r; })
    );
    await session.click(7, 9);
    const pending = session.click(6, 7);
    session.undo();
    resolve(legalResponse({ chinese: "马8进7" }));
    await pending;
    expect(session.state.moves).toHaveLength(0);
  });

  it("applyState 标注末步状态且悔棋后回退", () => {
    const moves = [{ x1: 1, y1: 2, x2: 4, y2: 2 }];
    const session = createPlaySession({ initial_fen: INITIAL_FEN, moves });
    session.applyState({ check: true, gameOver: null });
    expect(session.state.check).toBe(true);
    expect(session.state.gameOver).toBeNull();
    expect(session.state.moves[0].check).toBe(true);
    expect(session.state.moves[0].gameOver).toBeNull();

    session.undo();
    expect(session.state.check).toBe(false);
    expect(session.state.gameOver).toBeNull();
  });

  it("切换选中时清除非法提示", async () => {
    api.validateMove.mockResolvedValue({ legal: false, reason: "该棋子不能这样走" });
    const session = createPlaySession({});
    await session.click(1, 2);
    await session.click(1, 3);
    expect(session.state.hint).toBe("该棋子不能这样走");
    await session.click(0, 0);
    expect(session.state.hint).toBe("");
  });
});

describe("applyEngineMove", () => {
  it("直接追加引擎着法并重建局面", () => {
    const session = createPlaySession({});
    session.applyEngineMove({
      x1: 1,
      y1: 2,
      x2: 4,
      y2: 2,
      chinese: "炮二平五",
      check: false,
      game_over: null,
    });
    expect(session.state.moves).toHaveLength(1);
    expect(session.state.moves[0].chinese).toBe("炮二平五");
    expect(session.state.sideToMove).toBe("black");
  });

  it("记录终局快照", () => {
    const session = createPlaySession({});
    session.applyEngineMove({
      x1: 1,
      y1: 2,
      x2: 4,
      y2: 2,
      chinese: "炮二平五",
      check: true,
      game_over: { winner: "red", reason: "checkmate" },
    });
    expect(session.state.gameOver).toEqual({ winner: "red", reason: "checkmate" });
  });
});

describe("reset generation", () => {
  it("提交中 reset 后迟到响应不写入着法", async () => {
    let resolveMove;
    api.validateMove.mockReturnValue(new Promise((r) => { resolveMove = r; }));
    const session = createPlaySession({});
    await session.click(1, 2);
    const pending = session.click(4, 2);
    session.reset({});
    resolveMove({
      legal: true,
      fen: INITIAL_FEN,
      side_to_move: "black",
      chinese: "炮二平五",
      check: false,
      game_over: null,
    });
    const result = await pending;
    expect(result).toBe(false);
    expect(session.state.moves).toHaveLength(0);
  });
});
