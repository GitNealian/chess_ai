import { describe, expect, it } from "vitest";
import { createPracticeSession } from "../practice";

const bothGame = {
  id: 1,
  initial_fen: "4k4/9/9/9/9/9/9/9/9/4K4 w - - 0 1",
  practice_side: "both",
  moves: [{ x1: 4, y1: 0, x2: 4, y2: 1 }],
};

describe("practice session", () => {
  it("走对前进", () => {
    const session = createPracticeSession(bothGame);
    session.submitMove({ x1: 4, y1: 0, x2: 4, y2: 1 });
    expect(session.state.ply).toBe(1);
    expect(session.state.mistakes).toBe(0);
    expect(session.isFinished()).toBe(true);
  });

  it("走错计错不前进", () => {
    const session = createPracticeSession(bothGame);
    session.submitMove({ x1: 4, y1: 0, x2: 3, y2: 0 });
    expect(session.state.ply).toBe(0);
    expect(session.state.mistakes).toBe(1);
  });

  it("看答案计为揭示并前进", () => {
    const session = createPracticeSession(bothGame);
    session.reveal();
    expect(session.state.ply).toBe(1);
    expect(session.state.revealed).toBe(true);
  });

  it("practice_side=red 自动跳过黑方着法", () => {
    const game = {
      id: 2,
      initial_fen: "4k4/9/9/9/9/9/9/9/9/4K4 w - - 0 1",
      practice_side: "red",
      moves: [
        { x1: 4, y1: 0, x2: 4, y2: 1 }, // 红
        { x1: 4, y1: 9, x2: 4, y2: 8 }, // 黑（应自动）
      ],
    };
    const session = createPracticeSession(game);
    expect(session.state.expected).toEqual({ x1: 4, y1: 0, x2: 4, y2: 1 });
    session.submitMove({ x1: 4, y1: 0, x2: 4, y2: 1 });
    // 红方走完，黑方自动走，会话结束
    expect(session.state.ply).toBe(2);
    expect(session.isFinished()).toBe(true);
  });

  it("practice_side=black 自动跳过红方着法，expected 为黑方着法", () => {
    const game = {
      id: 3,
      initial_fen: "4k4/9/9/9/9/9/9/9/9/4K4 w - - 0 1",
      practice_side: "black",
      moves: [
        { x1: 4, y1: 0, x2: 4, y2: 1 }, // 红（自动）
        { x1: 4, y1: 9, x2: 4, y2: 8 }, // 黑
      ],
    };
    const session = createPracticeSession(game);
    expect(session.state.ply).toBe(1);
    expect(session.state.expected).toEqual({ x1: 4, y1: 9, x2: 4, y2: 8 });
  });
});
