# 人机对战与局面编辑实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在「人人对弈」页（`/play`）新增人机对战（引擎执红 / 执黑 + 三档难度）与局面编辑（摆子 + 完整摆子规则校验）两项能力。

**Architecture:** 后端新增 `POST /api/engine/best-move`（一次性 JSON，复用 `engine.analyze` 与 `_ANALYZE_LOCK` 返回引擎最佳着法）与 `POST /api/engine/validate-position`（调用新增的 `chess_engine/rules.py::validate_setup` 校验摆子合法性）。前端在 `PlayView.vue` 内扩展模式状态与编辑状态，新增 `PiecePalette.vue` 棋子面板，`play.js` 增加 `applyEngineMove`，`api/index.js` 增加两个封装。规则全部留在后端。

**Tech Stack:** Flask、numba/numpy 引擎（只读复用）、chess_engine 规则引擎、Vue 3 + vitest + @vue/test-utils。

**设计文档:** `docs/plans/2026-09-22-ai-play-and-board-editor-design.md`

**关键事实（已核实）:**
- 后端测试：`cd backend && .venv/bin/python -m pytest tests/<file> -v`；首次运行含 numba JIT 编译（约 20-35s）。
- 前端测试：`cd frontend && npm test`（`vitest run`）；单文件 `npx vitest run src/views/__tests__/PlayView.test.js`。
- `engine.analyze(fen, start_depth=, max_depth=, time_limit_ms=, stop=)` 逐层产出 `AnalysisResult`；`r.pv[0]` 为 packed int 着法；`EC.ROOT_START_DEPTH == 4`，从第 4 层起有产出。
- `routes/engine.py` 现有 `_resolve_fen(data)`、`_move_to_xy(packed)`、`_valid_move_dict`、`_ANALYZE_LOCK`、`Move`、`move_to_chinese`、`Board`、`EC` 可直接复用。
- `chess_engine.board.Board`：`empty()` / `set_piece(x,y,(side,kind))` / `pieces_of(side) -> [(pos, piece)]` / `kings_facing()` / `in_check(side)` / `has_legal_move(side)` / `to_fen()`；`RED="red"`、`BLACK="black"`。
- 前端 `play.js` 的 `reset({ initial_fen })` 会按 FEN 第二段确定先行方；`rebuild()` 会重算 `sideToMove` / `check` / `gameOver`。
- `PlayView.vue` 走子成功后调用 `startIntent()`（先意图后评分）；引擎走子须先于分析，避免与 `/analyze` 争锁。

**零侵入约束:**
- 不修改 `engine/**`、`chess_engine/board.py`、`chess_engine/fen.py` 的既有代码；摆子规则放新文件 `chess_engine/rules.py`。
- `routes/engine.py` 只**新增**端点与辅助常量 / 函数，不改既有函数。
- 每个后端 Task 结束跑全量后端测试确认无回归。

---

### Task 1: 摆子规则模块 `chess_engine/rules.py`

**Files:**
- Create: `backend/chess_engine/rules.py`
- Test: `backend/tests/test_position_rules.py`

**Step 1: 写失败测试**

```python
"""摆子规则 `validate_setup` 单元测试。"""

from chess_engine.board import BLACK, RED, Board
from chess_engine.rules import validate_setup


def board_with(pieces, side=RED):
    board = Board.empty()
    for x, y, s, kind in pieces:
        board.set_piece(x, y, (s, kind))
    board.side_to_move = side
    return board


def minimal_ok():
    return [(4, 0, RED, "K"), (4, 9, BLACK, "K")]


def test_valid_minimal_position():
    assert validate_setup(board_with(minimal_ok())) == []


def test_requires_exactly_one_king_each_side():
    errors = validate_setup(board_with([(4, 0, RED, "K")]))
    assert any("黑方" in e and "将" in e for e in errors)
    errors = validate_setup(board_with([(4, 0, RED, "K"), (4, 9, BLACK, "K"), (3, 0, RED, "K")]))
    assert any("红方" in e and "帅" in e for e in errors)


def test_king_must_stay_in_palace():
    errors = validate_setup(board_with([(4, 5, RED, "K"), (4, 9, BLACK, "K")]))
    assert any("红方" in e for e in errors)


def test_advisor_must_stay_in_palace():
    errors = validate_setup(board_with(minimal_ok() + [(0, 0, RED, "A")]))
    assert any("红方" in e for e in errors)


def test_elephant_cannot_cross_river():
    errors = validate_setup(board_with(minimal_ok() + [(2, 5, RED, "B")]))
    assert any("红相" in e for e in errors)
    errors = validate_setup(board_with(minimal_ok() + [(2, 4, BLACK, "B")]))
    assert any("黑象" in e for e in errors)


def test_soldier_position_bounds():
    errors = validate_setup(board_with(minimal_ok() + [(0, 2, RED, "P")]))
    assert any("红兵" in e for e in errors)
    errors = validate_setup(board_with(minimal_ok() + [(0, 7, BLACK, "P")]))
    assert any("黑卒" in e for e in errors)


def test_piece_count_limits():
    pieces = minimal_ok() + [(i, 3, RED, "P") for i in range(6)]
    errors = validate_setup(board_with(pieces))
    assert any("红方" in e and "兵" in e for e in errors)


def test_kings_facing_rejected():
    errors = validate_setup(board_with([(4, 0, RED, "K"), (4, 9, BLACK, "K")], side=RED))
    assert any("照面" in e for e in errors)


def test_side_in_check_rejected():
    # 黑车 (4, 5) 正对红帅 (4, 0)，中间无子 → 红被将军
    errors = validate_setup(board_with(minimal_ok() + [(4, 5, BLACK, "R")]))
    assert any("红方" in e and "将军" in e for e in errors)
```

