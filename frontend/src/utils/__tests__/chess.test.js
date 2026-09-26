import { describe, expect, it } from "vitest";
import { applyMove, fenToPieces, LABELS, MAX_COUNTS } from "../chess";

describe("chess utils", () => {
  it("标准开局有 32 个棋子", () => {
    const pieces = fenToPieces("rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1");
    expect(pieces).toHaveLength(32);
  });

  it("红帅标签正确", () => {
    const pieces = fenToPieces("4k4/9/9/9/9/9/9/9/9/4K4 w - - 0 1");
    const redKing = pieces.find((p) => p.side === "red");
    expect(redKing.label).toBe("帅");
  });

  it("applyMove 移动棋子", () => {
    const pieces = fenToPieces("4k4/9/9/9/9/9/9/9/9/4K4 w - - 0 1");
    const next = applyMove(pieces, { x1: 4, y1: 0, x2: 4, y2: 1 });
    expect(next.find((p) => p.x === 4 && p.y === 1).kind).toBe("K");
  });

  it("applyMove 吃子移除目标棋子", () => {
    const pieces = [
      { x: 0, y: 0, side: "red", kind: "R", label: "车" },
      { x: 0, y: 5, side: "black", kind: "P", label: "卒" },
    ];
    const next = applyMove(pieces, { x1: 0, y1: 0, x2: 0, y2: 5 });
    expect(next).toHaveLength(1);
    expect(next[0].side).toBe("red");
    expect(next[0].y).toBe(5);
  });

  it("FEN 坐标映射正确", () => {
    const pieces = fenToPieces("4k4/9/9/9/9/9/9/9/9/4K4 w - - 0 1");
    const blackKing = pieces.find((p) => p.side === "black");
    expect(blackKing.x).toBe(4);
    expect(blackKing.y).toBe(9);
  });

  it("LABELS 覆盖全部 14 种棋子且标签非空", () => {
    const expected = [
      "red-K", "red-A", "red-B", "red-N", "red-R", "red-C", "red-P",
      "black-K", "black-A", "black-B", "black-N", "black-R", "black-C", "black-P",
    ];
    expect(Object.keys(LABELS).sort()).toEqual([...expected].sort());
    for (const key of expected) {
      expect(LABELS[key]).toBeTruthy();
    }
  });

  it("空棋盘 FEN 返回空数组", () => {
    const pieces = fenToPieces("9/9/9/9/9/9/9/9/9/9 w - - 0 1");
    expect(pieces).toEqual([]);
  });

  it("applyMove 起点无棋子时返回原数组且目标子仍在", () => {
    const pieces = [
      { x: 0, y: 5, side: "black", kind: "P", label: "卒" },
    ];
    const next = applyMove(pieces, { x1: 0, y1: 0, x2: 0, y2: 5 });
    expect(next).toBe(pieces);
    expect(next).toHaveLength(1);
    expect(next[0].side).toBe("black");
  });

  it("applyMove 不修改入参（纯函数）", () => {
    const pieces = [
      { x: 0, y: 0, side: "red", kind: "R", label: "车" },
      { x: 0, y: 5, side: "black", kind: "P", label: "卒" },
    ];
    const snapshot = JSON.stringify(pieces);
    applyMove(pieces, { x1: 0, y1: 0, x2: 0, y2: 5 });
    expect(JSON.stringify(pieces)).toBe(snapshot);
  });
});

describe("MAX_COUNTS", () => {
  it("按象棋规则给出各兵种上限", () => {
    expect(MAX_COUNTS).toEqual({ K: 1, A: 2, B: 2, N: 2, R: 2, C: 2, P: 5 });
  });
});
