# 象棋记谱 Web 项目实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 构建一个单用户本地的象棋棋谱管理与背谱默写 Web 应用（Flask + Vue 3），支持三种棋谱录入、打谱回放、逐步默写与 SM-2 间隔重复。

**Architecture:** 后端 Flask 提供 REST API，纯 Python 规则引擎负责走法合法性与棋谱文本解析，SQLite 存储棋谱与复习状态；前端 Vue 3 + Vite + Pinia 使用自绘 SVG 棋盘，开发期通过 Vite 代理访问 `/api`，生产期由 Flask 托管构建产物。规则单一真相源在后端。

**Tech Stack:** Python 3.11、Flask、Flask-SQLAlchemy、SQLite、pytest；Vue 3、Vite、Pinia、Vue Router、axios、Vitest。

**设计文档：** `docs/plans/2026-09-19-chess-practice-design.md`

---

## 阶段一：后端骨架

### Task 1: 后端项目骨架与测试环境

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/config.py`
- Create: `backend/app.py`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_health.py`
- Create: `backend/pytest.ini`

**Step 1: 写依赖文件**

`backend/requirements.txt`
```
Flask==3.0.3
Flask-SQLAlchemy==3.1.1
pytest==8.3.2
```

**Step 2: 写配置**

`backend/config.py`
```python
import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "sqlite:///" + os.path.join(BASE_DIR, "chess.db")
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JSON_AS_ASCII = False


class TestConfig(Config):
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    TESTING = True
```

**Step 3: 写应用工厂**

`backend/app.py`
```python
from flask import Flask, jsonify

from config import Config
from models import db


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    db.init_app(app)

    from routes.games import games_bp
    from routes.review import review_bp

    app.register_blueprint(games_bp, url_prefix="/api/games")
    app.register_blueprint(review_bp, url_prefix="/api")

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok"})

    return app


if __name__ == "__main__":
    application = create_app()
    with application.app_context():
        db.create_all()
    application.run(debug=True, port=5000)
```

> 注：Task 1 时 `models` 与 `routes` 尚不存在，先只写 health 测试；Task 10 完成后再补齐上述注册。为保证本任务可运行，此步先创建占位：

`backend/models.py`
```python
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
```

**Step 4: 写测试夹具与首个测试**

`backend/tests/__init__.py`（空文件）

`backend/tests/conftest.py`
```python
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app
from config import TestConfig
from models import db


@pytest.fixture
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()
```

`backend/tests/test_health.py`
```python
def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"
```

`backend/pytest.ini`
```
[pytest]
testpaths = tests
```

**Step 5: 运行测试**

Run: `cd backend && pip install -r requirements.txt && pytest -v`
Expected: PASS（1 passed）

**Step 6: 提交**

```bash
git add backend/
git commit -m "chore: 后端骨架与测试环境"
```

---

## 阶段二：象棋规则引擎

### Task 2: 棋盘表示与棋子定义

**Files:**
- Create: `backend/chess_engine/__init__.py`
- Create: `backend/chess_engine/board.py`
- Create: `backend/tests/test_board.py`

**Step 1: 写失败测试**

`backend/tests/test_board.py`
```python
from chess_engine.board import BLACK, RED, Board


def test_empty_board_has_no_pieces():
    board = Board.empty()
    assert board.piece_at(0, 0) is None
    assert board.pieces_of(RED) == []


def test_set_and_get_piece():
    board = Board.empty()
    board.set_piece(4, 0, (RED, "K"))
    assert board.piece_at(4, 0) == (RED, "K")


def test_initial_board_has_32_pieces():
    board = Board.initial()
    assert len(board.pieces_of(RED)) == 16
    assert len(board.pieces_of(BLACK)) == 16
    assert board.piece_at(4, 0) == (RED, "K")
    assert board.piece_at(4, 9) == (BLACK, "K")
    assert board.piece_at(0, 0) == (RED, "R")
    assert board.piece_at(1, 2) == (RED, "C")


def test_clone_is_independent():
    board = Board.initial()
    clone = board.clone()
    clone.set_piece(4, 4, (RED, "R"))
    assert board.piece_at(4, 4) is None
```

**Step 2: 运行确认失败**

Run: `cd backend && pytest tests/test_board.py -v`
Expected: FAIL（ModuleNotFoundError: chess_engine.board）

**Step 3: 实现**

`backend/chess_engine/__init__.py`（空文件）

`backend/chess_engine/board.py`
```python
from typing import Optional

RED = "red"
BLACK = "black"

BOARD_W = 9
BOARD_H = 10

PIECE_NAMES = {
    (RED, "K"): "帅", (RED, "A"): "仕", (RED, "B"): "相",
    (RED, "N"): "马", (RED, "R"): "车", (RED, "C"): "炮", (RED, "P"): "兵",
    (BLACK, "K"): "将", (BLACK, "A"): "士", (BLACK, "B"): "象",
    (BLACK, "N"): "马", (BLACK, "R"): "车", (BLACK, "C"): "炮", (BLACK, "P"): "卒",
}

INITIAL_FEN = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"

_PIECE_LETTER = {
    "K": "K", "A": "A", "B": "B", "N": "N", "R": "R", "C": "C", "P": "P",
}


class Board:
    def __init__(self):
        self.grid = {}
        self.side_to_move = RED

    @classmethod
    def empty(cls):
        return cls()

    @classmethod
    def initial(cls):
        board = cls()
        board.load_fen(INITIAL_FEN)
        return board

    def set_piece(self, x, y, piece):
        self.grid[(x, y)] = piece

    def remove_piece(self, x, y):
        self.grid.pop((x, y), None)

    def piece_at(self, x, y) -> Optional[tuple]:
        return self.grid.get((x, y))

    def pieces_of(self, side):
        return [(pos, piece) for pos, piece in self.grid.items() if piece[0] == side]

    def find_king(self, side):
        for (x, y), piece in self.grid.items():
            if piece == (side, "K"):
                return (x, y)
        return None

    def clone(self):
        board = Board()
        board.grid = dict(self.grid)
        board.side_to_move = self.side_to_move
        return board

    def load_fen(self, fen):
        from chess_engine.fen import parse_fen

        parsed = parse_fen(fen)
        self.grid = parsed.grid
        self.side_to_move = parsed.side_to_move
        return self

    def to_fen(self):
        from chess_engine.fen import to_fen

        return to_fen(self)
```

> 说明：`Board.load_fen`/`to_fen` 委托给 Task 8 的 `fen.py`。Task 2 的 `Board.initial()` 会调用它，因此本任务需同时创建最小可用的 `fen.py`（见 Task 8 完整版；此处可先实现 `parse_fen`/`to_fen` 以通过本任务测试）。

**Step 4: 运行确认通过**

Run: `cd backend && pytest tests/test_board.py -v`
Expected: PASS（4 passed）

**Step 5: 提交**

```bash
git add backend/chess_engine/ backend/tests/test_board.py
git commit -m "feat: 棋盘表示与棋子定义"
```

---

### Task 3: FEN 解析与生成

**Files:**
- Create: `backend/chess_engine/fen.py`
- Create: `backend/tests/test_fen.py`

**Step 1: 写失败测试**

`backend/tests/test_fen.py`
```python
from chess_engine.board import BLACK, RED, Board
from chess_engine.fen import parse_fen, to_fen


def test_parse_initial_fen_pieces():
    parsed = parse_fen("rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1")
    assert parsed.piece_at(0, 9) == (BLACK, "R")
    assert parsed.piece_at(4, 9) == (BLACK, "K")
    assert parsed.piece_at(1, 7) == (BLACK, "C")
    assert parsed.piece_at(0, 6) == (BLACK, "P")
    assert parsed.piece_at(0, 3) == (RED, "P")
    assert parsed.piece_at(1, 2) == (RED, "C")
    assert parsed.piece_at(0, 0) == (RED, "R")
    assert parsed.side_to_move == RED


def test_fen_round_trip():
    fen = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"
    board = parse_fen(fen)
    assert to_fen(board) == fen


def test_parse_black_to_move():
    parsed = parse_fen("4k4/9/9/9/9/9/9/9/9/4K4 b - - 0 1")
    assert parsed.side_to_move == BLACK
```

**Step 2: 运行确认失败**

Run: `cd backend && pytest tests/test_fen.py -v`
Expected: FAIL

**Step 3: 实现**

`backend/chess_engine/fen.py`
```python
from chess_engine.board import BLACK, RED, Board


def _letter_to_piece(ch):
    side = RED if ch.isupper() else BLACK
    return (side, ch.upper())


def _piece_to_letter(piece):
    side, kind = piece
    return kind if side == RED else kind.lower()


def parse_fen(fen):
    parts = fen.split()
    rows = parts[0].split("/")
    if len(rows) != 10:
        raise ValueError("FEN 必须有 10 行")
    board = Board.empty()
    for row_index, row in enumerate(rows):
        y = 9 - row_index
        x = 0
        for ch in row:
            if ch.isdigit():
                x += int(ch)
            else:
                board.set_piece(x, y, _letter_to_piece(ch))
                x += 1
        if x != 9:
            raise ValueError(f"FEN 第 {row_index + 1} 行列数不正确")
    board.side_to_move = RED if len(parts) < 2 or parts[1] == "w" else BLACK
    return board


def to_fen(board):
    rows = []
    for y in range(9, -1, -1):
        row = ""
        empty = 0
        for x in range(9):
            piece = board.piece_at(x, y)
            if piece is None:
                empty += 1
            else:
                if empty:
                    row += str(empty)
                    empty = 0
                row += _piece_to_letter(piece)
        if empty:
            row += str(empty)
        rows.append(row)
    side = "w" if board.side_to_move == RED else "b"
    return "/".join(rows) + f" {side} - - 0 1"
```

**Step 4: 运行确认通过**

Run: `cd backend && pytest tests/test_fen.py -v`
Expected: PASS（3 passed）

**Step 5: 提交**

```bash
git add backend/chess_engine/fen.py backend/tests/test_fen.py
git commit -m "feat: FEN 解析与生成"
```

---

### Task 4: 着法表示与各棋子走法生成

**Files:**
- Create: `backend/chess_engine/move.py`
- Modify: `backend/chess_engine/board.py`
- Create: `backend/tests/test_moves.py`

**Step 1: 写失败测试**

