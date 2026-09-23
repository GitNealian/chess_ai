import { reactive } from "vue";
import { api } from "../api";
import { INITIAL_FEN, applyMove, fenToPieces } from "../utils/chess";

export function opposite(side) {
  return side === "red" ? "black" : "red";
}

function sideFromFen(fen) {
  return fen.split(" ")[1] === "b" ? "black" : "red";
}

export function createPlaySession({ initial_fen: initialFen, moves: initialMoves } = {}) {
  const state = reactive({
    initialFen: initialFen || INITIAL_FEN,
    moves: [],
    pieces: [],
    selected: null,
    sideToMove: "red",
    hint: "",
    check: false,
    gameOver: null,
  });
  let firstSide = "red";
  let pending = false;
  let generation = 0;

  function rebuild() {
    let board = fenToPieces(state.initialFen);
    for (const move of state.moves) board = applyMove(board, move);
    state.pieces = board;
    state.sideToMove = state.moves.length % 2 === 0 ? firstSide : opposite(firstSide);
    const last = state.moves[state.moves.length - 1];
    state.check = Boolean(last?.check);
    state.gameOver = last?.gameOver || null;
  }

  // 无参调用回到标准开局；载入棋谱时不带 check/gameOver 快照
  function reset({ initial_fen, moves } = {}) {
    generation += 1;
    pending = false;
    state.initialFen = initial_fen || INITIAL_FEN;
    firstSide = sideFromFen(state.initialFen);
    state.moves = (moves || []).map((move) => ({ ...move }));
    state.selected = null;
    state.hint = "";
    state.check = false;
    state.gameOver = null;
    rebuild();
  }

  async function submit(move) {
    state.hint = "";
    const snapshot = state.moves.length;
    const gen = generation;
    pending = true;
    let data;
    try {
      data = await api.validateMove({
        initial_fen: state.initialFen,
        moves: state.moves.map(({ chinese, check, gameOver, ...rest }) => rest),
        move,
      });
    } catch (err) {
      if (generation === gen && state.moves.length === snapshot) {
        state.hint =
          err?.response?.data?.detail || err?.response?.data?.error || "校验失败，请重试";
      }
      return false;
    } finally {
      pending = false;
    }
    if (generation !== gen) return false;
    if (state.moves.length !== snapshot) return false;
    if (!data.legal) {
      state.hint = data.reason || "着法不合法";
      return false;
    }
    state.moves.push({
      ...move,
      chinese: data.chinese || "",
      check: Boolean(data.check),
      gameOver: data.game_over || null,
    });
    state.selected = null;
    rebuild();
    return true;
  }

  async function click(x, y) {
    if (pending || state.gameOver) return false;
    const piece = state.pieces.find((item) => item.x === x && item.y === y);
    if (state.selected) {
      if (piece && piece.side === state.sideToMove) {
        state.hint = "";
        const same = state.selected.x === x && state.selected.y === y;
        state.selected = same ? null : { x, y };
        return false;
      }
      const from = state.selected;
      return submit({ x1: from.x, y1: from.y, x2: x, y2: y });
    }
    if (piece && piece.side === state.sideToMove) {
      state.selected = { x, y };
    }
    return false;
  }

  function undo() {
    if (!state.moves.length) return;
    state.moves.pop();
    state.selected = null;
    state.hint = "";
    rebuild();
  }

  function applyState({ check = false, gameOver = null } = {}) {
    const last = state.moves[state.moves.length - 1];
    if (last) {
      last.check = Boolean(check);
      last.gameOver = gameOver || null;
    }
    state.check = Boolean(check);
    state.gameOver = gameOver || null;
  }

  // 引擎着法由后端 best-move 保证合法，直接应用并重建（不再调 validate-move）
  function applyEngineMove(move) {
    state.moves.push({
      x1: move.x1,
      y1: move.y1,
      x2: move.x2,
      y2: move.y2,
      chinese: move.chinese || "",
      check: Boolean(move.check),
      gameOver: move.game_over || null,
    });
    state.selected = null;
    state.hint = "";
    rebuild();
  }

  reset({ initial_fen: initialFen, moves: initialMoves });

  return { state, click, undo, reset, applyState, applyEngineMove };
}
