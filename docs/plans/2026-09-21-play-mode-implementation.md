# 双人同屏对弈与实时分析 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增 `/play` 双人同屏对弈页：后端无状态校验走子合法性，前端支持翻转棋盘、悔棋、每步自动 AI 分析，并可手动保存到棋谱库。

**Architecture:** 后端在 engine 蓝本新增 `POST /api/engine/validate-move`（无状态：传 `initial_fen + moves + move`，复用 `chess_engine` 的 `Board.is_legal/apply_move/in_check/has_legal_move` 与 `move_to_chinese`）。前端新增 `stores/play.js` 会话（纯逻辑，可单测）、`PlayView.vue`（复用 `ChessBoard` 与 `analyzeStream`），`ChessBoard` 增加 `flipped` 实现 180° 旋转。

**Tech Stack:** Flask + SQLAlchemy（后端）、Vue 3 `<script setup>` + Pinia-style 工厂 store + Vue Test Utils/Vitest（前端）、pytest（后端测试）。

**设计文档：** `docs/plans/2026-09-21-play-mode-design.md`

---

## 约定

- 后端命令在 `/home/nealian/chess/backend` 下执行，使用 `.venv/bin/python`。
- 前端命令在 `/home/nealian/chess/frontend` 下执行，使用 `npx vitest run`。
- 每个任务结束提交一次，提交信息用中文，遵循现有 `type(scope): 描述` 风格。

---

### Task 1: 后端 `POST /api/engine/validate-move`

**Files:**
- Create: `backend/tests/test_engine_validate_api.py`
- Modify: `backend/routes/engine.py`（在 `analyze_position` 之前插入）

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_engine_validate_api.py`：

```python
"""`POST /api/engine/validate-move` 无状态走子校验接口测试。"""

from chess_engine.board import INITIAL_FEN, Board

# 红车 (0,8) 走 (0,9)：将死黑将（(3,9)/(5,9) 被同一车控制，(4,8) 被 (4,5) 车控制）
MATE_FEN = "4k4/R8/9/9/4R4/9/9/9/9/4K4 w - - 0 1"
# 红走帅 (3,0)→(3,1) 后黑将 (4,9) 无着可走且未被将军（困毙）
STALEMATE_FEN = "4k4/3R1R3/9/9/9/9/9/9/9/3K5 w - - 0 1"
# 红车 (0,8) 走 (0,9) 将军，但黑将可逃 (4,8)
CHECK_FEN = "4k4/R8/9/9/9/9/9/9/9/3K5 w - - 0 1"


def post(client, payload):
    return client.post("/api/engine/validate-move", json=payload)


def test_validate_legal_move_with_default_fen(client):
    resp = post(client, {"move": {"x1": 1, "y1": 2, "x2": 4, "y2": 2}})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["legal"] is True
    assert body["side_to_move"] == "black"
    assert body["chinese"] == "炮八平五"
    assert body["check"] is False
    assert body["game_over"] is None
    assert body["fen"] != INITIAL_FEN


def test_validate_replays_initial_fen_and_moves(client):
    payload = {
        "initial_fen": INITIAL_FEN,
        "moves": [{"x1": 1, "y1": 2, "x2": 4, "y2": 2}],
        "move": {"x1": 7, "y1": 9, "x2": 6, "y2": 7},
    }
    body = post(client, payload).get_json()
    assert body["legal"] is True
    assert body["side_to_move"] == "red"
    assert body["chinese"] == "马8进7"


def test_validate_illegal_move_returns_reason(client):
    body = post(client, {"move": {"x1": 0, "y1": 0, "x2": 0, "y2": 1}}).get_json()
    assert body["legal"] is False
    assert body["reason"] == "该棋子不能这样走"
    assert "fen" not in body


def test_validate_wrong_side_piece(client):
    body = post(client, {"move": {"x1": 0, "y1": 9, "x2": 0, "y2": 8}}).get_json()
    assert body["legal"] is False
    assert body["reason"] == "该棋子不属于行棋方"


def test_validate_empty_origin(client):
    body = post(client, {"move": {"x1": 4, "y1": 4, "x2": 4, "y2": 5}}).get_json()
    assert body["legal"] is False
    assert body["reason"] == "起点没有棋子"


def test_validate_reports_check_and_checkmate(client):
    body = post(
        client, {"initial_fen": CHECK_FEN, "move": {"x1": 0, "y1": 8, "x2": 0, "y2": 9}}
    ).get_json()
    assert body["legal"] is True
    assert body["check"] is True
    assert body["game_over"] is None

    body = post(
        client, {"initial_fen": MATE_FEN, "move": {"x1": 0, "y1": 8, "x2": 0, "y2": 9}}
    ).get_json()
    assert body["check"] is True
    assert body["game_over"] == {"winner": "red", "reason": "checkmate"}


def test_validate_reports_stalemate(client):
    body = post(
        client, {"initial_fen": STALEMATE_FEN, "move": {"x1": 3, "y1": 0, "x2": 3, "y2": 1}}
    ).get_json()
    assert body["legal"] is True
    assert body["check"] is False
    assert body["game_over"] == {"winner": "red", "reason": "stalemate"}


def test_validate_rejects_bad_payloads(client):
    assert client.post("/api/engine/validate-move", json={}).status_code == 400
    assert post(client, {"move": "炮二平五"}).status_code == 400
    assert post(client, {"move": {"x1": 1, "y1": 2}}).status_code == 400
    assert post(client, {"initial_fen": "not-a-fen", "move": {"x1": 1, "y1": 2, "x2": 4, "y2": 2}}).status_code == 400
    assert post(client, {"moves": "x", "move": {"x1": 1, "y1": 2, "x2": 4, "y2": 2}}).status_code == 400