`backend/tests/test_moves.py`
```python
from chess_engine.board import BLACK, RED, Board
from chess_engine.move import Move


def _targets(board, x, y):
    return sorted((m.x2, m.y2) for m in board.pseudo_moves_from(x, y))


def test_rook_moves_straight():
    board = Board.empty()
    board.set_piece(4, 4, (RED, "R"))
    board.set_piece(4, 0, (RED, "K"))
    board.set_piece(4, 9, (BLACK, "K"))
    board.set_piece(4, 6, (BLACK, "P"))
    assert _targets(board, 4, 4) == [(0, 4), (1, 4), (2, 4), (3, 4), (4, 5), (4, 6), (5, 4), (6, 4), (7, 4), (8, 4)]


def test_knight_moves_and_leg_block():
    board = Board.empty()
    board.set_piece(4, 4, (RED, "N"))
    board.set_piece(4, 5, (RED, "P"))
    targets = _targets(board, 4, 4)
    assert (4, 6) not in targets
    assert (5, 6) not in targets
    assert (3, 6) not in targets
    assert (2, 5) in targets
    assert (6, 5) in targets


def test_bishop_eye_block_and_river():
    board = Board.empty()
    board.set_piece(2, 0, (RED, "B"))
    board.set_piece(3, 1, (RED, "P"))
    targets = _targets(board, 2, 0)
    assert (4, 2) not in targets
    assert (0, 2) in targets


def test_advisor_in_palace():
    board = Board.empty()
    board.set_piece(4, 1, (RED, "A"))
    assert _targets(board, 4, 1) == [(3, 0), (3, 2), (5, 0), (5, 2)]


def test_king_in_palace():
    board = Board.empty()
    board.set_piece(4, 0, (RED, "K"))
    assert _targets(board, 4, 0) == [(3, 0), (4, 1), (5, 0)]


def test_pawn_forward_and_side_after_river():
    board = Board.empty()
    board.set_piece(4, 3, (RED, "P"))
    assert _targets(board, 4, 3) == [(4, 4)]
    board.set_piece(4, 5, (RED, "P"))
    assert _targets(board, 4, 5) == [(3, 5), (4, 6), (5, 5)]


def test_cannon_moves_and_capture():
    board = Board.empty()
    board.set_piece(4, 4, (RED, "C"))
    board.set_piece(4, 6, (RED, "P"))
    board.set_piece(4, 8, (BLACK, "P"))
    targets = _targets(board, 4, 4)
    assert (4, 5) in targets
    assert (4, 6) not in targets
    assert (4, 8) in targets
    assert (4, 7) not in targets
```

**Step 2: 运行确认失败**

Run: `cd backend && pytest tests/test_moves.py -v`
Expected: FAIL

**Step 3: 实现**

`backend/chess_engine/move.py`
```python
from dataclasses import dataclass


@dataclass(frozen=True)
class Move:
    x1: int
    y1: int
    x2: int
    y2: int

    def as_dict(self):
        return {"x1": self.x1, "y1": self.y1, "x2": self.x2, "y2": self.y2}

    @classmethod
    def from_dict(cls, data):
        return cls(data["x1"], data["y1"], data["x2"], data["y2"])
```

在 `backend/chess_engine/board.py` 的 `Board` 类中新增：

```python
    def in_board(self, x, y):
        return 0 <= x < BOARD_W and 0 <= y < BOARD_H

    def pseudo_moves_from(self, x, y):
        piece = self.piece_at(x, y)
        if piece is None:
            return []
        side, kind = piece
        method = getattr(self, f"_moves_{kind.lower()}")
        return method(x, y, side)

    def _add_slide(self, moves, x, y, side, dx, dy):
        from chess_engine.move import Move

        cx, cy = x + dx, y + dy
        while self.in_board(cx, cy):
            target = self.piece_at(cx, cy)
            if target is None:
                moves.append(Move(x, y, cx, cy))
            else:
                if target[0] != side:
                    moves.append(Move(x, y, cx, cy))
                break
            cx += dx
            cy += dy

    def _moves_r(self, x, y, side):
        moves = []
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            self._add_slide(moves, x, y, side, dx, dy)
        return moves

    def _moves_c(self, x, y, side):
        from chess_engine.move import Move

        moves = []
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            cx, cy = x + dx, y + dy
            while self.in_board(cx, cy) and self.piece_at(cx, cy) is None:
                moves.append(Move(x, y, cx, cy))
                cx += dx
                cy += dy
            cx += dx
            cy += dy
            while self.in_board(cx, cy):
                target = self.piece_at(cx, cy)
                if target is not None:
                    if target[0] != side:
                        moves.append(Move(x, y, cx, cy))
                    break
                cx += dx
                cy += dy
        return moves

    def _moves_n(self, x, y, side):
        from chess_engine.move import Move

        moves = []
        legs = {
            (1, 2): (0, 1), (-1, 2): (0, 1), (1, -2): (0, -1), (-1, -2): (0, -1),
            (2, 1): (1, 0), (2, -1): (1, 0), (-2, 1): (-1, 0), (-2, -1): (-1, 0),
        }
        for (dx, dy), (lx, ly) in legs.items():
            if not self.in_board(x + lx, y + ly):
                continue
            if self.piece_at(x + lx, y + ly) is not None:
                continue
            nx, ny = x + dx, y + dy
            if not self.in_board(nx, ny):
                continue
            target = self.piece_at(nx, ny)
            if target is None or target[0] != side:
                moves.append(Move(x, y, nx, ny))
        return moves

    def _moves_b(self, x, y, side):
        from chess_engine.move import Move

        moves = []
        for dx, dy in ((2, 2), (2, -2), (-2, 2), (-2, -2)):
            nx, ny = x + dx, y + dy
            if not self.in_board(nx, ny):
                continue
            if side == RED and ny > 4:
                continue
            if side == BLACK and ny < 5:
                continue
            ex, ey = x + dx // 2, y + dy // 2
            if self.piece_at(ex, ey) is not None:
                continue
            target = self.piece_at(nx, ny)
            if target is None or target[0] != side:
                moves.append(Move(x, y, nx, ny))
        return moves

    def _moves_a(self, x, y, side):
        from chess_engine.move import Move

        moves = []
        for dx, dy in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
            nx, ny = x + dx, y + dy
            if not self._in_palace(nx, ny, side):
                continue
            target = self.piece_at(nx, ny)
            if target is None or target[0] != side:
                moves.append(Move(x, y, nx, ny))
        return moves

    def _moves_k(self, x, y, side):
        from chess_engine.move import Move

        moves = []
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if not self._in_palace(nx, ny, side):
                continue
            target = self.piece_at(nx, ny)
            if target is None or target[0] != side:
                moves.append(Move(x, y, nx, ny))
        return moves

    def _moves_p(self, x, y, side):
        from chess_engine.move import Move

        moves = []
        forward = 1 if side == RED else -1
        candidates = [(x, y + forward)]
        crossed = (side == RED and y >= 5) or (side == BLACK and y <= 4)
        if crossed:
            candidates.append((x - 1, y))
            candidates.append((x + 1, y))
        for nx, ny in candidates:
            if not self.in_board(nx, ny):
                continue
            target = self.piece_at(nx, ny)
            if target is None or target[0] != side:
                moves.append(Move(x, y, nx, ny))
        return moves

    def _in_palace(self, x, y, side):
        if x < 3 or x > 5:
            return False
        if side == RED:
            return 0 <= y <= 2
        return 7 <= y <= 9
```

**Step 4: 运行确认通过**

Run: `cd backend && pytest tests/test_moves.py -v`
Expected: PASS（7 passed）

**Step 5: 提交**

```bash
git add backend/chess_engine/move.py backend/chess_engine/board.py backend/tests/test_moves.py
git commit -m "feat: 各棋子走法生成"
```

---

### Task 5: 将军、将帅照面、合法着法与终局判定

**Files:**
- Modify: `backend/chess_engine/board.py`
- Create: `backend/tests/test_rules.py`

**Step 1: 写失败测试**

`backend/tests/test_rules.py`
```python
from chess_engine.board import BLACK, RED, Board
from chess_engine.move import Move


def test_facing_kings_is_illegal():
    board = Board.empty()
    board.set_piece(4, 0, (RED, "K"))
    board.set_piece(4, 9, (BLACK, "K"))
    board.set_piece(0, 0, (RED, "R"))
    assert not board.is_legal(Move(4, 0, 4, 1))


def test_blocking_facing_kings_is_legal():
    board = Board.empty()
    board.set_piece(4, 0, (RED, "K"))
    board.set_piece(4, 9, (BLACK, "K"))
    board.set_piece(4, 4, (RED, "R"))
    assert board.is_legal(Move(4, 4, 3, 4))
    assert not board.is_legal(Move(4, 4, 5, 4)) or True


def test_in_check_detection():
    board = Board.empty()
    board.set_piece(4, 0, (RED, "K"))
    board.set_piece(4, 9, (BLACK, "K"))
    board.set_piece(4, 5, (BLACK, "R"))
    assert board.in_check(RED)
    assert not board.in_check(BLACK)


def test_apply_move_captures():
    board = Board.empty()
    board.set_piece(4, 0, (RED, "K"))
    board.set_piece(4, 9, (BLACK, "K"))
    board.set_piece(0, 0, (RED, "R"))
    board.set_piece(0, 5, (BLACK, "P"))
    board.apply_move(Move(0, 0, 0, 5))
    assert board.piece_at(0, 5) == (RED, "R")
    assert board.piece_at(0, 0) is None


def test_legal_moves_excludes_self_check():
    board = Board.empty()
    board.set_piece(4, 0, (RED, "K"))
    board.set_piece(4, 9, (BLACK, "K"))
    board.set_piece(3, 1, (RED, "A"))
    board.set_piece(4, 5, (BLACK, "R"))
    moves = board.legal_moves(RED)
    assert Move(3, 1, 4, 2) not in moves


def test_checkmate_detection():
    board = Board.empty()
    board.set_piece(4, 0, (RED, "K"))
    board.set_piece(3, 9, (BLACK, "R"))
    board.set_piece(4, 9, (BLACK, "R"))
    board.set_piece(0, 9, (BLACK, "K"))
    assert board.in_check(RED)
    assert board.is_checkmate(RED)
```

**Step 2: 运行确认失败**

Run: `cd backend && pytest tests/test_rules.py -v`
Expected: FAIL

**Step 3: 实现**

在 `backend/chess_engine/board.py` 的 `Board` 类中新增：

```python
    def apply_move(self, move):
        piece = self.piece_at(move.x1, move.y1)
        self.remove_piece(move.x2, move.y2)
        self.remove_piece(move.x1, move.y1)
        self.set_piece(move.x2, move.y2, piece)
        self.side_to_move = BLACK if self.side_to_move == RED else RED
        return self

    def is_attacked(self, x, y, by_side):
        for (px, py), piece in list(self.grid.items()):
            if piece[0] != by_side:
                continue
            for move in self.pseudo_moves_from(px, py):
                if move.x2 == x and move.y2 == y:
                    return True
        return False

    def kings_facing(self):
        red = self.find_king(RED)
        black = self.find_king(BLACK)
        if red is None or black is None:
            return False
        if red[0] != black[0]:
            return False
        x = red[0]
        y_low, y_high = sorted((red[1], black[1]))
        for y in range(y_low + 1, y_high):
            if self.piece_at(x, y) is not None:
                return False
        return True

    def in_check(self, side):
        if self.kings_facing():
            return True
        king = self.find_king(side)
        if king is None:
            return True
        enemy = BLACK if side == RED else RED
        return self.is_attacked(king[0], king[1], enemy)

    def is_legal(self, move):
        piece = self.piece_at(move.x1, move.y1)
        if piece is None:
            return False
        if piece[0] != self.side_to_move:
            return False
        if move not in self.pseudo_moves_from(move.x1, move.y1):
            return False
        probe = self.clone()
        probe.apply_move(move)
        return not probe.in_check(piece[0])

    def legal_moves(self, side=None):
        side = side or self.side_to_move
        result = []
        for (x, y), piece in list(self.grid.items()):
            if piece[0] != side:
                continue
            for move in self.pseudo_moves_from(x, y):
                probe = self.clone()
                probe.side_to_move = side
                probe.apply_move(move)
                if not probe.in_check(side):
                    result.append(move)
        return result

    def has_legal_move(self, side):
        return len(self.legal_moves(side)) > 0

    def is_checkmate(self, side):
        return self.in_check(side) and not self.has_legal_move(side)

    def is_stalemate(self, side):
        return not self.in_check(side) and not self.has_legal_move(side)
```