**Step 2: 跑测试确认失败**

Run: `cd backend && .venv/bin/python -m pytest tests/test_position_rules.py -v`
Expected: FAIL（`ModuleNotFoundError: chess_engine.rules`）

**Step 3: 最小实现**

```python
"""摆子合法性校验（不修改 Board，纯查询）。

规则见 docs/plans/2026-09-22-ai-play-and-board-editor-design.md：
帅将各一、各兵种数量不超初始配置、帅将士仕在九宫、相象不过河、
兵卒不出现在不可达位置、不得照面、任何一方不得被将军。
"""

from chess_engine.board import BLACK, RED

__all__ = ["validate_setup"]

SIDE_NAMES = {RED: "红方", BLACK: "黑方"}

# 各兵种数量上限（帅将单独判定）
MAX_COUNTS = {
    "A": (2, "仕/士"),
    "B": (2, "相/象"),
    "N": (2, "马"),
    "R": (2, "车"),
    "C": (2, "炮"),
    "P": (5, "兵/卒"),
}


def _in_palace(x, y, side):
    if x < 3 or x > 5:
        return False
    if side == RED:
        return 0 <= y <= 2
    return 7 <= y <= 9


def validate_setup(board):
    """返回错误文案列表；空列表表示合法。"""
    errors = []

    for side in (RED, BLACK):
        pieces = board.pieces_of(side)
        counts = {}
        for _pos, (_s, kind) in pieces:
            counts[kind] = counts.get(kind, 0) + 1

        king_name = "帅" if side == RED else "将"
        if counts.get("K", 0) != 1:
            errors.append(f"{SIDE_NAMES[side]}必须有且仅有一个{king_name}")

        for kind, (limit, name) in MAX_COUNTS.items():
            if counts.get(kind, 0) > limit:
                errors.append(f"{SIDE_NAMES[side]}的{name}不能超过 {limit} 个")

        for (x, y), (_s, kind) in pieces:
            if kind in ("K", "A") and not _in_palace(x, y, side):
                errors.append(f"{SIDE_NAMES[side]}{'帅/将' if kind == 'K' else '仕/士'}必须在九宫内")
            elif kind == "B":
                if side == RED and y > 4:
                    errors.append("红相不能在黑方半场")
                if side == BLACK and y < 5:
                    errors.append("黑象不能在红方半场")
            elif kind == "P":
                if side == RED and y < 3:
                    errors.append("红兵不能出现在红方底线附近")
                if side == BLACK and y > 6:
                    errors.append("黑卒不能出现在黑方底线附近")

    if board.kings_facing():
        errors.append("双方帅将不能照面")

    for side in (RED, BLACK):
        if board.in_check(side):
            errors.append(f"{SIDE_NAMES[side]}处于被将军状态")

    return errors
```

**Step 4: 跑测试确认通过**

Run: `cd backend && .venv/bin/python -m pytest tests/test_position_rules.py -v`
Expected: PASS（全部用例）

**Step 5: 跑全量后端测试确认无回归**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: 全部通过（1 个既有 skip 不变）

**Step 6: 提交**

```bash
git add backend/chess_engine/rules.py backend/tests/test_position_rules.py
git commit -m "feat(rules): 摆子合法性校验 validate_setup"
```

---

### Task 2: `POST /api/engine/validate-position` 接口

**Files:**
- Modify: `backend/routes/engine.py`（文件末尾新增端点与辅助常量）
- Test: `backend/tests/test_engine_validate_position_api.py`

**Step 1: 写失败测试**

```python
"""`POST /api/engine/validate-position` 摆子规则校验接口测试。"""


def post(client, payload):
    return client.post("/api/engine/validate-position", json=payload)


def test_valid_position_returns_fen(client):
    body = post(
        client,
        {
            "pieces": [
                {"x": 4, "y": 0, "side": "red", "kind": "K"},
                {"x": 4, "y": 9, "side": "black", "kind": "K"},
                {"x": 0, "y": 3, "side": "red", "kind": "P"},
            ],
            "side_to_move": "black",
        },
    ).get_json()
    assert body["valid"] is True
    assert body["fen"].split()[1] == "b"
    assert body["fen"].startswith("3k5/9/9/P8/9/9/9/9/9/3K5")


def test_invalid_position_returns_errors(client):
    body = post(
        client,
        {
            "pieces": [
                {"x": 4, "y": 5, "side": "red", "kind": "K"},
                {"x": 4, "y": 9, "side": "black", "kind": "K"},
            ],
            "side_to_move": "red",
        },
    ).get_json()
    assert body["valid"] is False
    assert any("红方" in e for e in body["errors"])


def test_empty_pieces_is_invalid(client):
    body = post(client, {"pieces": [], "side_to_move": "red"}).get_json()
    assert body["valid"] is False
    assert len(body["errors"]) >= 2


def test_kings_facing_rejected(client):
    body = post(
        client,
        {
            "pieces": [
                {"x": 4, "y": 0, "side": "red", "kind": "K"},
                {"x": 4, "y": 9, "side": "black", "kind": "K"},
            ],
            "side_to_move": "red",
        },
    ).get_json()
    assert body["valid"] is False
    assert any("照面" in e for e in body["errors"])


def test_rejects_bad_payloads(client):
    assert client.post("/api/engine/validate-position", json={}).status_code == 400
    assert post(client, {"pieces": "x"}).status_code == 400
    assert post(client, {"pieces": [{"x": 9, "y": 0, "side": "red", "kind": "K"}]}).status_code == 400
    assert post(client, {"pieces": [{"x": 4, "y": 0, "side": "green", "kind": "K"}]}).status_code == 400
    assert post(client, {"pieces": [{"x": 4, "y": 0, "side": "red", "kind": "X"}]}).status_code == 400
    assert post(client, {"pieces": [], "side_to_move": "blue"}).status_code == 400
```