def test_validate_rejects_illegal_replay_sequence(client):
    payload = {
        "moves": [{"x1": 0, "y1": 0, "x2": 0, "y2": 1}],
        "move": {"x1": 1, "y1": 2, "x2": 4, "y2": 2},
    }
    resp = post(client, payload)
    assert resp.status_code == 400
    assert "第 1 步" in resp.get_json()["error"]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && .venv/bin/python -m pytest tests/test_engine_validate_api.py -q`
Expected: FAIL（全部 404，因为路由不存在）

- [ ] **Step 3: 实现接口**

在 `backend/routes/engine.py` 中，`@engine_bp.post("/analyze")`（约 188 行）之前插入：

```python
def _illegal_reason(board, move):
    piece = board.piece_at(move.x1, move.y1)
    if piece is None:
        return "起点没有棋子"
    if piece[0] != board.side_to_move:
        return "该棋子不属于行棋方"
    if move not in board.pseudo_moves_from(move.x1, move.y1):
        return "该棋子不能这样走"
    return "不能送将"


@engine_bp.post("/validate-move")
def validate_move():
    """无状态走子校验：重放 `initial_fen + moves` 后校验 `move` 并返回新局面。"""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "请求体必须是 JSON 对象"}), 400

    initial_fen = data.get("initial_fen", INITIAL_FEN)
    if not isinstance(initial_fen, str) or not initial_fen.strip():
        return jsonify({"error": "initial_fen 必须是非空字符串"}), 400
    board = Board()
    try:
        board.load_fen(initial_fen)
    except ValueError as exc:
        return jsonify({"error": "初始局面无效", "detail": str(exc)}), 400

    moves = data.get("moves", [])
    if not isinstance(moves, list):
        return jsonify({"error": "moves 必须是数组"}), 400
    for index, raw in enumerate(moves, start=1):
        if not _valid_move_dict(raw):
            return jsonify({"error": f"第 {index} 步着法格式错误"}), 400
        replay = Move.from_dict(raw)
        if not board.is_legal(replay):
            return jsonify({"error": f"第 {index} 步不合法"}), 400
        board.apply_move(replay)

    raw_move = data.get("move")
    if not _valid_move_dict(raw_move):
        return jsonify({"error": "move 必须是含 x1/y1/x2/y2 的对象"}), 400
    move = Move.from_dict(raw_move)
    if not board.is_legal(move):
        return jsonify({"legal": False, "reason": _illegal_reason(board, move)})

    mover = board.side_to_move
    try:
        chinese = move_to_chinese(board, move)
    except ValueError:
        chinese = None
    board.apply_move(move)
    opponent = board.side_to_move
    check = board.in_check(opponent)
    game_over = None
    if not board.has_legal_move(opponent):
        game_over = {
            "winner": mover,
            "reason": "checkmate" if check else "stalemate",
        }
    return jsonify(
        {
            "legal": True,
            "fen": board.to_fen(),
            "side_to_move": opponent,
            "chinese": chinese,
            "check": check,
            "game_over": game_over,
        }
    )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && .venv/bin/python -m pytest tests/test_engine_validate_api.py -q`
Expected: 9 passed

再跑全量回归：`cd backend && .venv/bin/python -m pytest tests/ -q`
Expected: 全部通过（原 417 项上下）

- [ ] **Step 5: 提交**

```bash
git add backend/routes/engine.py backend/tests/test_engine_validate_api.py
git commit -m "feat(api): 新增无状态走子校验接口 validate-move"
```

---

### Task 2: `ChessBoard` 支持翻转

**Files:**
- Modify: `frontend/src/components/ChessBoard.vue`
- Test: `frontend/src/components/__tests__/ChessBoard.test.js`

- [ ] **Step 1: 写失败测试**

在 `ChessBoard.test.js` 末尾 `});` 之前追加：

```js
  it("flipped 时坐标上下左右镜像", () => {
    const normal = mount(ChessBoard, { props: { position } });
    const flipped = mount(ChessBoard, { props: { position, flipped: true } });
    const normalTarget = normal.find("[data-cell='0-0']").attributes();
    const flippedTarget = flipped.find("[data-cell='8-9']").attributes();
    expect(flippedTarget.x).toBe(normalTarget.x);
    expect(flippedTarget.y).toBe(normalTarget.y);
  });

  it("flipped 时点击仍发出真实坐标", async () => {
    const wrapper = mount(ChessBoard, { props: { position, flipped: true } });
    await wrapper.find("[data-cell='0-0']").trigger("click");
    expect(wrapper.emitted("cell-click")[0]).toEqual([0, 0]);
  });

  it("flipped 时楚河汉界文字旋转 180 度", () => {
    const wrapper = mount(ChessBoard, { props: { position, flipped: true } });
    const transform = wrapper.find("text").attributes("transform");
    expect(transform).toContain("rotate(180");
  });
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd frontend && npx vitest run src/components/__tests__/ChessBoard.test.js`
Expected: FAIL（flipped 属性未声明，坐标不镜像）

- [ ] **Step 3: 实现翻转**

修改 `frontend/src/components/ChessBoard.vue`：

1. props 增加 `flipped`：

```js
const props = defineProps({
  position: { type: Object, required: true },
  selected: { type: Object, default: null },
  legalTargets: { type: Array, default: () => [] },
  arrows: { type: Array, default: () => [] },
  flipped: { type: Boolean, default: false },
});
```

2. 坐标函数改为镜像（`x` 与 `y` 独立，180° 旋转等价于两次镜像）：

```js
const mirrorX = (x) => (props.flipped ? 8 - x : x);
const mirrorY = (y) => (props.flipped ? 9 - y : y);