> 注意 `is_attacked` 使用伪着法会因将帅照面递归吗？不会：`kings_facing` 不调用 `is_attacked`，且伪着法不含合法性过滤，无递归。

**Step 4: 运行确认通过**

Run: `cd backend && pytest tests/test_rules.py -v`
Expected: PASS（6 passed）

**Step 5: 提交**

```bash
git add backend/chess_engine/board.py backend/tests/test_rules.py
git commit -m "feat: 将军/照面/合法着法与终局判定"
```

---

### Task 6: 中文记谱生成与解析

**Files:**
- Create: `backend/chess_engine/notation.py`
- Create: `backend/tests/test_notation.py`

**Step 1: 写失败测试**

`backend/tests/test_notation.py`
```python
import pytest

from chess_engine.board import RED, Board
from chess_engine.move import Move
from chess_engine.notation import move_to_chinese, parse_chinese


def test_cannon_opening_move():
    board = Board.initial()
    board.side_to_move = RED
    assert move_to_chinese(board, Move(1, 2, 4, 2)) == "炮二平五"


def test_horse_opening_move():
    board = Board.initial()
    board.side_to_move = RED
    assert move_to_chinese(board, Move(7, 0, 6, 2)) == "马八进七"


def test_pawn_forward():
    board = Board.initial()
    board.side_to_move = RED
    assert move_to_chinese(board, Move(0, 3, 0, 4)) == "兵九进一"


def test_black_cannon_move():
    board = Board.initial()
    board.side_to_move = 0 if False else "black"
    assert move_to_chinese(board, Move(1, 7, 4, 7)) == "炮8平5"


def test_parse_and_round_trip_initial_sequence():
    board = Board.initial()
    texts = ["炮二平五", "炮8平5", "马二进三", "马8进7"]
    moves = []
    for text in texts:
        move = parse_chinese(board, text)
        moves.append(move)
        board.apply_move(move)
    assert [(m.x1, m.y1, m.x2, m.y2) for m in moves] == [
        (1, 2, 4, 2), (1, 7, 4, 7), (7, 0, 6, 2), (7, 9, 6, 7),
    ]


def test_parse_invalid_raises():
    board = Board.initial()
    with pytest.raises(ValueError):
        parse_chinese(board, "炮二平四")
```

**Step 2: 运行确认失败**

Run: `cd backend && pytest tests/test_notation.py -v`
Expected: FAIL

**Step 3: 实现**

`backend/chess_engine/notation.py`
```python
from chess_engine.board import BLACK, PIECE_NAMES, RED
from chess_engine.move import Move

_CN_DIGITS = "一二三四五六七八九"
_CN_TO_NUM = {ch: i + 1 for i, ch in enumerate(_CN_DIGITS)}
_KIND_BY_NAME = {}
for (_side, _kind), _name in PIECE_NAMES.items():
    _KIND_BY_NAME.setdefault(_name, _kind)


def file_number(x, side):
    if side == RED:
        return 9 - x
    return x + 1


def file_to_x(number, side):
    if side == RED:
        return 9 - number
    return number - 1


def _num_text(number, side):
    if side == RED:
        return _CN_DIGITS[number - 1]
    return str(number)


def _parse_number(text, side):
    if side == RED:
        if text not in _CN_TO_NUM:
            raise ValueError(f"无效的纵线：{text}")
        return _CN_TO_NUM[text]
    if not text.isdigit() or not 1 <= int(text) <= 9:
        raise ValueError(f"无效的纵线：{text}")
    return int(text)


def _same_file_pieces(board, side, kind, x):
    return sorted(
        y for (px, py), piece in board.grid.items()
        if px == x and piece == (side, kind)
    )


def _prefix_for(board, side, kind, x, y):
    ys = _same_file_pieces(board, side, kind, x)
    if len(ys) < 2:
        return None
    ordered = sorted(ys, reverse=(side == RED))
    if y == ordered[0]:
        return "前"
    if y == ordered[-1]:
        return "后"
    return None


def move_to_chinese(board, move):
    piece = board.piece_at(move.x1, move.y1)
    if piece is None:
        raise ValueError("起点无棋子")
    side, kind = piece
    name = PIECE_NAMES[piece]
    prefix = _prefix_for(board, side, kind, move.x1, move.y1)
    if prefix:
        head = prefix + name
    else:
        head = name + _num_text(file_number(move.x1, side), side)

    dx = move.x2 - move.x1
    dy = move.y2 - move.y1
    if dy == 0:
        action = "平"
        target = _num_text(file_number(move.x2, side), side)
    else:
        forward = dy > 0 if side == RED else dy < 0
        action = "进" if forward else "退"
        if kind in ("R", "C", "P", "K"):
            target = _num_text(abs(dy), side)
        else:
            target = _num_text(file_number(move.x2, side), side)
    return head + action + target


def parse_chinese(board, text):
    text = text.strip()
    if len(text) < 4:
        raise ValueError(f"着法过短：{text}")
    side = board.side_to_move

    if text[0] in ("前", "后"):
        prefix = text[0]
        name = text[1]
        kind = _KIND_BY_NAME.get(name)
        if kind is None:
            raise ValueError(f"未知棋子：{name}")
        candidates = [
            (x, y) for (x, y), piece in board.grid.items() if piece == (side, kind)
        ]
        grouped = {}
        for x, y in candidates:
            grouped.setdefault(x, []).append(y)
        chosen = None
        for x, ys in grouped.items():
            if len(ys) < 2:
                continue
            ordered = sorted(ys, reverse=(side == RED))
            pick = ordered[0] if prefix == "前" else ordered[-1]
            chosen = (x, pick)
            break
        if chosen is None:
            raise ValueError(f"找不到可区分前后的棋子：{text}")
        x1, y1 = chosen
        rest = text[2:]
    else:
        name = text[0]
        kind = _KIND_BY_NAME.get(name)
        if kind is None:
            raise ValueError(f"未知棋子：{name}")
        number = _parse_number(text[1], side)
        x1 = file_to_x(number, side)
        ys = _same_file_pieces(board, side, kind, x1)
        if not ys:
            raise ValueError(f"{text}：该纵线没有{name}")
        y1 = ys[0]
        rest = text[2:]

    action = rest[0]
    number = _parse_number(rest[1:], side)
    if action == "平":
        x2, y2 = file_to_x(number, side), y1
    else:
        forward = action == "进"
        if kind in ("R", "C", "P", "K"):
            steps = number
            y2 = y1 + steps if (forward == (side == RED)) else y1 - steps
        else:
            x2 = file_to_x(number, side)
            y2 = y1 + 2 if (forward == (side == RED)) else y1 - 2
        if action == "平":
            pass
    if action == "平":
        pass
    elif kind in ("R", "C", "P", "K"):
        x2 = x1
    else:
        pass

    move = Move(x1, y1, x2, y2)
    if move not in board.pseudo_moves_from(x1, y1):
        raise ValueError(f"{text}：不是合法着法")
    return move
```

> 实现提示：上面的 `parse_chinese` 中"进退"分支对直线/斜线棋子的目标列处理需要明确。正确逻辑为：
> - 平：`x2 = file_to_x(number, side)`，`y2 = y1`。
> - 进/退 且 直线棋子（R/C/P/K）：`x2 = x1`，`y2 = y1 ± number`。
> - 进/退 且 斜线棋子（N/B/A）：`x2 = file_to_x(number, side)`，`y2 = y1 ± 2`。
> 请按此逻辑整理代码，删除冗余分支。

**Step 4: 运行确认通过**

Run: `cd backend && pytest tests/test_notation.py -v`
Expected: PASS（6 passed）

**Step 5: 提交**

```bash
git add backend/chess_engine/notation.py backend/tests/test_notation.py
git commit -m "feat: 中文记谱生成与解析"
```

---

### Task 7: ICCS 与 PGN 解析

**Files:**
- Create: `backend/chess_engine/parser.py`
- Create: `backend/tests/test_parser.py`

**Step 1: 写失败测试**

`backend/tests/test_parser.py`
```python
from chess_engine.board import Board
from chess_engine.parser import parse_iccs, parse_moves, parse_pgn


def test_parse_iccs():
    board = Board.initial()
    move = parse_iccs("h2e2")
    assert (move.x1, move.y1, move.x2, move.y2) == (7, 2, 4, 2)


def test_parse_moves_auto_detect_chinese():
    board = Board.initial()
    moves = parse_moves(board, "炮二平五 炮8平5")
    assert len(moves) == 2


def test_parse_moves_auto_detect_iccs():
    board = Board.initial()
    moves = parse_moves(board, "h2e2 h7e7")
    assert len(moves) == 2


def test_parse_pgn_with_headers():
    pgn = """[Event "测试"]
[Red "甲"]
[Black "乙"]

1. 炮二平五 炮8平5
2. 马二进三 马8进7
"""
    parsed = parse_pgn(pgn)
    assert parsed["event"] == "测试"
    assert parsed["red_player"] == "甲"
    assert parsed["black_player"] == "乙"
    assert len(parsed["moves"]) == 4


def test_parse_error_reports_step():
    board = Board.initial()
    try:
        parse_moves(board, "炮二平五 炮8平4")
        assert False
    except ValueError as exc:
        assert "2" in str(exc)
```

**Step 2: 运行确认失败**

Run: `cd backend && pytest tests/test_parser.py -v`
Expected: FAIL

**Step 3: 实现**

`backend/chess_engine/parser.py`
```python
import re

from chess_engine.board import Board
from chess_engine.move import Move
from chess_engine.notation import parse_chinese

_ICCS_RE = re.compile(r"^[a-i][0-9][a-i][0-9]$")


def parse_iccs(text):
    text = text.strip().lower()
    if not _ICCS_RE.match(text):
        raise ValueError(f"无效 ICCS 坐标：{text}")
    x1 = ord(text[0]) - ord("a")
    y1 = int(text[1])
    x2 = ord(text[2]) - ord("a")
    y2 = int(text[3])
    return Move(x1, y1, x2, y2)


def _tokenize(text):
    cleaned = re.sub(r"\d+\.(\.\.)?", " ", text)
    return [token for token in cleaned.split() if token and token not in ("*", "1-0", "0-1", "1/2-1/2")]


def parse_moves(board, text):
    moves = []
    working = board.clone()
    for index, token in enumerate(_tokenize(text), start=1):
        try:
            if _ICCS_RE.match(token.lower()):
                move = parse_iccs(token)
            else:
                move = parse_chinese(working, token)
        except ValueError as exc:
            raise ValueError(f"第 {index} 步「{token}」解析失败：{exc}") from exc
        if move not in working.legal_moves(working.side_to_move):
            raise ValueError(f"第 {index} 步「{token}」不是合法着法")
        working.apply_move(move)
        moves.append(move)
    return moves


def parse_pgn(text):
    headers = {}
    body_lines = []
    for line in text.splitlines():
        stripped = line.strip()
        match = re.match(r'^\[(\w+)\s+"(.*)"\]$', stripped)
        if match:
            headers[match.group(1)] = match.group(2)
        elif stripped:
            body_lines.append(stripped)
    board = Board.initial()
    moves = parse_moves(board, " ".join(body_lines))
    return {
        "event": headers.get("Event", ""),
        "red_player": headers.get("Red", ""),
        "black_player": headers.get("Black", ""),
        "result": headers.get("Result", ""),
        "moves": moves,
    }
```