**Step 2: 跑测试确认失败**

Run: `cd backend && .venv/bin/python -m pytest tests/test_engine_validate_position_api.py -v`
Expected: FAIL（404 / 断言失败）

**Step 3: 最小实现**

在 `backend/routes/engine.py` 末尾追加（并在文件顶部 import 区补充 `from chess_engine.rules import validate_setup`）：

```python
# ---- 摆子规则校验（新端点） -----------------------------------------

VALID_SIDES = ("red", "black")
VALID_KINDS = ("K", "A", "B", "N", "R", "C", "P")


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


@engine_bp.post("/validate-position")
def validate_position():
    """校验摆子局面是否符合摆子规则，合法则返回对应 FEN。"""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "请求体必须是 JSON 对象"}), 400

    pieces = data.get("pieces")
    if not isinstance(pieces, list):
        return jsonify({"error": "pieces 必须是数组"}), 400
    side = data.get("side_to_move", "red")
    if side not in VALID_SIDES:
        return jsonify({"error": "side_to_move 必须是 red 或 black"}), 400

    board = Board.empty()
    for index, raw in enumerate(pieces, start=1):
        if not isinstance(raw, dict):
            return jsonify({"error": "棋子格式错误", "detail": f"第 {index} 个棋子格式错误"}), 400
        x, y = raw.get("x"), raw.get("y")
        if not _is_int(x) or not _is_int(y) or not (0 <= x < 9 and 0 <= y < 10):
            return jsonify({"error": "棋子坐标错误", "detail": f"第 {index} 个棋子坐标越界"}), 400
        piece_side, kind = raw.get("side"), raw.get("kind")
        if piece_side not in VALID_SIDES or kind not in VALID_KINDS:
            return jsonify({"error": "棋子类型错误", "detail": f"第 {index} 个棋子类型非法"}), 400
        board.set_piece(x, y, (piece_side, kind))
    board.side_to_move = side

    errors = validate_setup(board)
    if errors:
        return jsonify({"valid": False, "errors": errors})
    return jsonify({"valid": True, "fen": board.to_fen()})
```

**Step 4: 跑测试确认通过**

Run: `cd backend && .venv/bin/python -m pytest tests/test_engine_validate_position_api.py -v`
Expected: PASS

**Step 5: 跑全量后端测试确认无回归**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: 全部通过

**Step 6: 提交**

```bash
git add backend/routes/engine.py backend/tests/test_engine_validate_position_api.py
git commit -m "feat(api): 摆子规则校验端点 /engine/validate-position"
```

---

### Task 3: `POST /api/engine/best-move` 接口

**Files:**
- Modify: `backend/routes/engine.py`（文件末尾新增端点与难度常量）
- Test: `backend/tests/test_engine_best_move_api.py`

**Step 1: 写失败测试**

```python
"""`POST /api/engine/best-move` 引擎走子接口测试。

首次运行含 numba JIT 编译（约 20-35s）。
"""

from chess_engine.board import INITIAL_FEN


def post(client, payload):
    return client.post("/api/engine/best-move", json=payload)


def test_best_move_from_initial(client):
    body = post(client, {"level": "easy"}).get_json()
    assert body["legal"] is True
    move = body["move"]
    assert all(isinstance(move[k], int) for k in ("x1", "y1", "x2", "y2"))
    assert body["side_to_move"] == "black"
    assert body["fen"] == (
        "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR b - - 0 1"
    ) or body["fen"].split()[1] == "b"
    assert body["move"]["chinese"]


def test_best_move_black_to_move(client):
    fen = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/4C2C1/9/RNBAKABNR b - - 0 1"
    body = post(client, {"fen": fen, "level": "easy"}).get_json()
    assert body["legal"] is True
    assert body["side_to_move"] == "red"


def test_best_move_level_defaults_and_invalid_falls_back(client):
    for level in (None, "unknown"):
        payload = {} if level is None else {"level": level}
        body = post(client, payload).get_json()
        assert body["legal"] is True


def test_best_move_reports_game_over(client):
    # 红车 (0,8) 走 (0,9) 将死黑将的上一手：直接给红一步杀局面
    fen = "4k4/R8/9/9/4R4/9/9/9/9/4K4 w - - 0 1"
    body = post(client, {"fen": fen, "level": "easy"}).get_json()
    assert body["legal"] is True
    assert body["check"] is True
    assert body["game_over"] == {"winner": "red", "reason": "checkmate"}


def test_best_move_no_legal_move(client):
    # 黑将 (4,9) 被红车 (4,8) 与 (3,8) 控制且无着可走，但未被将军（困毙）
    fen = "4k4/3R1R3/9/9/9/9/9/9/9/3K5 w - - 0 1"
    body = post(client, {"fen": fen, "level": "easy"}).get_json()
    assert body["legal"] is True  # 红仍有合法着法
    # 构造行棋方无着的局面：把走子方设为黑（黑困毙）
    body = post(client, {"fen": fen.replace(" w ", " b "), "level": "easy"}).get_json()
    assert body["legal"] is False


def test_best_move_rejects_bad_payloads(client):
    assert client.post("/api/engine/best-move", json={}).status_code == 200  # 缺省初始局面
    assert post(client, {"fen": "not-a-fen"}).status_code == 400
    assert post(client, {"moves": "x"}).status_code == 400
```