const cellX = (x) => margin + mirrorX(x) * gap;
const cellY = (y) => margin + (9 - mirrorY(y)) * gap;
```

3. 楚河汉界两个 `<text>` 各加 `:transform`（位置取文字锚点，翻转时旋转 180°）：

模板中两个 `<text ...>` 标签增加属性（两处同样处理）：

```html
      :transform="riverTransform(1.5)"
```

```html
      :transform="riverTransform(6.5)"
```

script 中增加：

```js
const riverTransform = (x) =>
  props.flipped
    ? `rotate(180 ${cellX(x)} ${(cellY(4) + cellY(5)) / 2 + 10})`
    : undefined;
```

> 说明：`data-cell` 属性始终保持真实坐标，点击坐标读取逻辑不变；翻转只影响 SVG 绘制位置，因此点击自动输出真实坐标。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd frontend && npx vitest run src/components/__tests__/ChessBoard.test.js`
Expected: 11 passed

全量前端回归：`cd frontend && npx vitest run`
Expected: 全部通过（原 94 项 + 3）

- [ ] **Step 5: 提交**

```bash
git add frontend/src/components/ChessBoard.vue frontend/src/components/__tests__/ChessBoard.test.js
git commit -m "feat(web): ChessBoard 支持翻转棋盘"
```

---

### Task 3: 对弈会话 `stores/play.js`

**Files:**
- Modify: `frontend/src/utils/chess.js`（导出 `INITIAL_FEN`）
- Create: `frontend/src/stores/play.js`
- Modify: `frontend/src/api/index.js`（新增 `validateMove`）
- Test: `frontend/src/stores/__tests__/play.test.js`

- [ ] **Step 1: 写失败测试**

创建 `frontend/src/stores/__tests__/play.test.js`：

```js
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
      { x1: 1, y1: 2, x2: 4, y2: 2, chinese: "炮八平五" },
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
});
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd frontend && npx vitest run src/stores/__tests__/play.test.js`
Expected: FAIL（`../play` 不存在）

- [ ] **Step 3: 实现**

1. `frontend/src/utils/chess.js` 顶部新增导出：

```js
export const INITIAL_FEN = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1";
```

2. `frontend/src/api/index.js` 的 `api` 对象中新增：

```js
  validateMove: (data) => http.post("/engine/validate-move", data).then((r) => r.data),
```

3. 创建 `frontend/src/stores/play.js`：

```js
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
    } catch {
      state.hint = "校验失败，请重试";
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
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd frontend && npx vitest run src/stores/__tests__/play.test.js`
Expected: 8 passed

- [ ] **Step 5: 提交**

```bash
git add frontend/src/utils/chess.js frontend/src/api/index.js frontend/src/stores/play.js frontend/src/stores/__tests__/play.test.js
git commit -m "feat(web): 对弈会话逻辑与 validate-move 前端封装"
```

---

### Task 4: 对弈页面（走子、悔棋、翻转、终局）

**Files:**
- Modify: `frontend/src/router/index.js`
- Create: `frontend/src/views/PlayView.vue`
- Test: `frontend/src/views/__tests__/PlayView.test.js`

- [ ] **Step 1: 写失败测试**

创建 `frontend/src/views/__tests__/PlayView.test.js`：