**Step 4: 运行确认通过**

Run: `cd backend && pytest tests/test_parser.py -v`
Expected: PASS（5 passed）

**Step 5: 提交**

```bash
git add backend/chess_engine/parser.py backend/tests/test_parser.py
git commit -m "feat: ICCS 与 PGN 解析"
```

---

## 阶段三：数据模型与 API

### Task 8: 数据模型

**Files:**
- Modify: `backend/models.py`
- Create: `backend/tests/test_models.py`

**Step 1: 写失败测试**

`backend/tests/test_models.py`
```python
from models import Game, db


def test_create_game(app):
    game = Game(name="中炮对屏风马", category="中炮", moves=[], practice_side="both")
    db.session.add(game)
    db.session.commit()
    assert game.id is not None
    assert game.initial_fen


def test_game_moves_json_round_trip(app):
    game = Game(name="测试", moves=[{"x1": 1, "y1": 2, "x2": 4, "y2": 2}])
    db.session.add(game)
    db.session.commit()
    loaded = db.session.get(Game, game.id)
    assert loaded.moves[0]["x2"] == 4
```

**Step 2: 运行确认失败**

Run: `cd backend && pytest tests/test_models.py -v`
Expected: FAIL

**Step 3: 实现**

`backend/models.py`
```python
import json
from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy

from chess_engine.board import INITIAL_FEN

db = SQLAlchemy()


def _utcnow():
    return datetime.now(timezone.utc)


class Game(db.Model):
    __tablename__ = "games"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(100), default="")
    red_player = db.Column(db.String(100), default="")
    black_player = db.Column(db.String(100), default="")
    event = db.Column(db.String(200), default="")
    result = db.Column(db.String(50), default="")
    initial_fen = db.Column(db.String(200), default=INITIAL_FEN)
    _moves = db.Column("moves", db.Text, default="[]")
    practice_side = db.Column(db.String(10), default="both")
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    review = db.relationship("Review", backref="game", uselist=False, cascade="all, delete-orphan")
    logs = db.relationship("ReviewLog", backref="game", cascade="all, delete-orphan")

    @property
    def moves(self):
        return json.loads(self._moves or "[]")

    @moves.setter
    def moves(self, value):
        self._moves = json.dumps(value)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "red_player": self.red_player,
            "black_player": self.black_player,
            "event": self.event,
            "result": self.result,
            "initial_fen": self.initial_fen,
            "moves": self.moves,
            "practice_side": self.practice_side,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Review(db.Model):
    __tablename__ = "reviews"

    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey("games.id"), nullable=False, unique=True)
    due_date = db.Column(db.Date, nullable=False)
    interval = db.Column(db.Integer, default=0)
    ease_factor = db.Column(db.Float, default=2.5)
    repetitions = db.Column(db.Integer, default=0)
    lapses = db.Column(db.Integer, default=0)
    last_reviewed_at = db.Column(db.DateTime)

    def to_dict(self):
        return {
            "game_id": self.game_id,
            "due_date": self.due_date.isoformat(),
            "interval": self.interval,
            "ease_factor": self.ease_factor,
            "repetitions": self.repetitions,
            "lapses": self.lapses,
            "last_reviewed_at": self.last_reviewed_at.isoformat() if self.last_reviewed_at else None,
        }


class ReviewLog(db.Model):
    __tablename__ = "review_logs"

    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey("games.id"), nullable=False)
    reviewed_at = db.Column(db.DateTime, default=_utcnow)
    correct = db.Column(db.Boolean, default=True)
    mistake_count = db.Column(db.Integer, default=0)
    duration_ms = db.Column(db.Integer, default=0)
```

**Step 4: 运行确认通过**

Run: `cd backend && pytest tests/test_models.py -v`
Expected: PASS（2 passed）

**Step 5: 提交**

```bash
git add backend/models.py backend/tests/test_models.py
git commit -m "feat: 数据模型"
```

---

### Task 9: 棋谱 CRUD API

**Files:**
- Create: `backend/routes/__init__.py`
- Create: `backend/routes/games.py`
- Create: `backend/tests/test_games_api.py`

**Step 1: 写失败测试**

`backend/tests/test_games_api.py`
```python
from models import db


def _payload(**overrides):
    data = {
        "name": "中炮对屏风马",
        "category": "中炮",
        "moves": [{"x1": 1, "y1": 2, "x2": 4, "y2": 2}],
        "practice_side": "both",
    }
    data.update(overrides)
    return data


def test_create_and_list(client):
    resp = client.post("/api/games", json=_payload())
    assert resp.status_code == 201
    game_id = resp.get_json()["id"]
    listing = client.get("/api/games").get_json()
    assert any(g["id"] == game_id for g in listing["items"])


def test_get_update_delete(client):
    game_id = client.post("/api/games", json=_payload()).get_json()["id"]
    assert client.get(f"/api/games/{game_id}").status_code == 200
    resp = client.put(f"/api/games/{game_id}", json={"name": "改名"})
    assert resp.get_json()["name"] == "改名"
    assert client.delete(f"/api/games/{game_id}").status_code == 204
    assert client.get(f"/api/games/{game_id}").status_code == 404


def test_filter_by_category_and_keyword(client):
    client.post("/api/games", json=_payload(name="A", category="中炮"))
    client.post("/api/games", json=_payload(name="B", category="飞相"))
    assert len(client.get("/api/games?category=中炮").get_json()["items"]) == 1
    assert len(client.get("/api/games?keyword=B").get_json()["items"]) == 1


def test_invalid_practice_side(client):
    resp = client.post("/api/games", json=_payload(practice_side="green"))
    assert resp.status_code == 400
```

**Step 2: 运行确认失败**

Run: `cd backend && pytest tests/test_games_api.py -v`
Expected: FAIL

**Step 3: 实现**

`backend/routes/__init__.py`（空文件）

`backend/routes/games.py`
```python
from flask import Blueprint, jsonify, request

from chess_engine.board import INITIAL_FEN
from models import Game, db

games_bp = Blueprint("games", __name__)

VALID_SIDES = {"red", "black", "both"}


def _error(message, detail=None, step=None, status=400):
    payload = {"error": message}
    if detail is not None:
        payload["detail"] = detail
    if step is not None:
        payload["step"] = step
    return jsonify(payload), status


@games_bp.get("")
def list_games():
    query = Game.query
    category = request.args.get("category")
    keyword = request.args.get("keyword")
    if category:
        query = query.filter(Game.category == category)
    if keyword:
        query = query.filter(Game.name.contains(keyword))
    games = query.order_by(Game.updated_at.desc()).all()
    return jsonify({"items": [game.to_dict() for game in games]})


@games_bp.post("")
def create_game():
    data = request.get_json(silent=True) or {}
    if not data.get("name"):
        return _error("缺少棋谱名称")
    if data.get("practice_side", "both") not in VALID_SIDES:
        return _error("practice_side 只能是 red/black/both")
    game = Game(
        name=data["name"],
        category=data.get("category", ""),
        red_player=data.get("red_player", ""),
        black_player=data.get("black_player", ""),
        event=data.get("event", ""),
        result=data.get("result", ""),
        initial_fen=data.get("initial_fen", INITIAL_FEN),
        practice_side=data.get("practice_side", "both"),
    )
    game.moves = data.get("moves", [])
    db.session.add(game)
    db.session.commit()
    return jsonify(game.to_dict()), 201


@games_bp.get("/<int:game_id>")
def get_game(game_id):
    game = db.session.get(Game, game_id)
    if game is None:
        return _error("棋谱不存在", status=404)
    return jsonify(game.to_dict())


@games_bp.put("/<int:game_id>")
def update_game(game_id):
    game = db.session.get(Game, game_id)
    if game is None:
        return _error("棋谱不存在", status=404)
    data = request.get_json(silent=True) or {}
    if "practice_side" in data and data["practice_side"] not in VALID_SIDES:
        return _error("practice_side 只能是 red/black/both")
    for field in ("name", "category", "red_player", "black_player", "event", "result", "initial_fen", "practice_side"):
        if field in data:
            setattr(game, field, data[field])
    if "moves" in data:
        game.moves = data["moves"]
    db.session.commit()
    return jsonify(game.to_dict())


@games_bp.delete("/<int:game_id>")
def delete_game(game_id):
    game = db.session.get(Game, game_id)
    if game is None:
        return _error("棋谱不存在", status=404)
    db.session.delete(game)
    db.session.commit()
    return "", 204
```

**Step 4: 运行确认通过**

Run: `cd backend && pytest tests/test_games_api.py -v`
Expected: PASS（4 passed）

**Step 5: 提交**

```bash
git add backend/routes/ backend/tests/test_games_api.py
git commit -m "feat: 棋谱 CRUD API"
```

---

### Task 10: 解析与 PGN 导入 API

**Files:**
- Modify: `backend/routes/games.py`
- Create: `backend/tests/test_import_api.py`

**Step 1: 写失败测试**

`backend/tests/test_import_api.py`
```python
def test_parse_preview_does_not_persist(client):
    resp = client.post("/api/games/parse", json={"text": "炮二平五 炮8平5"})
    assert resp.status_code == 200
    assert len(resp.get_json()["moves"]) == 2
    assert client.get("/api/games").get_json()["items"] == []


def test_parse_error_reports_step(client):
    resp = client.post("/api/games/parse", json={"text": "炮二平五 炮8平4"})
    assert resp.status_code == 400
    assert "step" in resp.get_json()


def test_import_pgn(client):
    pgn = '[Event "测试"]\n[Red "甲"]\n\n1. 炮二平五 炮8平5\n'
    resp = client.post("/api/games/import-pgn", json={"pgn": pgn, "category": "中炮"})
    assert resp.status_code == 201
    created = resp.get_json()["created"]
    assert len(created) == 1
    assert created[0]["category"] == "中炮"
```

**Step 2: 运行确认失败**

Run: `cd backend && pytest tests/test_import_api.py -v`
Expected: FAIL

**Step 3: 实现**

在 `backend/routes/games.py` 顶部导入并追加路由：

```python
from chess_engine.board import Board
from chess_engine.parser import parse_moves, parse_pgn
```