> 注：`test_best_move_no_legal_move` 第一段断言红方有合法着法（该 FEN 红方不困毙）；第二段把行棋方改成黑，黑方无合法着法，接口应返回 `legal:false`。

**Step 2: 跑测试确认失败**

Run: `cd backend && .venv/bin/python -m pytest tests/test_engine_best_move_api.py -v`
Expected: FAIL（404）

**Step 3: 最小实现**

在 `backend/routes/engine.py` 末尾追加：

```python
# ---- 引擎走子（新端点） ---------------------------------------------

BEST_MOVE_LEVELS = {
    "easy": {"max_depth": 5, "time_limit_ms": 300},
    "normal": {"max_depth": 7, "time_limit_ms": 1000},
    "hard": {"max_depth": 11, "time_limit_ms": 2500},
}
DEFAULT_BEST_MOVE_LEVEL = "normal"
BEST_MOVE_START_DEPTH = EC.ROOT_START_DEPTH  # 4


@engine_bp.post("/best-move")
def best_move():
    """返回当前局面的引擎最佳着法（一次性 JSON，持 _ANALYZE_LOCK）。"""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "请求体必须是 JSON 对象"}), 400
    try:
        fen = _resolve_fen(data)
    except _RequestError as exc:
        return jsonify({"error": "局面无效", "detail": str(exc)}), 400

    level = data.get("level")
    if level not in BEST_MOVE_LEVELS:
        level = DEFAULT_BEST_MOVE_LEVEL
    conf = BEST_MOVE_LEVELS[level]

    board = Board().load_fen(fen)
    if not board.has_legal_move(board.side_to_move):
        return jsonify({"legal": False, "reason": "当前局面无合法着法"})

    stop = np.zeros(1, dtype=np.int8)
    last = None
    with _ANALYZE_LOCK:
        for result in analyze(
            fen,
            start_depth=BEST_MOVE_START_DEPTH,
            max_depth=conf["max_depth"],
            time_limit_ms=conf["time_limit_ms"],
            stop=stop,
        ):
            last = result

    if last is None or not last.pv:
        return jsonify({"legal": False, "reason": "引擎未给出着法"})

    x1, y1, x2, y2 = _move_to_xy(last.pv[0])
    move = Move(x1, y1, x2, y2)
    if not board.is_legal(move):
        return jsonify({"legal": False, "reason": "引擎给出的着法不合法"})

    mover = board.side_to_move
    iccs = f"{chr(97 + x1)}{y1}{chr(97 + x2)}{y2}"
    try:
        chinese = move_to_chinese(board, move)
    except ValueError:
        chinese = iccs
    board.apply_move(move)
    opponent = board.side_to_move
    check = board.in_check(opponent)
    game_over = None
    if not board.has_legal_move(opponent):
        game_over = {"winner": mover, "reason": "checkmate" if check else "stalemate"}
    return jsonify(
        {
            "legal": True,
            "move": {
                "x1": x1,
                "y1": y1,
                "x2": x2,
                "y2": y2,
                "iccs": iccs,
                "chinese": chinese,
            },
            "fen": board.to_fen(),
            "side_to_move": opponent,
            "check": check,
            "game_over": game_over,
        }
    )
```

**Step 4: 跑测试确认通过**

Run: `cd backend && .venv/bin/python -m pytest tests/test_engine_best_move_api.py -v`
Expected: PASS

**Step 5: 跑全量后端测试确认无回归**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: 全部通过

**Step 6: 提交**

```bash
git add backend/routes/engine.py backend/tests/test_engine_best_move_api.py
git commit -m "feat(api): 引擎走子端点 /engine/best-move（三档难度）"
```

---

### Task 4: 前端 API 封装与 `play.js::applyEngineMove`

**Files:**
- Modify: `frontend/src/api/index.js:109-122`（`api` 对象）
- Modify: `frontend/src/stores/play.js`（新增 `applyEngineMove` 并导出）
- Test: `frontend/src/stores/__tests__/play.test.js`

**Step 1: 写失败测试**

在 `frontend/src/stores/__tests__/play.test.js` 末尾追加：

```javascript
import { describe, expect, it } from "vitest";
import { createPlaySession } from "../play";

describe("applyEngineMove", () => {
  it("直接追加引擎着法并重建局面", () => {
    const session = createPlaySession({});
    session.applyEngineMove({
      x1: 1, y1: 2, x2: 4, y2: 2,
      chinese: "炮二平五", check: false, game_over: null,
    });
    expect(session.state.moves).toHaveLength(1);
    expect(session.state.moves[0].chinese).toBe("炮二平五");
    expect(session.state.sideToMove).toBe("black");
  });

  it("记录终局快照", () => {
    const session = createPlaySession({});
    session.applyEngineMove({
      x1: 1, y1: 2, x2: 4, y2: 2,
      chinese: "炮二平五", check: true,
      game_over: { winner: "red", reason: "checkmate" },
    });
    expect(session.state.gameOver).toEqual({ winner: "red", reason: "checkmate" });
  });
});
```

> 注意：既有测试文件顶部已 import `createPlaySession`，若重复 import 需合并，避免重复声明。