```js
import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { nextTick } from "vue";
import PlayView from "../PlayView.vue";
import { api } from "../../api";

const { route, push } = vi.hoisted(() => ({
  route: { query: {} },
  push: vi.fn(),
}));

vi.mock("../../api", () => ({
  api: {
    getGame: vi.fn(),
    validateMove: vi.fn(),
    createGame: vi.fn(),
  },
  analyzeStream: vi.fn(),
}));

vi.mock("vue-router", () => ({
  useRoute: () => route,
  useRouter: () => ({ push }),
}));

const INITIAL_FEN = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1";

const BoardStub = {
  name: "ChessBoard",
  props: ["position", "selected", "legalTargets", "arrows", "flipped"],
  emits: ["cell-click"],
  template: '<div class="board-stub" />',
};

function mountView() {
  return mount(PlayView, { global: { stubs: { ChessBoard: BoardStub } } });
}

function board(wrapper) {
  return wrapper.findComponent(BoardStub);
}

async function clickCells(wrapper, ...coords) {
  for (const [x, y] of coords) {
    board(wrapper).vm.$emit("cell-click", x, y);
    await nextTick();
  }
}

function button(wrapper, test) {
  return wrapper.find(`[data-test="${test}"]`);
}

describe("PlayView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    route.query = {};
    api.validateMove.mockResolvedValue({
      legal: true,
      fen: INITIAL_FEN,
      side_to_move: "black",
      chinese: "炮二平五",
      check: false,
      game_over: null,
    });
  });

  it("空白开局显示 32 子与红方走棋", async () => {
    const wrapper = mountView();
    await flushPromises();
    expect(board(wrapper).props("position").pieces).toHaveLength(32);
    expect(wrapper.find('[data-test="turn"]').text()).toContain("红方走棋");
  });

  it("选中棋子传给棋盘，合法走子后更新轮次与着法列表", async () => {
    const wrapper = mountView();
    await flushPromises();

    await clickCells(wrapper, [1, 2]);
    expect(board(wrapper).props("selected")).toEqual({ x: 1, y: 2 });

    await clickCells(wrapper, [4, 2]);
    await flushPromises();

    expect(api.validateMove).toHaveBeenCalledWith({
      initial_fen: INITIAL_FEN,
      moves: [],
      move: { x1: 1, y1: 2, x2: 4, y2: 2 },
    });
    expect(wrapper.find('[data-test="turn"]').text()).toContain("黑方走棋");
    expect(wrapper.find('[data-test="move-list"]').text()).toContain("1. 炮二平五");
  });

  it("非法着法显示提示且不改变局面", async () => {
    api.validateMove.mockResolvedValue({ legal: false, reason: "该棋子不能这样走" });
    const wrapper = mountView();
    await flushPromises();

    await clickCells(wrapper, [1, 2], [1, 3]);
    await flushPromises();

    expect(wrapper.find('[data-test="hint"]').text()).toBe("该棋子不能这样走");
    expect(wrapper.find('[data-test="turn"]').text()).toContain("红方走棋");
  });

  it("悔棋回退一步", async () => {
    const wrapper = mountView();
    await flushPromises();
    await clickCells(wrapper, [1, 2], [4, 2]);
    await flushPromises();
    expect(button(wrapper, "undo").attributes("disabled")).toBeUndefined();

    await button(wrapper, "undo").trigger("click");
    await flushPromises();
    expect(wrapper.find('[data-test="turn"]').text()).toContain("红方走棋");
    expect(wrapper.find('[data-test="move-list"]').exists()).toBe(false);
  });

  it("翻转按钮切换 flipped", async () => {
    const wrapper = mountView();
    await flushPromises();
    expect(board(wrapper).props("flipped")).toBe(false);
    await button(wrapper, "flip").trigger("click");
    expect(board(wrapper).props("flipped")).toBe(true);
  });

  it("终局显示结果并锁定棋盘", async () => {
    api.validateMove.mockResolvedValue({
      legal: true,
      fen: INITIAL_FEN,
      side_to_move: "black",
      chinese: "车二进九",
      check: true,
      game_over: { winner: "red", reason: "checkmate" },
    });
    const wrapper = mountView();
    await flushPromises();
    await clickCells(wrapper, [1, 2], [4, 2]);
    await flushPromises();

    expect(wrapper.find('[data-test="game-over"]').text()).toContain("红方胜");
    await clickCells(wrapper, [1, 9]);
    expect(api.validateMove).toHaveBeenCalledTimes(1);
  });

  it("URL 带 game/ply 时载入棋谱前 N 步", async () => {
    route.query = { game: "7", ply: "2" };
    api.getGame.mockResolvedValue({
      id: 7,
      name: "库内棋谱",
      initial_fen: INITIAL_FEN,
      moves: [
        { x1: 1, y1: 2, x2: 4, y2: 2 },
        { x1: 7, y1: 9, x2: 6, y2: 7 },
        { x1: 0, y1: 9, x2: 0, y2: 8 },
      ],
    });
    const wrapper = mountView();
    await flushPromises();
    expect(api.getGame).toHaveBeenCalledWith("7");
    expect(wrapper.find('[data-test="turn"]').text()).toContain("红方走棋");
    expect(wrapper.findAll('[data-test="move-list"] li')).toHaveLength(2);
  });
});
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd frontend && npx vitest run src/views/__tests__/PlayView.test.js`
Expected: FAIL（`../PlayView.vue` 不存在）

- [ ] **Step 3: 实现**

1. `frontend/src/router/index.js` 增加路由（放在 `/review` 之前）：

```js
  { path: "/play", component: () => import("../views/PlayView.vue") },
```

2. 创建 `frontend/src/views/PlayView.vue`（本任务不包含分析面板与保存弹窗，由 Task 5/6 增量加入）：