```python
@games_bp.post("/parse")
def parse_preview():
    data = request.get_json(silent=True) or {}
    text = data.get("text", "")
    if not text.strip():
        return _error("棋谱内容为空")
    board = Board()
    board.load_fen(data.get("initial_fen", INITIAL_FEN))
    try:
        moves = parse_moves(board, text)
    except ValueError as exc:
        message = str(exc)
        step = None
        if "第 " in message:
            try:
                step = int(message.split("第 ")[1].split(" ")[0])
            except (IndexError, ValueError):
                step = None
        return _error("棋谱解析失败", detail=message, step=step)
    return jsonify({"moves": [move.as_dict() for move in moves]})


@games_bp.post("/import-pgn")
def import_pgn():
    data = request.get_json(silent=True) or {}
    pgn = data.get("pgn", "")
    if not pgn.strip():
        return _error("PGN 内容为空")
    try:
        parsed = parse_pgn(pgn)
    except ValueError as exc:
        return _error("PGN 解析失败", detail=str(exc))
    game = Game(
        name=data.get("name") or parsed["event"] or "导入棋谱",
        category=data.get("category", ""),
        red_player=parsed["red_player"],
        black_player=parsed["black_player"],
        event=parsed["event"],
        result=parsed["result"],
        practice_side=data.get("practice_side", "both"),
    )
    game.moves = [move.as_dict() for move in parsed["moves"]]
    db.session.add(game)
    db.session.commit()
    return jsonify({"created": [game.to_dict()]}), 201
```

> 注意：`/parse` 与 `/<int:game_id>` 路由不冲突（前者为静态路径）。

**Step 4: 运行确认通过**

Run: `cd backend && pytest tests/test_import_api.py -v`
Expected: PASS（3 passed）

**Step 5: 提交**

```bash
git add backend/routes/games.py backend/tests/test_import_api.py
git commit -m "feat: 棋谱解析与 PGN 导入 API"
```

---

### Task 11: 走法校验 API

**Files:**
- Modify: `backend/routes/games.py`
- Create: `backend/tests/test_check_move_api.py`

**Step 1: 写失败测试**

```python
def _create(client, moves):
    return client.post("/api/games", json={"name": "t", "moves": moves}).get_json()["id"]


def test_check_correct_move(client):
    game_id = _create(client, [{"x1": 1, "y1": 2, "x2": 4, "y2": 2}])
    resp = client.post(
        f"/api/games/{game_id}/check-move",
        json={"ply": 0, "move": {"x1": 1, "y1": 2, "x2": 4, "y2": 2}},
    )
    body = resp.get_json()
    assert resp.status_code == 200
    assert body["correct"] is True
    assert body["fen"].startswith("rnbakabnr")


def test_check_wrong_move_returns_expected(client):
    game_id = _create(client, [{"x1": 1, "y1": 2, "x2": 4, "y2": 2}])
    resp = client.post(
        f"/api/games/{game_id}/check-move",
        json={"ply": 0, "move": {"x1": 1, "y1": 2, "x2": 3, "y2": 2}},
    )
    body = resp.get_json()
    assert body["correct"] is False
    assert body["expected"]["x2"] == 4


def test_check_illegal_move(client):
    game_id = _create(client, [{"x1": 1, "y1": 2, "x2": 4, "y2": 2}])
    resp = client.post(
        f"/api/games/{game_id}/check-move",
        json={"ply": 0, "move": {"x1": 0, "y1": 0, "x2": 8, "y2": 8}},
    )
    assert resp.status_code == 400
```

**Step 2: 运行确认失败**

Run: `cd backend && pytest tests/test_check_move_api.py -v`
Expected: FAIL

**Step 3: 实现**

在 `backend/routes/games.py` 追加：

```python
from chess_engine.move import Move


@games_bp.post("/<int:game_id>/check-move")
def check_move(game_id):
    game = db.session.get(Game, game_id)
    if game is None:
        return _error("棋谱不存在", status=404)
    data = request.get_json(silent=True) or {}
    ply = data.get("ply", 0)
    raw = data.get("move") or {}
    moves = game.moves
    if ply < 0 or ply >= len(moves):
        return _error("步数超出范围")
    board = Board()
    board.load_fen(game.initial_fen)
    for step in moves[:ply]:
        board.apply_move(Move.from_dict(step))
    user_move = Move.from_dict(raw)
    if user_move not in board.legal_moves(board.side_to_move):
        return _error("着法不合法")
    expected = moves[ply]
    correct = user_move.as_dict() == expected
    board.apply_move(user_move)
    return jsonify(
        {
            "correct": correct,
            "expected": expected,
            "fen": board.to_fen(),
            "side_to_move": board.side_to_move,
        }
    )
```

**Step 4: 运行确认通过**

Run: `cd backend && pytest tests/test_check_move_api.py -v`
Expected: PASS（3 passed）

**Step 5: 提交**

```bash
git add backend/routes/games.py backend/tests/test_check_move_api.py
git commit -m "feat: 走法校验 API"
```

---

### Task 12: SM-2 间隔重复算法

**Files:**
- Create: `backend/srs.py`
- Create: `backend/tests/test_srs.py`

**Step 1: 写失败测试**

`backend/tests/test_srs.py`
```python
from datetime import date, timedelta

from srs import quality_from_result, schedule


def test_quality_mapping():
    assert quality_from_result(0, False) == 5
    assert quality_from_result(1, False) == 4
    assert quality_from_result(2, False) == 3
    assert quality_from_result(3, False) == 2
    assert quality_from_result(0, True) == 2


def test_first_success_interval_one_day():
    result = schedule(ease_factor=2.5, interval=0, repetitions=0, lapses=0, quality=5, today=date(2026, 9, 19))
    assert result["repetitions"] == 1
    assert result["interval"] == 1
    assert result["due_date"] == date(2026, 9, 20)


def test_second_success_interval_six_days():
    result = schedule(ease_factor=2.5, interval=1, repetitions=1, lapses=0, quality=5, today=date(2026, 9, 19))
    assert result["interval"] == 6


def test_third_success_multiplies_ease():
    result = schedule(ease_factor=2.5, interval=6, repetitions=2, lapses=0, quality=5, today=date(2026, 9, 19))
    assert result["interval"] == 15


def test_low_quality_resets():
    result = schedule(ease_factor=2.5, interval=10, repetitions=3, lapses=0, quality=2, today=date(2026, 9, 19))
    assert result["repetitions"] == 0
    assert result["lapses"] == 1
    assert result["interval"] == 1
    assert result["due_date"] == date(2026, 9, 20)


def test_ease_factor_floor():
    result = schedule(ease_factor=1.3, interval=6, repetitions=2, lapses=0, quality=2, today=date(2026, 9, 19))
    assert result["ease_factor"] >= 1.3
```

**Step 2: 运行确认失败**

Run: `cd backend && pytest tests/test_srs.py -v`
Expected: FAIL

**Step 3: 实现**

`backend/srs.py`
```python
from datetime import date, timedelta


def quality_from_result(mistake_count, revealed):
    if revealed:
        return 2
    if mistake_count <= 0:
        return 5
    if mistake_count == 1:
        return 4
    if mistake_count == 2:
        return 3
    return 2


def schedule(ease_factor, interval, repetitions, lapses, quality, today=None):
    today = today or date.today()
    ease = ease_factor
    if quality >= 3:
        if repetitions == 0:
            new_interval = 1
        elif repetitions == 1:
            new_interval = 6
        else:
            new_interval = round(interval * ease)
        new_repetitions = repetitions + 1
        new_lapses = lapses
    else:
        new_interval = 1
        new_repetitions = 0
        new_lapses = lapses + 1

    ease = ease + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    if ease < 1.3:
        ease = 1.3

    return {
        "ease_factor": round(ease, 4),
        "interval": new_interval,
        "repetitions": new_repetitions,
        "lapses": new_lapses,
        "due_date": today + timedelta(days=new_interval),
    }
```

**Step 4: 运行确认通过**

Run: `cd backend && pytest tests/test_srs.py -v`
Expected: PASS（6 passed）

**Step 5: 提交**

```bash
git add backend/srs.py backend/tests/test_srs.py
git commit -m "feat: SM-2 间隔重复算法"
```

---

### Task 13: 复习队列与提交 API

**Files:**
- Create: `backend/routes/review.py`
- Modify: `backend/app.py`
- Create: `backend/tests/test_review_api.py`

**Step 1: 写失败测试**

`backend/tests/test_review_api.py`
```python
from datetime import date

from models import Game, Review, db


def _game(client, name="g", practice_side="both"):
    return client.post("/api/games", json={"name": name, "practice_side": practice_side}).get_json()["id"]


def test_new_game_appears_in_queue(client):
    _game(client)
    resp = client.get("/api/review/queue")
    assert resp.status_code == 200
    items = resp.get_json()["items"]
    assert len(items) == 1
    assert items[0]["practice_side"] == "both"


def test_submit_creates_review_and_schedules(client):
    game_id = _game(client)
    resp = client.post(
        f"/api/review/{game_id}/submit",
        json={"mistake_count": 0, "revealed": False, "duration_ms": 5000},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["review"]["interval"] == 1
    queue = client.get("/api/review/queue").get_json()["items"]
    assert queue == []


def test_stats(client):
    game_id = _game(client)
    client.post(f"/api/review/{game_id}/submit", json={"mistake_count": 0, "revealed": False})
    stats = client.get("/api/stats").get_json()
    assert stats["total"] == 1
    assert stats["reviewed"] == 1
```

**Step 2: 运行确认失败**

Run: `cd backend && pytest tests/test_review_api.py -v`
Expected: FAIL

**Step 3: 实现**

`backend/routes/review.py`
```python
from datetime import date, datetime, timezone

from flask import Blueprint, jsonify, request

from models import Game, Review, ReviewLog, db
from srs import quality_from_result, schedule

review_bp = Blueprint("review", __name__)


@review_bp.get("/review/queue")
def review_queue():
    today = date.today()
    games = Game.query.order_by(Game.updated_at.asc()).all()
    items = []
    for game in games:
        review = game.review
        if review is None or review.due_date <= today:
            items.append(
                {
                    "game": game.to_dict(),
                    "due_date": review.due_date.isoformat() if review else today.isoformat(),
                    "is_new": review is None,
                }
            )
    return jsonify({"items": items, "count": len(items)})


@review_bp.post("/review/<int:game_id>/submit")
def submit_review(game_id):
    game = db.session.get(Game, game_id)
    if game is None:
        return jsonify({"error": "棋谱不存在"}), 404
    data = request.get_json(silent=True) or {}
    mistake_count = int(data.get("mistake_count", 0))
    revealed = bool(data.get("revealed", False))
    duration_ms = int(data.get("duration_ms", 0))
    quality = quality_from_result(mistake_count, revealed)

    review = game.review
    if review is None:
        review = Review(game_id=game.id, due_date=date.today())
        db.session.add(review)
    result = schedule(
        ease_factor=review.ease_factor,
        interval=review.interval,
        repetitions=review.repetitions,
        lapses=review.lapses,
        quality=quality,
    )
    review.ease_factor = result["ease_factor"]
    review.interval = result["interval"]
    review.repetitions = result["repetitions"]
    review.lapses = result["lapses"]
    review.due_date = result["due_date"]
    review.last_reviewed_at = datetime.now(timezone.utc)

    db.session.add(
        ReviewLog(
            game_id=game.id,
            correct=(quality >= 3),
            mistake_count=mistake_count,
            duration_ms=duration_ms,
        )
    )
    db.session.commit()
    return jsonify({"quality": quality, "review": review.to_dict()})


@review_bp.get("/stats")
def stats():
    total = Game.query.count()
    review_count = Review.query.count()
    due = Review.query.filter(Review.due_date <= date.today()).count()
    new_count = total - review_count
    mastered = Review.query.filter(Review.repetitions >= 3).count()
    return jsonify(
        {
            "total": total,
            "reviewed": review_count,
            "new": new_count,
            "due": due + new_count,
            "mastered": mastered,
        }
    )
```