**Step 2: 跑测试确认失败**

Run: `cd frontend && npx vitest run src/stores/__tests__/play.test.js`
Expected: FAIL（`session.applyEngineMove is not a function`）

**Step 3: 最小实现**

`frontend/src/api/index.js` 的 `api` 对象内新增：

```javascript
  bestMove: (data) => http.post("/engine/best-move", data).then((r) => r.data),
  validatePosition: (data) => http.post("/engine/validate-position", data).then((r) => r.data),
```

`frontend/src/stores/play.js` 新增函数（放在 `applyState` 之后、`reset` 调用之前），并在 return 中导出：

```javascript
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
```

```javascript
  return { state, click, undo, reset, applyState, applyEngineMove };
```

**Step 4: 跑测试确认通过**

Run: `cd frontend && npx vitest run src/stores/__tests__/play.test.js`
Expected: PASS

**Step 5: 提交**

```bash
git add frontend/src/api/index.js frontend/src/stores/play.js frontend/src/stores/__tests__/play.test.js
git commit -m "feat(frontend): best-move/validate-position API 与 applyEngineMove"
```

---

### Task 5: `PiecePalette.vue` 棋子面板组件

**Files:**
- Create: `frontend/src/components/PiecePalette.vue`
- Test: `frontend/src/components/__tests__/PiecePalette.test.js`

**Step 1: 写失败测试**

```javascript
import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import PiecePalette from "../PiecePalette.vue";

function findPiece(wrapper, side, kind) {
  return wrapper.find(`[data-piece="${side}-${kind}"]`);
}

describe("PiecePalette", () => {
  it("渲染红黑各 7 种棋子", () => {
    const wrapper = mount(PiecePalette);
    expect(wrapper.findAll("[data-piece]")).toHaveLength(14);
  });

  it("点击棋子发出 select 事件", async () => {
    const wrapper = mount(PiecePalette);
    await findPiece(wrapper, "red", "R").trigger("click");
    expect(wrapper.emitted("select")[0]).toEqual([{ side: "red", kind: "R" }]);
  });

  it("选中项带高亮样式", () => {
    const wrapper = mount(PiecePalette, { props: { selected: { side: "black", kind: "C" } } });
    expect(findPiece(wrapper, "black", "C").classes()).toContain("active");
  });

  it("清空与标准开局按钮发出事件", async () => {
    const wrapper = mount(PiecePalette);
    await wrapper.find('[data-test="palette-clear"]').trigger("click");
    await wrapper.find('[data-test="palette-initial"]').trigger("click");
    expect(wrapper.emitted("clear")).toHaveLength(1);
    expect(wrapper.emitted("initial")).toHaveLength(1);
  });
});
```

**Step 2: 跑测试确认失败**

Run: `cd frontend && npx vitest run src/components/__tests__/PiecePalette.test.js`
Expected: FAIL（模块不存在）

**Step 3: 最小实现**

```vue
<script setup>
import { LABELS } from "../utils/chess";

defineProps({
  selected: { type: Object, default: null },
});
defineEmits(["select", "clear", "initial"]);

const kinds = ["K", "A", "B", "N", "R", "C", "P"];
const sides = ["red", "black"];
const label = (side, kind) => LABELS[`${side}-${kind}`];
</script>

<template>
  <div class="palette">
    <div v-for="side in sides" :key="side" class="palette-row">
      <button
        v-for="kind in kinds"
        :key="kind"
        type="button"
        :data-piece="`${side}-${kind}`"
        class="piece-btn"
        :class="{
          active: selected && selected.side === side && selected.kind === kind,
          red: side === 'red',
          black: side === 'black',
        }"
        @click="$emit('select', { side, kind })"
      >
        {{ label(side, kind) }}
      </button>
    </div>
    <div class="palette-actions">
      <button type="button" data-test="palette-clear" @click="$emit('clear')">清空棋盘</button>
      <button type="button" data-test="palette-initial" @click="$emit('initial')">标准开局</button>
    </div>
  </div>
</template>

<style scoped>
.palette {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.palette-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.piece-btn {
  min-width: 40px;
  min-height: 40px;
  border: 1px solid #cbb89a;
  border-radius: 50%;
  background: #fff4e0;
  font-size: 18px;
  cursor: pointer;
}

.piece-btn.black {
  background: #f7f7f2;
}

.piece-btn.red {
  color: #b32020;
}

.piece-btn.active {
  border-color: #d4a017;
  box-shadow: 0 0 0 2px rgba(212, 160, 23, 0.5);
}

.palette-actions {
  display: flex;
  gap: 8px;
}

.palette-actions button {
  min-height: 40px;
}
</style>
```

**Step 4: 跑测试确认通过**

Run: `cd frontend && npx vitest run src/components/__tests__/PiecePalette.test.js`
Expected: PASS

**Step 5: 提交**

```bash
git add frontend/src/components/PiecePalette.vue frontend/src/components/__tests__/PiecePalette.test.js
git commit -m "feat(frontend): 摆子棋子面板 PiecePalette"
```

---

### Task 6: `PlayView` 人机对战

**Files:**
- Modify: `frontend/src/views/PlayView.vue`（script + template + 样式）
- Test: `frontend/src/views/__tests__/PlayView.test.js`

**Step 1: 写失败测试**

在 `PlayView.test.js` 的 `vi.mock("../../api", ...)` 的 `api` 中补 `bestMove: vi.fn(), validatePosition: vi.fn()`，并在 `beforeEach` 补默认值：