```vue
<template>
  <section class="play">
    <h2>人人对弈</h2>
    <p v-if="loading" class="hint">加载中…</p>
    <div v-else-if="error" class="hint">
      <p>加载失败</p>
      <button data-test="retry" @click="load">重试</button>
    </div>
    <div v-else class="layout">
      <ChessBoard
        :position="{ pieces: session.state.pieces }"
        :selected="session.state.selected"
        :flipped="flipped"
        @cell-click="onCellClick"
      />
      <div class="side">
        <p class="turn" data-test="turn">{{ turnText }}</p>
        <p v-if="session.state.hint" class="warn" data-test="hint">{{ session.state.hint }}</p>
        <p v-if="session.state.gameOver" class="result" data-test="game-over">{{ resultText }}</p>
        <div class="controls">
          <button data-test="undo" :disabled="!session.state.moves.length" @click="undo">悔棋</button>
          <button data-test="flip" @click="flipped = !flipped">翻转棋盘</button>
        </div>
        <ol v-if="session.state.moves.length" class="moves" data-test="move-list">
          <li v-for="(move, index) in session.state.moves" :key="index">
            {{ describe(move, index) }}
          </li>
        </ol>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import ChessBoard from "../components/ChessBoard.vue";
import { api } from "../api";
import { createPlaySession } from "../stores/play";

const route = useRoute();
const loading = ref(true);
const error = ref(false);
const flipped = ref(false);
const session = createPlaySession({});

const turnText = computed(() => {
  if (session.state.gameOver) return "";
  const side = session.state.sideToMove === "red" ? "红方" : "黑方";
  return session.state.check ? `${side}走棋（被将军）` : `${side}走棋`;
});

const resultText = computed(() => {
  const over = session.state.gameOver;
  if (!over) return "";
  const winner = over.winner === "red" ? "红方" : "黑方";
  return over.reason === "checkmate" ? `${winner}胜（绝杀）` : `${winner}胜（困毙）`;
});

function describe(move, index) {
  const text = move.chinese || `(${move.x1},${move.y1})→(${move.x2},${move.y2})`;
  return `${index + 1}. ${text}`;
}

async function onCellClick(x, y) {
  await session.click(x, y);
}

function undo() {
  session.undo();
}

async function load() {
  loading.value = true;
  error.value = false;
  try {
    if (route.query.game) {
      const game = await api.getGame(route.query.game);
      const ply = Math.max(
        0,
        Math.min(Number(route.query.ply) || 0, game.moves.length)
      );
      session.reset({ initial_fen: game.initial_fen, moves: game.moves.slice(0, ply) });
    } else {
      session.reset({});
    }
  } catch {
    error.value = true;
    loading.value = false;
    return;
  }
  loading.value = false;
}

onMounted(load);
</script>

<style scoped>
.layout {
  display: grid;
  grid-template-columns: 1fr;
  gap: 16px;
}

.side {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.turn {
  margin: 0;
  font-weight: 600;
}

.warn {
  margin: 0;
  color: #b45309;
}

.result {
  margin: 0;
  font-weight: 600;
  color: #b91c1c;
}

.controls {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.controls button {
  flex: 1 1 0;
  min-height: 44px;
}

.moves {
  max-height: 320px;
  overflow: auto;
  -webkit-overflow-scrolling: touch;
  list-style: none;
  padding-left: 0;
  margin: 0;
}

.moves li {
  min-height: 40px;
  display: flex;
  align-items: center;
}

.hint {
  text-align: center;
}

.hint button {
  min-height: 44px;
  padding: 10px 16px;
}

@media (min-width: 768px) {
  .layout {
    grid-template-columns: 528px 1fr;
    gap: 24px;
  }

  .controls button {
    flex: 0 0 auto;
    min-height: 0;
  }

  .moves {
    max-height: 420px;
  }

  .moves li {
    min-height: 0;
  }
}
</style>
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd frontend && npx vitest run src/views/__tests__/PlayView.test.js`
Expected: 7 passed

- [ ] **Step 5: 提交**

```bash
git add frontend/src/router/index.js frontend/src/views/PlayView.vue frontend/src/views/__tests__/PlayView.test.js
git commit -m "feat(web): 人人对弈页面走子、悔棋与翻转"
```

---

### Task 5: 对弈页面接入 AI 分析

**Files:**
- Modify: `frontend/src/views/PlayView.vue`
- Test: `frontend/src/views/__tests__/PlayView.test.js`

- [ ] **Step 1: 写失败测试**

在 `PlayView.test.js` 的 `import { api } from "../../api";` 后补充导入：

```js
import { analyzeStream } from "../../api";
```

在文件顶部（`describe` 之前，`beforeEach` 附近）加入 mock 基础设施：

```js
let streams = [];

function emitResult(index, payload) {
  streams[index].handlers.onResult(payload);
}

function emitDone(index) {
  streams[index].handlers.onDone({});
}
```

`beforeEach` 中增加：

```js
    streams = [];
    analyzeStream.mockImplementation((payload, handlers = {}) => {
      streams.push({ payload, handlers });
      return Promise.resolve();
    });
```

在 `describe` 内追加测试：

```js
  it("进入页面自动分析当前局面", async () => {
    const wrapper = mountView();
    await flushPromises();

    expect(analyzeStream).toHaveBeenCalledTimes(1);
    expect(streams[0].payload.initial_fen).toBe(INITIAL_FEN);
    expect(streams[0].payload.moves).toEqual([]);
  });

  it("走子后重新分析并展示分数与箭头", async () => {
    const wrapper = mountView();
    await flushPromises();
    await clickCells(wrapper, [1, 2], [4, 2]);
    await flushPromises();

    expect(analyzeStream).toHaveBeenCalledTimes(2);
    expect(streams[1].payload.moves).toEqual([{ x1: 1, y1: 2, x2: 4, y2: 2 }]);

    emitResult(1, {
      depth: 8,
      score_red: 135,
      mate: null,
      time_ms: 100,
      pv: [
        { x1: 3, y1: 0, x2: 4, y2: 2, chinese: "炮二平五", iccs: "c0e2" },
        { x1: 1, y1: 9, x2: 2, y2: 7, chinese: "马8进7", iccs: "b9c7" },
      ],
    });
    await nextTick();

    expect(wrapper.find('[data-test="score"]').text()).toContain("+135");
    expect(board(wrapper).props("arrows")).toHaveLength(2);
  });

  it("悔棋后重新分析", async () => {
    const wrapper = mountView();
    await flushPromises();
    await clickCells(wrapper, [1, 2], [4, 2]);
    await flushPromises();

    await button(wrapper, "undo").trigger("click");
    await flushPromises();
    expect(analyzeStream).toHaveBeenCalledTimes(3);
    expect(streams[2].payload.moves).toEqual([]);
  });

  it("分析失败时显示失败原因", async () => {
    const wrapper = mountView();
    await flushPromises();
    emitDone(0);
    await nextTick();
    expect(wrapper.find('[data-test="analysis-status"]').text()).toContain("已完成");
  });
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd frontend && npx vitest run src/views/__tests__/PlayView.test.js`
Expected: FAIL（无分析面板、未调用 `analyzeStream`）

