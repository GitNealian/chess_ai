import { reactive } from "vue";
import { applyMove, fenToPieces } from "../utils/chess";

function sameMove(a, b) {
  return a.x1 === b.x1 && a.y1 === b.y1 && a.x2 === b.x2 && a.y2 === b.y2;
}

function isPracticeTurn(ply, practiceSide) {
  if (practiceSide === "both") return true;
  const isRedTurn = ply % 2 === 0;
  if (practiceSide === "red") return isRedTurn;
  if (practiceSide === "black") return !isRedTurn;
  return true;
}

export function createPracticeSession(game) {
  const practiceSide = game.practice_side || "both";
  const state = reactive({
    ply: 0,
    mistakes: 0,
    revealed: false,
    pieces: fenToPieces(game.initial_fen),
    expected: null,
  });

  function syncExpected() {
    state.expected = state.ply < game.moves.length ? game.moves[state.ply] : null;
  }

  function advance() {
    if (state.ply >= game.moves.length) return;
    const move = game.moves[state.ply];
    state.pieces = applyMove(state.pieces, move);
    state.ply += 1;
  }

  function advanceAuto() {
    while (state.ply < game.moves.length && !isPracticeTurn(state.ply, practiceSide)) {
      advance();
    }
    syncExpected();
  }

  advanceAuto();

  return {
    game,
    state,
    submitMove(move) {
      const expected = game.moves[state.ply];
      if (!expected) return false;
      if (sameMove(move, expected)) {
        advance();
        advanceAuto();
        return true;
      }
      state.mistakes += 1;
      return false;
    },
    reveal() {
      if (state.ply >= game.moves.length) return;
      state.revealed = true;
      advance();
      advanceAuto();
    },
    isFinished() {
      return state.ply >= game.moves.length;
    },
  };
}