```javascript
    api.bestMove.mockResolvedValue({
      legal: true,
      move: { x1: 1, y1: 2, x2: 4, y2: 2, chinese: "炮二平五", iccs: "b2e2" },
      fen: INITIAL_FEN,
      side_to_move: "black",
      check: false,
      game_over: null,
    });
```

新增用例：

```javascript
  it("引擎执红时点击后立即走子", async () => {
    const wrapper = mountView();
    await flushPromises();

    await button(wrapper, "engine-red").trigger("click");
    await flushPromises();

    expect(api.bestMove).toHaveBeenCalledWith(
      expect.objectContaining({ level: "normal", moves: [] })
    );
    expect(wrapper.findAll('[data-test="move-list"] li')).toHaveLength(1);
    expect(wrapper.find('[data-test="turn"]').text()).toContain("黑方走棋");
  });

  it("引擎执黑时用户走子后引擎自动应着", async () => {
    const wrapper = mountView();
    await flushPromises();

    await button(wrapper, "engine-black").trigger("click");
    await flushPromises();
    expect(api.bestMove).not.toHaveBeenCalled();

    await clickCells(wrapper, [1, 2], [4, 2]);
    await flushPromises();

    expect(api.bestMove).toHaveBeenCalledTimes(1);
    expect(wrapper.findAll('[data-test="move-list"] li')).toHaveLength(2);
  });

  it("引擎思考中锁定棋盘并显示提示", async () => {
    let resolveMove;
    api.bestMove.mockReturnValue(new Promise((r) => { resolveMove = r; }));
    const wrapper = mountView();
    await flushPromises();

    await button(wrapper, "engine-red").trigger("click");
    await nextTick();
    expect(wrapper.find('[data-test="engine-thinking"]').exists()).toBe(true);

    await clickCells(wrapper, [1, 9]);
    expect(api.validateMove).not.toHaveBeenCalled();

    resolveMove({
      legal: true,
      move: { x1: 1, y1: 2, x2: 4, y2: 2, chinese: "炮二平五" },
      side_to_move: "black", check: false, game_over: null,
    });
    await flushPromises();
    expect(wrapper.find('[data-test="engine-thinking"]').exists()).toBe(false);
  });

  it("难度选择传递给 best-move", async () => {
    const wrapper = mountView();
    await flushPromises();
    await wrapper.find('[data-test="level"]').setValue("hard");
    await button(wrapper, "engine-black").trigger("click");
    await flushPromises();
    await clickCells(wrapper, [1, 2], [4, 2]);
    await flushPromises();
    expect(api.bestMove).toHaveBeenCalledWith(
      expect.objectContaining({ level: "hard" })
    );
  });

  it("已有对局时进入人机需确认，取消则不变", async () => {
    const wrapper = mountView();
    await flushPromises();
    await clickCells(wrapper, [1, 2], [4, 2]);
    await flushPromises();

    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
    await button(wrapper, "engine-red").trigger("click");
    await flushPromises();
    expect(api.bestMove).not.toHaveBeenCalled();
    expect(wrapper.findAll('[data-test="move-list"] li')).toHaveLength(1);
    confirmSpy.mockRestore();
  });
```

**Step 2: 跑测试确认失败**

Run: `cd frontend && npx vitest run src/views/__tests__/PlayView.test.js`
Expected: FAIL（找不到 `[data-test="engine-red"]`）

**Step 3: 实现**

在 `PlayView.vue` 的 `<script setup>` 中：

1. 导入组件与 API：

```javascript
import PiecePalette from "../components/PiecePalette.vue";
import { INITIAL_FEN, fenToPieces } from "../utils/chess";
```

`api` 已整体导入，直接 `api.bestMove` / `api.validatePosition`。

2. 新增状态与常量：

```javascript
const LEVELS = [
  { value: "easy", label: "简单" },
  { value: "normal", label: "普通" },
  { value: "hard", label: "困难" },
];

const mode = ref("human"); // human | ai
const engineSide = ref(null);
const level = ref("normal");
const engineThinking = ref(false);
```

3. 新增引擎走子逻辑：

```javascript
function movePayload() {
  return session.state.moves.map(({ chinese, check, gameOver, ...rest }) => rest);
}

async function runEngineMove() {
  if (engineThinking.value || session.state.gameOver) return;
  engineThinking.value = true;
  stopIntent();
  stopAnalysis();
  analysis.value = emptyAnalysis("idle");
  intent.value = emptyIntent("idle");
  try {
    const data = await api.bestMove({
      initial_fen: session.state.initialFen,
      moves: movePayload(),
      level: level.value,
    });
    if (disposed) return;
    if (data.legal) session.applyEngineMove(data.move);
    else session.state.hint = data.reason || "引擎未能走子";
  } catch (err) {
    if (!disposed) {
      session.state.hint = err?.response?.data?.detail || "引擎走子失败";
    }
  } finally {
    engineThinking.value = false;
  }
  if (disposed) return;
  startIntent();
}

async function enterAi(side) {
  if (
    session.state.moves.length &&
    !window.confirm("将清空当前对局，确定开始人机对战？")
  ) {
    return;
  }
  stopIntent();
  stopAnalysis();
  mode.value = "ai";
  engineSide.value = side;
  flipped.value = side === "red";
  session.reset({});
  if (side === "red") await runEngineMove();
  else startIntent();
}
```

4. 改造 `onCellClick`：