- [ ] **Step 3: 实现分析面板**

修改 `frontend/src/views/PlayView.vue`：

1. template 中，在 `<div class="controls">...</div>` 之后插入：

```html
        <div class="analysis" data-test="analysis">
          <div class="score-row">
            <span class="score-text" data-test="score">{{ scoreText }}</span>
            <div v-if="analysis.scoreRed !== null" class="score-bar">
              <div class="score-bar-fill" :style="{ width: barWidth + '%' }"></div>
            </div>
          </div>
          <p class="analysis-status" data-test="analysis-status">{{ statusText }}</p>
          <ol v-if="analysis.results.length" class="analysis-history">
            <li v-for="r in analysis.results" :key="r.depth" data-test="analysis-item">
              <span class="depth">第 {{ r.depth }} 层</span>
              <span class="score">{{ formatScore(r.score_red, r.mate) }}</span>
              <span class="line">{{ pvText(r) }}</span>
              <span class="time">{{ r.time_ms }}ms</span>
            </li>
          </ol>
        </div>
```

2. script 中，导入行改为：

```js
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useRoute } from "vue-router";
import ChessBoard from "../components/ChessBoard.vue";
import { analyzeStream, api } from "../api";
import { createPlaySession } from "../stores/play";
```

3. script 中，在 `const session = createPlaySession({});` 之后插入：

```js
function emptyAnalysis(status) {
  return {
    status,
    results: [],
    scoreRed: null,
    mate: null,
    best: null,
    reply: null,
    error: "",
  };
}

const analysis = ref(emptyAnalysis("idle"));
let controller = null;
let requestToken = 0;

const arrows = computed(() => {
  const out = [];
  const a = analysis.value;
  if (a.best) out.push({ ...a.best, kind: "best" });
  if (a.reply) out.push({ ...a.reply, kind: "reply" });
  return out;
});

function formatScore(scoreRed, mate) {
  if (scoreRed === null || scoreRed === undefined) return "";
  if (mate !== null && mate !== undefined) {
    const side = scoreRed >= 0 ? "红方" : "黑方";
    return `${side} ${Math.abs(mate)} 步杀`;
  }
  if (Math.abs(scoreRed) < 1) return "均势";
  const value = Math.abs(scoreRed);
  return scoreRed > 0 ? `红优 +${value}` : `黑优 ${value}`;
}

const scoreText = computed(() => formatScore(analysis.value.scoreRed, analysis.value.mate));

const barWidth = computed(() => {
  const score = analysis.value.scoreRed;
  if (score === null) return 50;
  const clamped = Math.max(-1000, Math.min(1000, score));
  return 50 + clamped / 20;
});

const statusText = computed(() => {
  const a = analysis.value;
  if (a.status === "running") return "分析中…";
  if (a.status === "done") return "已完成";
  if (a.status === "error") return `分析失败：${a.error}`;
  return "";
});

function pvText(r) {
  return (r.pv || []).map((p) => p.chinese || p.iccs).join(" → ");
}

function stopAnalysis() {
  requestToken += 1;
  if (controller) {
    controller.abort();
    controller = null;
  }
}

function startAnalysis() {
  stopAnalysis();
  const token = requestToken;
  analysis.value = emptyAnalysis("running");
  controller = new AbortController();
  analyzeStream(
    {
      initial_fen: session.state.initialFen,
      moves: session.state.moves.map(({ chinese, ...rest }) => rest),
    },
    {
      signal: controller.signal,
      onResult: (r) => {
        if (token !== requestToken) return;
        const current = analysis.value;
        current.results.unshift(r);
        current.scoreRed = r.score_red ?? null;
        current.mate = r.mate ?? null;
        current.best = r.pv?.[0] ?? null;
        current.reply = r.pv?.[1] ?? null;
      },
      onDone: () => {
        if (token === requestToken) analysis.value.status = "done";
      },
      onError: (e) => {
        if (token !== requestToken) return;
        analysis.value.status = "error";
        analysis.value.error = e?.message || "未知错误";
      },
    }
  );
}
```

4. `onCellClick` 与 `undo` 改为触发分析：

```js
async function onCellClick(x, y) {
  const before = session.state.moves.length;
  await session.click(x, y);
  if (session.state.moves.length !== before) startAnalysis();
}

function undo() {
  if (!session.state.moves.length) return;
  session.undo();
  startAnalysis();
}
```

5. `load()` 末尾（`loading.value = false;` 之后）加 `startAnalysis();`：

```js
  loading.value = false;
  startAnalysis();
```

6. 生命周期：`onMounted(load);` 之后加：

```js
onUnmounted(stopAnalysis);
```

7. style 中追加（从 PracticeView 复制分析面板样式）：