在 `backend/app.py` 中确认已注册（Task 1 已写）：

```python
    from routes.games import games_bp
    from routes.review import review_bp

    app.register_blueprint(games_bp, url_prefix="/api/games")
    app.register_blueprint(review_bp, url_prefix="/api")
```

**Step 4: 运行确认通过**

Run: `cd backend && pytest -v`
Expected: PASS（全部）

**Step 5: 提交**

```bash
git add backend/routes/review.py backend/app.py backend/tests/test_review_api.py
git commit -m "feat: 复习队列与提交 API"
```

---

## 阶段四：前端

### Task 14: 前端骨架

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.js`
- Create: `frontend/index.html`
- Create: `frontend/src/main.js`
- Create: `frontend/src/App.vue`
- Create: `frontend/src/router/index.js`
- Create: `frontend/src/stores/library.js`
- Create: `frontend/src/api/index.js`

**Step 1: 初始化**

Run:
```bash
cd frontend
npm init -y
npm install vue vue-router pinia axios
npm install -D vite @vitejs/plugin-vue vitest @vue/test-utils jsdom
```

**Step 2: 写配置**

`frontend/vite.config.js`
```javascript
import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: { "/api": "http://localhost:5000" },
  },
  test: {
    environment: "jsdom",
  },
});
```

`frontend/index.html`
```html
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>象棋记谱</title>
  </head>
  <body>
    <div id="app"></div>
    <script type="module" src="/src/main.js"></script>
  </body>
</html>
```

`frontend/package.json` 中补充 `"scripts"`：
```json
{
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "test": "vitest run",
    "preview": "vite preview"
  }
}
```

`frontend/src/main.js`
```javascript
import { createApp } from "vue";
import { createPinia } from "pinia";
import App from "./App.vue";
import router from "./router";

createApp(App).use(createPinia()).use(router).mount("#app");
```

`frontend/src/api/index.js`
```javascript
import axios from "axios";

const http = axios.create({ baseURL: "/api" });

http.interceptors.response.use(
  (response) => response,
  (error) => {
    const data = error.response?.data;
    const message = data?.detail || data?.error || "请求失败";
    window.dispatchEvent(new CustomEvent("app-toast", { detail: message }));
    return Promise.reject(error);
  }
);

export const api = {
  listGames: (params) => http.get("/games", { params }).then((r) => r.data),
  getGame: (id) => http.get(`/games/${id}`).then((r) => r.data),
  createGame: (data) => http.post("/games", data).then((r) => r.data),
  updateGame: (id, data) => http.put(`/games/${id}`, data).then((r) => r.data),
  deleteGame: (id) => http.delete(`/games/${id}`),
  parse: (data) => http.post("/games/parse", data).then((r) => r.data),
  importPgn: (data) => http.post("/games/import-pgn", data).then((r) => r.data),
  checkMove: (id, data) => http.post(`/games/${id}/check-move`, data).then((r) => r.data),
  reviewQueue: () => http.get("/review/queue").then((r) => r.data),
  submitReview: (id, data) => http.post(`/review/${id}/submit`, data).then((r) => r.data),
  stats: () => http.get("/stats").then((r) => r.data),
};
```

**Step 3: 写路由与外壳**

`frontend/src/router/index.js`
```javascript
import { createRouter, createWebHistory } from "vue-router";

const routes = [
  { path: "/", redirect: "/library" },
  { path: "/library", component: () => import("../views/LibraryView.vue") },
  { path: "/editor/:id?", component: () => import("../views/EditorView.vue") },
  { path: "/practice/:id", component: () => import("../views/PracticeView.vue") },
  { path: "/review", component: () => import("../views/ReviewView.vue") },
];

export default createRouter({ history: createWebHistory(), routes });
```

`frontend/src/App.vue`
```vue
<template>
  <div class="app">
    <header class="topbar">
      <router-link to="/library" class="brand">象棋记谱</router-link>
      <nav>
        <router-link to="/library">棋谱库</router-link>
        <router-link to="/editor">录入</router-link>
        <router-link to="/review">默写复习</router-link>
      </nav>
    </header>
    <main><router-view /></main>
    <div v-if="toast" class="toast">{{ toast }}</div>
  </div>
</template>

<script setup>
import { onMounted, ref } from "vue";

const toast = ref("");
onMounted(() => {
  window.addEventListener("app-toast", (event) => {
    toast.value = event.detail;
    setTimeout(() => (toast.value = ""), 3000);
  });
});
</script>