```javascript
async function onCellClick(x, y) {
  if (engineThinking.value) return;
  if (await session.click(x, y)) {
    if (mode.value === "ai" && !session.state.gameOver && session.state.sideToMove === engineSide.value) {
      await runEngineMove();
    } else {
      startIntent();
    }
  }
}
```

5. `undo` 保持原逻辑（逐步悔棋），但引擎模式下悔棋后若轮到引擎，不再自动走子（避免用户无法悔棋）。仅 `startIntent()`。

6. template 控件区新增：

```html
        <div class="ai-controls">
          <label class="level-label">
            难度
            <select v-model="level" data-test="level">
              <option v-for="l in LEVELS" :key="l.value" :value="l.value">{{ l.label }}</option>
            </select>
          </label>
          <button data-test="engine-red" :disabled="engineThinking" @click="enterAi('red')">引擎执红</button>
          <button data-test="engine-black" :disabled="engineThinking" @click="enterAi('black')">引擎执黑</button>
          <button data-test="edit" :disabled="engineThinking" @click="enterEdit">编辑局面</button>
        </div>
        <p v-if="engineThinking" class="warn" data-test="engine-thinking">引擎思考中…</p>
```

7. 样式新增：

```css
.ai-controls {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.ai-controls button {
  flex: 1 1 0;
  min-height: 44px;
}

.level-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
}

.level-label select {
  min-height: 40px;
}
```

> `enterEdit` 在 Task 7 实现；本 Task 先加占位函数 `function enterEdit() {}`，Task 7 替换。

**Step 4: 跑测试确认通过**

Run: `cd frontend && npx vitest run src/views/__tests__/PlayView.test.js`
Expected: PASS（含既有全部用例）

**Step 5: 提交**

```bash
git add frontend/src/views/PlayView.vue frontend/src/views/__tests__/PlayView.test.js
git commit -m "feat(frontend): 对弈页人机对战（引擎执红/执黑 + 三档难度）"
```

---

### Task 7: `PlayView` 局面编辑（摆子）

**Files:**
- Modify: `frontend/src/views/PlayView.vue`
- Test: `frontend/src/views/__tests__/PlayView.test.js`

**Step 1: 写失败测试**

```javascript
  it("进入编辑并落子、移除", async () => {
    const wrapper = mountView();
    await flushPromises();

    await button(wrapper, "edit").trigger("click");
    await nextTick();
    expect(wrapper.find('[data-test="editor-panel"]').exists()).toBe(true);

    await wrapper.find('[data-piece="black-R"]').trigger("click");
    await clickCells(wrapper, [0, 0]);
    expect(board(wrapper).props("position").pieces).toContainEqual(
      expect.objectContaining({ x: 0, y: 0, side: "black", kind: "R" })
    );

    await clickCells(wrapper, [0, 0]);
    expect(board(wrapper).props("position").pieces).not.toContainEqual(
      expect.objectContaining({ x: 0, y: 0, side: "black", kind: "R" })
    );
  });

  it("应用合法局面后以该 FEN 开局", async () => {
    const fen = "3k5/9/9/9/9/9/9/9/9/3K5 b - - 0 1";
    api.validatePosition.mockResolvedValue({ valid: true, fen });
    const wrapper = mountView();
    await flushPromises();

    await button(wrapper, "edit").trigger("click");
    await nextTick();
    await wrapper.find('[data-test="edit-side"]').setValue("black");
    await button(wrapper, "edit-apply").trigger("click");
    await flushPromises();

    expect(api.validatePosition).toHaveBeenCalledWith(
      expect.objectContaining({ side_to_move: "black" })
    );
    expect(wrapper.find('[data-test="editor-panel"]').exists()).toBe(false);
    expect(wrapper.find('[data-test="turn"]').text()).toContain("黑方走棋");
  });

  it("应用非法局面时展示错误并停留在编辑", async () => {
    api.validatePosition.mockResolvedValue({ valid: false, errors: ["红方必须有且仅有一个帅"] });
    const wrapper = mountView();
    await flushPromises();

    await button(wrapper, "edit").trigger("click");
    await nextTick();
    await button(wrapper, "edit-apply").trigger("click");
    await flushPromises();

    expect(wrapper.find('[data-test="edit-error"]').text()).toContain("红方必须有且仅有一个帅");
    expect(wrapper.find('[data-test="editor-panel"]').exists()).toBe(true);
  });

  it("已有对局时进入编辑需确认，取消则不变", async () => {
    const wrapper = mountView();
    await flushPromises();
    await clickCells(wrapper, [1, 2], [4, 2]);
    await flushPromises();

    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
    await button(wrapper, "edit").trigger("click");
    await nextTick();
    expect(wrapper.find('[data-test="editor-panel"]').exists()).toBe(false);
    confirmSpy.mockRestore();
  });
```

**Step 2: 跑测试确认失败**

Run: `cd frontend && npx vitest run src/views/__tests__/PlayView.test.js`
Expected: FAIL（找不到 `[data-test="editor-panel"]`）

**Step 3: 实现**

1. 新增状态：

```javascript
const editing = ref(false);
const editPieces = ref([]);
const palette = ref(null);
const editSide = ref("red");
const editError = ref([]);
```

2. 替换 Task 6 的 `enterEdit` 占位：