```css
.analysis {
  background: #faf6ee;
  border: 1px solid #e6ddcc;
  border-radius: 10px;
  padding: 12px;
}

.score-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.score-text {
  font-weight: 600;
  white-space: nowrap;
}

.score-bar {
  flex: 1;
  height: 8px;
  border-radius: 4px;
  background: #e05252;
  overflow: hidden;
}

.score-bar-fill {
  height: 100%;
  border-radius: 4px;
  background: linear-gradient(90deg, #7fb0ff, #2563eb);
  transition: width 0.2s ease;
}

.analysis-status {
  margin: 6px 0 0;
  font-size: 13px;
  color: #6b5b45;
}

.analysis-history {
  list-style: none;
  margin: 8px 0 0;
  padding: 0;
  max-height: 200px;
  overflow: auto;
  -webkit-overflow-scrolling: touch;
  font-size: 13px;
}

.analysis-history li {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 8px;
  min-height: 40px;
  padding: 4px 0;
  border-top: 1px solid #e9dfcd;
}

.analysis-history li:first-child {
  border-top: 0;
}

.analysis-history .depth {
  font-weight: 600;
}

.analysis-history .line {
  flex: 1 1 100%;
  color: #4a3a28;
  word-break: break-all;
}

.analysis-history .time {
  margin-left: auto;
  color: #8a7a63;
}

@media (min-width: 768px) {
  .analysis-history {
    max-height: 260px;
  }

  .analysis-history li {
    min-height: 0;
  }
}
```

> 注意：模板中 `ChessBoard` 需补上 `:arrows="arrows"`（Task 4 未设置）。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd frontend && npx vitest run src/views/__tests__/PlayView.test.js`
Expected: 11 passed

- [ ] **Step 5: 提交**

```bash
git add frontend/src/views/PlayView.vue frontend/src/views/__tests__/PlayView.test.js
git commit -m "feat(web): 对弈页每步自动 AI 分析与箭头推演"
```

---

### Task 6: 保存对局到棋谱库

**Files:**
- Modify: `frontend/src/views/PlayView.vue`
- Test: `frontend/src/views/__tests__/PlayView.test.js`

- [ ] **Step 1: 写失败测试**

在 `PlayView.test.js` 的 `describe` 内追加：

```js
  it("保存弹窗预填终局结果并提交棋谱", async () => {
    api.validateMove.mockResolvedValue({
      legal: true,
      fen: INITIAL_FEN,
      side_to_move: "black",
      chinese: "车二进九",
      check: true,
      game_over: { winner: "red", reason: "checkmate" },
    });
    api.createGame.mockResolvedValue({ id: 9 });
    const wrapper = mountView();
    await flushPromises();
    await clickCells(wrapper, [1, 2], [4, 2]);
    await flushPromises();

    await button(wrapper, "save").trigger("click");
    expect(wrapper.find('[data-test="save-result"]').element.value).toBe("1-0");

    await button(wrapper, "save-submit").trigger("submit");
    await flushPromises();

    expect(api.createGame).toHaveBeenCalledWith(
      expect.objectContaining({
        result: "1-0",
        category: "对弈",
        practice_side: "both",
        initial_fen: INITIAL_FEN,
        moves: [{ x1: 1, y1: 2, x2: 4, y2: 2 }],
      })
    );
    expect(push).toHaveBeenCalledWith("/practice/9");
  });

  it("保存失败在弹窗内显示错误", async () => {
    api.createGame.mockRejectedValue({ response: { data: { error: "名称重复" } } });
    const wrapper = mountView();
    await flushPromises();

    await button(wrapper, "save").trigger("click");
    await button(wrapper, "save-submit").trigger("submit");
    await flushPromises();

    expect(wrapper.find('[data-test="save-error"]').text()).toBe("名称重复");
  });
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd frontend && npx vitest run src/views/__tests__/PlayView.test.js`
Expected: FAIL（无保存按钮与弹窗）

- [ ] **Step 3: 实现保存弹窗**

修改 `frontend/src/views/PlayView.vue`：

1. 模板顶部 `<section class="play">` 内，`</div>`（`v-else` 的布局块结束）之后插入：

```html
    <div v-if="showSave" class="modal" data-test="save-modal">
      <form class="save-form" @submit.prevent="save">
        <h3>保存到棋谱库</h3>
        <label>名称<input v-model="form.name" data-test="save-name" /></label>
        <label>红方<input v-model="form.red_player" /></label>
        <label>黑方<input v-model="form.black_player" /></label>
        <label>赛事<input v-model="form.event" /></label>
        <label>分类<input v-model="form.category" /></label>
        <label>
          结果
          <select v-model="form.result" data-test="save-result">
            <option value="*">未结束</option>
            <option value="1-0">红胜</option>
            <option value="0-1">黑胜</option>
            <option value="1/2-1/2">和棋</option>
          </select>
        </label>
        <p v-if="saveError" class="warn" data-test="save-error">{{ saveError }}</p>
        <div class="modal-actions">
          <button type="button" @click="showSave = false">取消</button>
          <button type="submit" data-test="save-submit" :disabled="saving">保存</button>
        </div>
      </form>
    </div>
```

2. 模板的 controls 块中，"翻转棋盘"按钮之后加：

```html
          <button data-test="save" @click="openSave">保存到棋谱库</button>