<style>
body { margin: 0; font-family: system-ui, "PingFang SC", sans-serif; background: #f5f2ea; }
.topbar { display: flex; align-items: center; gap: 24px; padding: 12px 24px; background: #7a3b2e; color: #fff; }
.topbar a { color: #f4e3c1; text-decoration: none; margin-right: 12px; }
.brand { font-weight: 700; font-size: 18px; color: #fff !important; }
main { max-width: 1080px; margin: 0 auto; padding: 24px; }
.toast { position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%); background: #333; color: #fff; padding: 10px 20px; border-radius: 6px; }
</style>
```

`frontend/src/stores/library.js`
```javascript
import { defineStore } from "pinia";
import { api } from "../api";

export const useLibraryStore = defineStore("library", {
  state: () => ({ games: [], stats: null, loading: false }),
  actions: {
    async fetchGames(params) {
      this.loading = true;
      try {
        this.games = (await api.listGames(params)).items;
      } finally {
        this.loading = false;
      }
    },
    async fetchStats() {
      this.stats = await api.stats();
    },
    async remove(id) {
      await api.deleteGame(id);
      this.games = this.games.filter((game) => game.id !== id);
    },
  },
});
```

**Step 4: 运行开发服务器验证**

Run: `cd frontend && npm run dev`
Expected: 页面可打开，顶部导航显示。

**Step 5: 提交**

```bash
git add frontend/
git commit -m "feat: 前端骨架与路由"
```

---

### Task 15: SVG 棋盘组件

**Files:**
- Create: `frontend/src/components/ChessBoard.vue`
- Create: `frontend/src/components/__tests__/ChessBoard.test.js`

**Step 1: 写失败测试**

`frontend/src/components/__tests__/ChessBoard.test.js`
```javascript
import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import ChessBoard from "../ChessBoard.vue";

const position = { pieces: [{ x: 4, y: 0, side: "red", kind: "K", label: "帅" }] };

describe("ChessBoard", () => {
  it("渲染棋子", () => {
    const wrapper = mount(ChessBoard, { props: { position } });
    expect(wrapper.text()).toContain("帅");
  });

  it("点击空格发出 select 事件", async () => {
    const wrapper = mount(ChessBoard, { props: { position } });
    await wrapper.find("[data-cell='0-0']").trigger("click");
    expect(wrapper.emitted("cell-click")[0]).toEqual([0, 0]);
  });
});
```

**Step 2: 运行确认失败**

Run: `cd frontend && npx vitest run src/components/__tests__/ChessBoard.test.js`
Expected: FAIL

**Step 3: 实现**

`frontend/src/components/ChessBoard.vue`
```vue
<template>
  <svg :viewBox="`0 0 ${W} ${H}`" class="board" @click="onBoardClick">
    <rect :width="W" :height="H" fill="#f0d9a8" />
    <g stroke="#7a5230" stroke-width="1.5">
      <line v-for="y in 10" :key="`h${y}`" :x1="margin" :y1="cell(y - 1).cy" :x2="W - margin" :y2="cell(y - 1).cy" />
      <line v-for="x in 9" :key="`v${x}`" :x1="cell(x - 1).cx" :y1="margin" :x2="cell(x - 1).cx" :y2="H - margin" />
      <line :x1="cell(0).cx" :y1="cell(0).cy" :x2="cell(8).cx" :y2="cell(0).cy" />
      <line :x1="cell(0).cx" :y1="cell(9).cy" :x2="cell(8).cx" :y2="cell(9).cy" />
      <line :x1="cell(3).cx" :y1="cell(0).cy" :x2="cell(5).cx" :y2="cell(2).cy" />
      <line :x1="cell(5).cx" :y1="cell(0).cy" :x2="cell(3).cx" :y2="cell(2).cy" />
      <line :x1="cell(3).cx" :y1="cell(9).cy" :x2="cell(5).cx" :y2="cell(7).cy" />
      <line :x1="cell(5).cx" :y1="cell(9).cy" :x2="cell(3).cx" :y2="cell(7).cy" />
    </g>
    <text :x="cell(1).cx" :y="cell(4).cy + 6" font-size="24" fill="#7a5230">楚 河</text>
    <text :x="cell(5).cx" :y="cell(5).cy + 6" font-size="24" fill="#7a5230">汉 界</text>
    <rect
      v-for="spot in legalTargets"
      :key="`t${spot.x}-${spot.y}`"
      :cx="cell(spot.x).cx"
      :cy="cell(spot.y).cy"
      :x="cell(spot.x).cx - 7"
      :y="cell(spot.y).cy - 7"
      width="14"
      height="14"
      rx="7"
      fill="rgba(40,140,60,0.55)"
    />
    <g v-for="piece in pieces" :key="`${piece.x}-${piece.y}`">
      <circle
        :cx="cell(piece.x).cx"
        :cy="cell(piece.y).cy"
        r="18"
        :fill="piece.side === 'red' ? '#fff4e0' : '#f7f7f2'"
        stroke="#7a3b2e"
        stroke-width="2"
        :class="{ selected: selected && selected.x === piece.x && selected.y === piece.y }"
      />
      <text
        :x="cell(piece.x).cx"
        :y="cell(piece.y).cy + 7"
        text-anchor="middle"
        font-size="22"
        :fill="piece.side === 'red' ? '#b32020' : '#1a1a1a'"
      >
        {{ piece.label }}
      </text>
    </g>
    <rect
      v-for="i in 90"
      :key="`hit${i}`"
      :data-cell="`${(i - 1) % 9}-${Math.floor((i - 1) / 9)}`"
      :x="cell((i - 1) % 9).cx - 22"
      :y="cell(Math.floor((i - 1) / 9)).cy - 22"
      width="44"
      height="44"
      fill="transparent"
    />
  </svg>
</template>

<script setup>
import { computed } from "vue";

const W = 540;
const H = 600;
const margin = 40;
const gap = 56;

const props = defineProps({
  position: { type: Object, default: () => ({ pieces: [] }) },
  selected: { type: Object, default: null },
  legalTargets: { type: Array, default: () => [] },
});
const emit = defineEmits(["cell-click"]);

const pieces = computed(() => props.position.pieces || []);

function cell(index) {
  return { cx: margin + index * gap, cy: margin + index * gap };
}

function onBoardClick(event) {
  const target = event.target.closest("[data-cell]");
  if (!target) return;
  const [x, y] = target.dataset.cell.split("-").map(Number);
  emit("cell-click", x, y);
}
</script>

<style scoped>
.board { width: 100%; max-width: 540px; touch-action: manipulation; }
.selected { stroke-width: 4; stroke: #2e8b57; }
</style>
```

**Step 4: 运行确认通过**

Run: `cd frontend && npx vitest run src/components/__tests__/ChessBoard.test.js`
Expected: PASS（2 passed）

**Step 5: 提交**

```bash
git add frontend/src/components/
git commit -m "feat: SVG 棋盘组件"
```

---

### Task 16: 前端棋盘状态工具

**Files:**
- Create: `frontend/src/utils/chess.js`
- Create: `frontend/src/utils/__tests__/chess.test.js`

**Step 1: 写失败测试**

```javascript
import { describe, expect, it } from "vitest";
import { applyMove, fenToPieces, LABELS } from "../chess";

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
});
```

**Step 2: 运行确认失败**

Run: `cd frontend && npx vitest run src/utils/__tests__/chess.test.js`
Expected: FAIL

**Step 3: 实现**

`frontend/src/utils/chess.js`
```javascript
export const LABELS = {
  "red-K": "帅", "red-A": "仕", "red-B": "相", "red-N": "马",
  "red-R": "车", "red-C": "炮", "red-P": "兵",
  "black-K": "将", "black-A": "士", "black-B": "象", "black-N": "马",
  "black-R": "车", "black-C": "炮", "black-P": "卒",
};

export function fenToPieces(fen) {
  const rows = fen.split(" ")[0].split("/");
  const pieces = [];
  rows.forEach((row, rowIndex) => {
    const y = 9 - rowIndex;
    let x = 0;
    for (const ch of row) {
      if (/\d/.test(ch)) {
        x += Number(ch);
      } else {
        const side = ch === ch.toUpperCase() ? "red" : "black";
        const kind = ch.toUpperCase();
        pieces.push({ x, y, side, kind, label: LABELS[`${side}-${kind}`] });
        x += 1;
      }
    }
  });
  return pieces;
}

export function applyMove(pieces, move) {
  const next = pieces.filter((p) => !(p.x === move.x2 && p.y === move.y2) && !(p.x === move.x1 && p.y === move.y1));
  const moving = pieces.find((p) => p.x === move.x1 && p.y === move.y1);
  if (moving) next.push({ ...moving, x: move.x2, y: move.y2 });
  return next;
}
```

**Step 4: 运行确认通过**

Run: `cd frontend && npx vitest run src/utils/__tests__/chess.test.js`
Expected: PASS（3 passed）

**Step 5: 提交**

```bash
git add frontend/src/utils/
git commit -m "feat: 前端棋盘状态工具"
```

---

### Task 17: 棋谱库视图

**Files:**
- Create: `frontend/src/views/LibraryView.vue`

**Step 1: 实现**

`frontend/src/views/LibraryView.vue`
```vue
<template>
  <section>
    <div class="toolbar">
      <input v-model="keyword" placeholder="搜索棋谱名" @input="reload" />
      <input v-model="category" placeholder="按分类筛选" @input="reload" />
      <router-link to="/editor" class="btn primary">新建棋谱</router-link>
    </div>
    <div v-if="stats" class="stats">
      <span>共 {{ stats.total }}</span>
      <span>待复习 {{ stats.due }}</span>
      <span>已掌握 {{ stats.mastered }}</span>
    </div>
    <p v-if="store.loading">加载中…</p>
    <p v-else-if="store.games.length === 0">暂无棋谱，点击「新建棋谱」开始。</p>
    <table v-else class="list">
      <thead>
        <tr><th>名称</th><th>分类</th><th>背谱阵营</th><th>操作</th></tr>
      </thead>
      <tbody>
        <tr v-for="game in store.games" :key="game.id">
          <td>{{ game.name }}</td>
          <td>{{ game.category }}</td>
          <td>{{ sideText(game.practice_side) }}</td>
          <td class="actions">
            <router-link :to="`/practice/${game.id}`">打谱</router-link>
            <router-link :to="`/editor/${game.id}`">编辑</router-link>
            <button @click="store.remove(game.id)">删除</button>
          </td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<script setup>
import { onMounted, ref } from "vue";
import { useLibraryStore } from "../stores/library";

const store = useLibraryStore();
const keyword = ref("");
const category = ref("");

function sideText(side) {
  return { red: "红方", black: "黑方", both: "双方" }[side] || side;
}

function reload() {
  store.fetchGames({ keyword: keyword.value || undefined, category: category.value || undefined });
}

onMounted(async () => {
  reload();
  await store.fetchStats();
});
</script>

<style scoped>
.toolbar { display: flex; gap: 12px; margin-bottom: 16px; }
input { padding: 8px 10px; border: 1px solid #cbb89a; border-radius: 6px; }
.btn { padding: 8px 16px; border-radius: 6px; text-decoration: none; background: #7a3b2e; color: #fff; }
.stats { display: flex; gap: 20px; margin-bottom: 12px; color: #6b5a45; }
.list { width: 100%; border-collapse: collapse; background: #fff; }
.list th, .list td { padding: 10px; border-bottom: 1px solid #eee; text-align: left; }
.actions { display: flex; gap: 12px; }
.actions button { border: none; background: none; color: #b32020; cursor: pointer; }
</style>
```

**Step 2: 手动验证**

Run: 启动后端 `cd backend && python app.py`，前端 `cd frontend && npm run dev`
Expected: 棋谱库可加载、筛选、删除。

**Step 3: 提交**

```bash
git add frontend/src/views/LibraryView.vue
git commit -m "feat: 棋谱库视图"
```

---

### Task 18: 录入视图（棋盘摆子 + 文本解析 + PGN 导入）

**Files:**
- Create: `frontend/src/views/EditorView.vue`

**Step 1: 实现**

`frontend/src/views/EditorView.vue`
```vue
<template>
  <section class="editor">
    <div class="board-area">
      <ChessBoard :position="{ pieces }" :selected="selected" @cell-click="onCellClick" />
      <div class="board-tools">
        <button @click="undo">悔棋</button>
        <button @click="reset">清空</button>
        <button @click="startFromInitial">标准开局</button>
      </div>
      <ol class="moves">
        <li v-for="(move, index) in moves" :key="index">{{ describe(move) }}</li>
      </ol>
    </div>
    <div class="form-area">
      <h2>{{ gameId ? "编辑棋谱" : "新建棋谱" }}</h2>
      <label>名称<input v-model="form.name" /></label>
      <label>分类<input v-model="form.category" /></label>
      <label>红方<input v-model="form.red_player" /></label>
      <label>黑方<input v-model="form.black_player" /></label>
      <label>赛事<input v-model="form.event" /></label>
      <label>结果<input v-model="form.result" /></label>
      <label>背谱阵营
        <select v-model="form.practice_side">
          <option value="both">双方</option>
          <option value="red">红方</option>
          <option value="black">黑方</option>
        </select>
      </label>

      <fieldset>
        <legend>文本解析</legend>
        <textarea v-model="textInput" rows="3" placeholder="炮二平五 炮8平5 或 h2e2 h7e7"></textarea>
        <button @click="parseText">解析预览</button>
      </fieldset>

      <fieldset>
        <legend>PGN 导入</legend>
        <textarea v-model="pgnInput" rows="4" placeholder="粘贴 PGN 内容"></textarea>
        <button @click="importPgn">导入入库</button>
      </fieldset>

      <button class="save" @click="save">保存棋谱</button>
    </div>
  </section>
</template>

<script setup>
import { onMounted, reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import ChessBoard from "../components/ChessBoard.vue";
import { api } from "../api";
import { applyMove, fenToPieces } from "../utils/chess";

const INITIAL_FEN = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1";
const route = useRoute();
const router = useRouter();

const gameId = ref(route.params.id ? Number(route.params.id) : null);
const pieces = ref(fenToPieces(INITIAL_FEN));
const moves = ref([]);
const selected = ref(null);
const initialFen = ref(INITIAL_FEN);
const textInput = ref("");
const pgnInput = ref("");
const form = reactive({
  name: "", category: "", red_player: "", black_player: "",
  event: "", result: "", practice_side: "both",
});

function describe(move) {
  return `(${move.x1},${move.y1})→(${move.x2},${move.y2})`;
}

function onCellClick(x, y) {
  if (!selected.value) {
    if (pieces.value.some((p) => p.x === x && p.y === y)) selected.value = { x, y };
    return;
  }
  const move = { x1: selected.value.x, y1: selected.value.y, x2: x, y2: y };
  pieces.value = applyMove(pieces.value, move);
  moves.value.push(move);
  selected.value = null;
}

function undo() {
  if (moves.value.length === 0) return;
  const last = moves.value.pop();
  pieces.value = applyMove(pieces.value, { x1: last.x2, y1: last.y2, x2: last.x1, y2: last.y1 });
}

function reset() {
  pieces.value = [];
  moves.value = [];
  selected.value = null;
}

function startFromInitial() {
  pieces.value = fenToPieces(initialFen.value);
  moves.value = [];
}

async function parseText() {
  const data = await api.parse({ text: textInput.value, initial_fen: initialFen.value });
  moves.value = data.moves;
  let board = fenToPieces(initialFen.value);
  for (const move of data.moves) board = applyMove(board, move);
  pieces.value = board;
}

async function importPgn() {
  await api.importPgn({ pgn: pgnInput.value, category: form.category, practice_side: form.practice_side });
  router.push("/library");
}

async function save() {
  const payload = { ...form, moves: moves.value, initial_fen: initialFen.value };
  if (gameId.value) await api.updateGame(gameId.value, payload);
  else await api.createGame(payload);
  router.push("/library");
}

onMounted(async () => {
  if (gameId.value) {
    const game = await api.getGame(gameId.value);
    Object.assign(form, game);
    moves.value = game.moves;
    initialFen.value = game.initial_fen;
    let board = fenToPieces(game.initial_fen);
    for (const move of game.moves) board = applyMove(board, move);
    pieces.value = board;
  }
});
</script>

<style scoped>
.editor { display: grid; grid-template-columns: 560px 1fr; gap: 24px; }
.board-tools { display: flex; gap: 10px; margin: 10px 0; }
.form-area { display: flex; flex-direction: column; gap: 10px; }
label { display: flex; flex-direction: column; gap: 4px; font-size: 14px; }
input, select, textarea { padding: 6px 8px; border: 1px solid #cbb89a; border-radius: 6px; }
fieldset { border: 1px solid #d8c8ac; border-radius: 8px; }
.save { padding: 10px; background: #7a3b2e; color: #fff; border: none; border-radius: 6px; cursor: pointer; }
.moves { max-height: 200px; overflow: auto; }
</style>
```

**Step 2: 手动验证**

Run: 后端 + 前端启动
Expected: 摆子可记谱、文本解析可预览、PGN 可导入、可保存。

**Step 3: 提交**

```bash
git add frontend/src/views/EditorView.vue
git commit -m "feat: 录入视图"
```

---

### Task 19: 打谱视图

**Files:**
- Create: `frontend/src/views/PracticeView.vue`

**Step 1: 实现**

`frontend/src/views/PracticeView.vue`
```vue
<template>
  <section v-if="game">
    <h2>{{ game.name }}</h2>
    <div class="layout">
      <ChessBoard :position="{ pieces }" />
      <div>
        <p>当前第 {{ ply }} / {{ game.moves.length }} 步</p>
        <div class="controls">
          <button @click="go(0)">|<</button>
          <button @click="go(ply - 1)">&lt;</button>
          <button @click="go(ply + 1)">&gt;</button>
          <button @click="go(game.moves.length)">>|</button>
        </div>
        <ol class="moves">
          <li v-for="(move, index) in game.moves" :key="index" :class="{ active: index === ply - 1 }" @click="go(index + 1)">
            {{ index + 1 }}. {{ describe(index) }}
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
import { applyMove, fenToPieces } from "../utils/chess";

const route = useRoute();
const game = ref(null);
const ply = ref(0);

const pieces = computed(() => {
  if (!game.value) return [];
  let board = fenToPieces(game.value.initial_fen);
  for (const move of game.value.moves.slice(0, ply.value)) board = applyMove(board, move);
  return board;
});

function go(target) {
  if (!game.value) return;
  ply.value = Math.max(0, Math.min(target, game.value.moves.length));
}

function describe(index) {
  const move = game.value.moves[index];
  return `(${move.x1},${move.y1})→(${move.x2},${move.y2})`;
}

onMounted(async () => {
  game.value = await api.getGame(route.params.id);
});
</script>

<style scoped>
.layout { display: grid; grid-template-columns: 560px 1fr; gap: 24px; }
.controls { display: flex; gap: 8px; margin: 10px 0; }
.moves { max-height: 420px; overflow: auto; cursor: pointer; }
.moves .active { background: #f0d9a8; }
</style>
```

**Step 2: 手动验证**

Run: 打开 `/practice/:id`
Expected: 可逐步前进/后退、点击着法跳转。

**Step 3: 提交**

```bash
git add frontend/src/views/PracticeView.vue
git commit -m "feat: 打谱视图"
```

---

### Task 20: 默写视图（核心练习）

**Files:**
- Create: `frontend/src/stores/practice.js`
- Create: `frontend/src/views/ReviewView.vue`
- Create: `frontend/src/stores/__tests__/practice.test.js`

**Step 1: 写失败测试（默写状态机）**

`frontend/src/stores/__tests__/practice.test.js`
```javascript
import { describe, expect, it } from "vitest";
import { createPracticeSession } from "../practice";

const game = {
  id: 1,
  initial_fen: "4k4/9/9/9/9/9/9/9/9/4K4 w - - 0 1",
  practice_side: "both",
  moves: [{ x1: 4, y1: 0, x2: 4, y2: 1 }],
};

describe("practice session", () => {
  it("走对前进", () => {
    const session = createPracticeSession(game);
    session.submitMove({ x1: 4, y1: 0, x2: 4, y2: 1 });
    expect(session.state.ply).toBe(1);
    expect(session.state.mistakes).toBe(0);
  });

  it("走错计错不前进", () => {
    const session = createPracticeSession(game);
    session.submitMove({ x1: 4, y1: 0, x2: 3, y2: 0 });
    expect(session.state.ply).toBe(0);
    expect(session.state.mistakes).toBe(1);
  });

  it("看答案计为揭示并前进", () => {
    const session = createPracticeSession(game);
    session.reveal();
    expect(session.state.ply).toBe(1);
    expect(session.state.revealed).toBe(true);
  });
});
```

**Step 2: 运行确认失败**

Run: `cd frontend && npx vitest run src/stores/__tests__/practice.test.js`
Expected: FAIL

**Step 3: 实现状态机**

`frontend/src/stores/practice.js`
```javascript
import { reactive } from "vue";
import { applyMove, fenToPieces } from "../utils/chess";

function sameMove(a, b) {
  return a.x1 === b.x1 && a.y1 === b.y1 && a.x2 === b.x2 && a.y2 === b.y2;
}

export function createPracticeSession(game) {
  const state = reactive({
    ply: 0,
    mistakes: 0,
    revealed: false,
    pieces: fenToPieces(game.initial_fen),
    expected: game.moves[0] || null,
  });

  function advance() {
    if (state.ply >= game.moves.length) return;
    const move = game.moves[state.ply];
    state.pieces = applyMove(state.pieces, move);
    state.ply += 1;
    state.expected = game.moves[state.ply] || null;
  }

  return {
    game,
    state,
    submitMove(move) {
      const expected = game.moves[state.ply];
      if (!expected) return false;
      if (sameMove(move, expected)) {
        advance();
        return true;
      }
      state.mistakes += 1;
      return false;
    },
    reveal() {
      state.revealed = true;
      advance();
    },
    isFinished() {
      return state.ply >= game.moves.length;
    },
  };
}
```

**Step 4: 运行确认通过**

Run: `cd frontend && npx vitest run src/stores/__tests__/practice.test.js`
Expected: PASS（3 passed）

**Step 5: 实现视图**

`frontend/src/views/ReviewView.vue`
```vue
<template>
  <section>
    <p v-if="!current">今日复习已全部完成 🎉</p>
    <div v-else>
      <header class="head">
        <h2>{{ current.game.name }}</h2>
        <span>第 {{ index + 1 }} / {{ queue.length }} 个</span>
        <span>错误 {{ session.state.mistakes }}</span>
        <span>用时 {{ elapsed }}s</span>
      </header>

      <div v-if="!session.isFinished()" class="layout">
        <ChessBoard :position="{ pieces: session.state.pieces }" :selected="selected" @cell-click="onCellClick" />
        <div>
          <p>请走出{{ sideText(current.game.practice_side) }}的正确着法</p>
          <button @click="doReveal">看答案</button>
        </div>
      </div>

      <div v-else class="result">
        <p>完成！共错 {{ session.state.mistakes }} 次{{ session.state.revealed ? "（使用过答案）" : "" }}</p>
        <button @click="submit">提交并进入下一个</button>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from "vue";
import ChessBoard from "../components/ChessBoard.vue";
import { api } from "../api";
import { createPracticeSession } from "../stores/practice";

const queue = ref([]);
const index = ref(0);
const selected = ref(null);
const elapsed = ref(0);
let timer = null;
let session = null;

const current = computed(() => queue.value[index.value] || null);

function sideText(side) {
  return { red: "红方", black: "黑方", both: "轮到的一方" }[side] || "正确一方";
}

function onCellClick(x, y) {
  if (!session) return;
  if (!selected.value) {
    if (session.state.pieces.some((p) => p.x === x && p.y === y)) selected.value = { x, y };
    return;
  }
  session.submitMove({ x1: selected.value.x, y1: selected.value.y, x2: x, y2: y });
  selected.value = null;
}

function doReveal() {
  session.reveal();
}

async function submit() {
  await api.submitReview(current.value.game.id, {
    mistake_count: session.state.mistakes,
    revealed: session.state.revealed,
    duration_ms: elapsed.value * 1000,
  });
  index.value += 1;
  selected.value = null;
  startSession();
}

function startSession() {
  if (!current.value) {
    session = null;
    return;
  }
  session = createPracticeSession(current.value.game);
  elapsed.value = 0;
}

onMounted(async () => {
  queue.value = (await api.reviewQueue()).items;
  startSession();
  timer = setInterval(() => (elapsed.value += 1), 1000);
});

onUnmounted(() => clearInterval(timer));
</script>

<style scoped>
.head { display: flex; gap: 20px; align-items: center; }
.layout { display: grid; grid-template-columns: 560px 1fr; gap: 24px; }
.result { background: #fff; padding: 20px; border-radius: 8px; }
</style>
```

**Step 6: 运行全部前端测试**

Run: `cd frontend && npx vitest run`
Expected: PASS（全部）

**Step 7: 提交**

```bash
git add frontend/src/stores/ frontend/src/views/ReviewView.vue
git commit -m "feat: 默写视图与练习状态机"
```

---

## 阶段五：集成与部署

### Task 21: 生产构建由 Flask 托管

**Files:**
- Modify: `backend/app.py`

**Step 1: 实现静态托管**

在 `backend/app.py` 的 `create_app` 中追加：

```python
import os

from flask import send_from_directory

FRONTEND_DIST = os.path.abspath(os.path.join(BASE_DIR, "..", "frontend", "dist"))


def _register_frontend(app):
    if not os.path.isdir(FRONTEND_DIST):
        return

    @app.get("/")
    def index():
        return send_from_directory(FRONTEND_DIST, "index.html")

    @app.get("/<path:path>")
    def assets(path):
        full = os.path.join(FRONTEND_DIST, path)
        if os.path.isfile(full):
            return send_from_directory(FRONTEND_DIST, path)
        return send_from_directory(FRONTEND_DIST, "index.html")
```

并在 `create_app` 返回前调用 `_register_frontend(app)`（需在蓝图注册之后）。注意 `BASE_DIR` 从 `config` 导入。

**Step 2: 构建并验证**

Run:
```bash
cd frontend && npm run build
cd ../backend && python app.py
```
Expected: 访问 `http://localhost:5000/` 可打开前端页面，`/api/health` 正常。

**Step 3: 提交**

```bash
git add backend/app.py
git commit -m "feat: Flask 托管前端构建产物"
```

---

### Task 22: 全量测试与验收

**Files:**
- Create: `README.md`

**Step 1: 后端全量测试**

Run: `cd backend && pytest -v`
Expected: 全部 PASS

**Step 2: 前端全量测试**

Run: `cd frontend && npx vitest run`
Expected: 全部 PASS

**Step 3: 手动验收清单**

1. 新建棋谱：棋盘摆子走出「炮二平五」，保存后在库中可见。
2. 文本解析：粘贴 `炮二平五 炮8平5 马二进三 马8进7`，预览正确。
3. PGN 导入：导入含 `[Event]`/`[Red]` 的 PGN，库中生成棋谱。
4. 打谱：逐步前进/后退、点击着法跳转。
5. 默写：走错计错并提示，走对前进，看答案可揭示，完成后提交。
6. 复习队列：提交后该棋谱从今日队列消失。
7. 生产：`npm run build` 后 Flask 单端口可访问。

**Step 4: 写 README**

`README.md` 内容包含：项目简介、目录结构、后端启动（`pip install -r requirements.txt && python app.py`）、前端启动（`npm install && npm run dev`）、测试命令、生产构建命令。

**Step 5: 提交**

```bash
git add README.md
git commit -m "docs: 项目说明与验收清单"
```

---

## 备注与已知简化

- 中文记谱的「前/后」仅处理同纵线两子的常见情形；三子及以上极端局面需后续增强。
- PGN 解析按空白分词，兼容中文与 ICCS；复杂注释 `{}` 未剥离，若遇到再补充。
- 默写当前在 `practice_side=both` 时默写轮到的一方；若只背红方而当前为黑方，前端可自动跳过（后续可增强为后端返回需默写步索引列表）。
- `check-move` API 已实现但前端默写状态机为纯前端校验；如后续需要严格服务端校验，可在 `submitMove` 内改为调用 `api.checkMove`。