```javascript
function enterEdit() {
  if (
    session.state.moves.length &&
    !window.confirm("将清空当前对局，确定进入编辑局面？")
  ) {
    return;
  }
  stopIntent();
  stopAnalysis();
  analysis.value = emptyAnalysis("idle");
  intent.value = emptyIntent("idle");
  mode.value = "human";
  engineSide.value = null;
  engineThinking.value = false;
  editPieces.value = session.state.pieces.map((p) => ({ ...p }));
  palette.value = null;
  editError.value = [];
  editSide.value = session.state.sideToMove;
  editing.value = true;
}

function onEditClick(x, y) {
  if (palette.value) {
    const { side, kind } = palette.value;
    editPieces.value = [
      ...editPieces.value.filter((p) => !(p.x === x && p.y === y)),
      { x, y, side, kind, label: LABELS[`${side}-${kind}`] },
    ];
    return;
  }
  editPieces.value = editPieces.value.filter((p) => !(p.x === x && p.y === y));
}

function loadInitialEdit() {
  editPieces.value = fenToPieces(INITIAL_FEN);
  palette.value = null;
}

async function applyPosition() {
  editError.value = [];
  try {
    const data = await api.validatePosition({
      pieces: editPieces.value.map(({ x, y, side, kind }) => ({ x, y, side, kind })),
      side_to_move: editSide.value,
    });
    if (disposed) return;
    if (!data.valid) {
      editError.value = data.errors || ["局面不合法"];
      return;
    }
    editing.value = false;
    palette.value = null;
    session.reset({ initial_fen: data.fen });
    startIntent();
  } catch (err) {
    editError.value = [err?.response?.data?.detail || "校验失败，请重试"];
  }
}
```

3. `onCellClick` 顶部增加编辑分派：

```javascript
async function onCellClick(x, y) {
  if (editing.value) return onEditClick(x, y);
  if (engineThinking.value) return;
  ...
}
```

4. 导入 `LABELS`：

```javascript
import { INITIAL_FEN, LABELS, fenToPieces } from "../utils/chess";
```

5. 棋盘绑定改为编辑态切换：

```html
      <ChessBoard
        :position="{ pieces: editing ? editPieces : session.state.pieces }"
        :selected="editing ? null : session.state.selected"
        :arrows="editing ? [] : arrows"
        :flipped="flipped"
        @cell-click="onCellClick"
      />
```

6. 控件区下方新增编辑面板：

```html
        <div v-if="editing" class="editor-panel" data-test="editor-panel">
          <PiecePalette
            :selected="palette"
            @select="palette = $event"
            @clear="editPieces = []"
            @initial="loadInitialEdit"
          />
          <label class="level-label">
            行棋方
            <select v-model="editSide" data-test="edit-side">
              <option value="red">红先</option>
              <option value="black">黑先</option>
            </select>
          </label>
          <p v-for="(err, i) in editError" :key="i" class="warn" data-test="edit-error">{{ err }}</p>
          <div class="modal-actions">
            <button data-test="edit-cancel" @click="editing = false">取消</button>
            <button data-test="edit-apply" @click="applyPosition">应用局面</button>
          </div>
        </div>
```

7. 样式新增：

```css
.editor-panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
  background: #faf6ee;
  border: 1px solid #e6ddcc;
  border-radius: 10px;
  padding: 12px;
}
```

> 编辑态下「悔棋 / 翻转 / 保存 / 人机入口」按钮保留可见即可；点击棋盘由 `onEditClick` 分派，不影响 session。

**Step 4: 跑测试确认通过**

Run: `cd frontend && npx vitest run src/views/__tests__/PlayView.test.js`
Expected: PASS（含既有与 Task 6 全部用例）

**Step 5: 跑全量前端测试**

Run: `cd frontend && npm test`
Expected: 全部通过

**Step 6: 提交**

```bash
git add frontend/src/views/PlayView.vue frontend/src/views/__tests__/PlayView.test.js
git commit -m "feat(frontend): 对弈页局面编辑与摆子规则校验"
```

---

### Task 8: 文档更新与全量回归

**Files:**
- Modify: `README.md`（功能特性 / API 一览 / 已知限制 / 设计文档与实现计划）
- Modify: `docs/plans/2026-09-22-ai-play-and-board-editor-design.md`（如需与实际实现对齐）

**Step 1: 更新 README**

- 「功能特性」新增两条：
  - **人机对战**：对弈页可让引擎执红或执黑，三档难度（简单/普通/困难），引擎计算后自动走子；保留实时分析/意图面板。
  - **局面编辑**：对弈页可手动摆子（棋子面板选取 + 点击落子/移除），摆子局面经后端完整摆子规则校验，可选定行棋方后直接开局。
- 「API 一览」新增 `/api/engine/best-move` 与 `/api/engine/validate-position` 的请求/响应说明。
- 「已知限制」更新：人机对战为本地引擎、无联网；悔棋为逐步回退（不自动撤销引擎两步）；编辑局面不持久化。
- 「设计文档与实现计划」追加本功能两条链接。

**Step 2: 全量后端测试**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: 全部通过

**Step 3: 全量前端测试**

Run: `cd frontend && npm test`
Expected: 全部通过

**Step 4: 前端构建验证**

Run: `cd frontend && npm run build`
Expected: 构建成功，无报错

**Step 5: 提交**

```bash
git add README.md docs/plans/2026-09-22-ai-play-and-board-editor-design.md
git commit -m "docs: 人机对战与局面编辑文档与 README 对齐"
```

---

## 完成标准

- 后端新增 `validate-position`、`best-move` 两个端点，新增摆子规则模块，均有单测覆盖；
- 前端对弈页支持引擎执红/执黑、三档难度、引擎自动走子、摆子编辑与校验；
- 后端 `pytest`、前端 `npm test`、前端 `npm run build` 全部通过；
- README 与设计文档同步更新。