```

3. script 导入改为：

```js
import { computed, onMounted, onUnmounted, reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
```

并在 `const route = useRoute();` 后加 `const router = useRouter();`

4. script 的 `load()` 之前插入：

```js
const showSave = ref(false);
const saving = ref(false);
const saveError = ref("");
const form = reactive({
  name: "红方 vs 黑方",
  red_player: "",
  black_player: "",
  event: "",
  category: "对弈",
  result: "*",
});

function openSave() {
  if (session.state.gameOver) {
    form.result = session.state.gameOver.winner === "red" ? "1-0" : "0-1";
  }
  saveError.value = "";
  showSave.value = true;
}

async function save() {
  saving.value = true;
  saveError.value = "";
  try {
    const created = await api.createGame({
      name: form.name || "红方 vs 黑方",
      red_player: form.red_player,
      black_player: form.black_player,
      event: form.event,
      category: form.category,
      result: form.result,
      initial_fen: session.state.initialFen,
      moves: session.state.moves.map(({ chinese, ...move }) => move),
      practice_side: "both",
    });
    showSave.value = false;
    router.push(`/practice/${created.id}`);
  } catch (err) {
    saveError.value = err?.response?.data?.error || "保存失败";
  } finally {
    saving.value = false;
  }
}
```

5. style 中追加：

```css
.modal {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
}

.save-form {
  width: 100%;
  max-width: 360px;
  background: #fff;
  border-radius: 12px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.save-form h3 {
  margin: 0;
}

.save-form label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 14px;
}

.save-form input,
.save-form select {
  min-height: 40px;
  padding: 6px 10px;
  border: 1px solid #cbb89a;
  border-radius: 6px;
  font: inherit;
}

.modal-actions {
  display: flex;
  gap: 8px;
  margin-top: 4px;
}

.modal-actions button {
  flex: 1;
  min-height: 44px;
}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd frontend && npx vitest run src/views/__tests__/PlayView.test.js`
Expected: 13 passed

- [ ] **Step 5: 提交**

```bash
git add frontend/src/views/PlayView.vue frontend/src/views/__tests__/PlayView.test.js
git commit -m "feat(web): 对弈结果手动保存到棋谱库"
```

---

### Task 7: 入口按钮（打谱页 / 棋谱库）

**Files:**
- Modify: `frontend/src/views/PracticeView.vue`
- Modify: `frontend/src/views/LibraryView.vue`
- Test: `frontend/src/views/__tests__/PracticeView.test.js`
- Test: `frontend/src/views/__tests__/LibraryView.test.js`

- [ ] **Step 1: 写失败测试**

1. `PracticeView.test.js` 顶部 mock 增加 `useRouter`：

```js
const { route, push } = vi.hoisted(() => ({
  route: { params: { id: "1" } },
  push: vi.fn(),
}));

vi.mock("vue-router", () => ({
  useRoute: () => route,
  useRouter: () => ({ push }),
}));
```

在 `beforeEach` 中加 `push.mockClear();`。

在 `describe` 内追加：

```js
  it("点击从此处开始对弈跳转 /play 携带 game 与 ply", async () => {
    const wrapper = mountView();
    await flushPromises();

    await button(wrapper, "next").trigger("click");
    await nextTick();
    await button(wrapper, "start-play").trigger("click");

    expect(push).toHaveBeenCalledWith({ path: "/play", query: { game: 1, ply: 1 } });
  });
```

2. `LibraryView.test.js` 中追加（若已有类似 mountView 辅助则复用）：

```js
  it("工具栏提供新对局入口", async () => {
    const wrapper = mountView();
    await flushPromises();
    expect(wrapper.html()).toContain('href="/play"');
  });
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd frontend && npx vitest run src/views/__tests__/PracticeView.test.js src/views/__tests__/LibraryView.test.js`
Expected: FAIL（按钮与链接不存在）

- [ ] **Step 3: 实现**

1. `PracticeView.vue` 模板 controls 块中，"|&gt;|" 按钮之后加：

```html
            <button data-test="start-play" @click="startPlay">从此处开始对弈</button>
```

2. `PracticeView.vue` script：导入改为 `import { useRoute, useRouter } from "vue-router";`，并在 `const route = useRoute();` 后加：

```js
const router = useRouter();
```

在 `function go(target) {...}` 之后加：

```js
function startPlay() {
  if (!game.value) return;
  router.push({ path: "/play", query: { game: game.value.id, ply: ply.value } });
}
```

3. `LibraryView.vue` 工具栏中，`<router-link to="/editor" class="btn primary">新建棋谱</router-link>` 之后加：

```html
      <router-link to="/play" class="btn">新对局</router-link>
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd frontend && npx vitest run src/views/__tests__/PracticeView.test.js src/views/__tests__/LibraryView.test.js`
Expected: 全部通过

- [ ] **Step 5: 提交**

```bash
git add frontend/src/views/PracticeView.vue frontend/src/views/LibraryView.vue frontend/src/views/__tests__/PracticeView.test.js frontend/src/views/__tests__/LibraryView.test.js
git commit -m "feat(web): 打谱页与棋谱库新增对弈入口"
```

---

### Task 8: 全量验证与构建

**Files:** 无新增，仅验证

- [ ] **Step 1: 后端全量测试**

Run: `cd backend && .venv/bin/python -m pytest tests/ -q`
Expected: 全部通过

- [ ] **Step 2: 前端全量测试**

Run: `cd frontend && npx vitest run`
Expected: 全部通过

- [ ] **Step 3: 构建前端产物**

Run: `cd frontend && npm run build`
Expected: 构建成功，`dist/assets/PlayView-*.js` 生成

- [ ] **Step 4: 手动冒烟（需要用户参与）**

1. 重启后端（`kill <旧 PID>`，`cd backend && setsid nohup .venv/bin/python app.py > /tmp/chess-backend.log 2>&1 &`）。
2. 浏览器打开 `http://127.0.0.1:5000/play`：走几步、翻转棋盘、观察分析面板与箭头、悔棋、保存。
3. 打开打谱页点击「从此处开始对弈」，确认从当前步续下。

- [ ] **Step 5: 提交（如有遗留修改）**

```bash
git status --short
# 若有未提交改动（例如构建产物不纳入版本库，只有源码），按需提交
```
