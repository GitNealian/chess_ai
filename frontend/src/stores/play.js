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

  function rebuild() {
    let board = fenToPieces(state.initialFen);
    for (const move of state.moves) board = applyMove(board, move);
    state.pieces = board;
    state.sideToMove = state.moves.length % 2 === 0 ? firstSide : opposite(firstSide);
  }

  function reset({ initial_fen, moves } = {}) {
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
    let data;
    try {
      data = await api.validateMove({
        initial_fen: state.initialFen,
        moves: state.moves.map(({ chinese, ...rest }) => rest),
        move,
      });
    } catch (err) {
      state.hint =
        err?.response?.data?.detail || err?.response?.data?.error || "校验失败，请重试";
      return false;
    }
    if (!data.legal) {
      state.hint = data.reason || "着法不合法";
      return false;
    }
    state.moves.push({ ...move, chinese: data.chinese || "" });
    state.selected = null;
    state.check = Boolean(data.check);
    state.gameOver = data.game_over || null;
    rebuild();
    return true;
  }

  async function click(x, y) {
    if (state.gameOver) return false;
    const piece = state.pieces.find((item) => item.x === x && item.y === y);
    if (state.selected) {
      if (piece && piece.side === state.sideToMove) {
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
    state.check = false;
    state.gameOver = null;
    rebuild();
  }

  reset({ initial_fen: initialFen, moves: initialMoves });

  return { state, click, undo, reset };
}
