"""棋谱变着树的局面判定（纯逻辑，无 Flask / SQLAlchemy 依赖）。

- 节点 = 局面，key 为 FEN 的「布局段 + 行棋方段」，与到达路径无关。
- 边   = 一步着法；不同谱、不同着法只要 from 局面相同即落在同一节点。
"""

from chess_engine.board import Board
from chess_engine.move import Move

COLLECTION_PREFIX = "古谱 · "

# 分叉入口要求经过该局面的每一盘棋步数都严格大于该值（4 着 = 双方各 2 步）。
VARIATION_MIN_PLY = 4


def fen_key(fen: str) -> str:
    """局面的归一化 key：布局 + 行棋方，忽略末尾的步数计数。"""
    parts = fen.split()
    return f"{parts[0]} {parts[1]}"


def collection_of(category: str):
    """棋谱集名；非 `古谱 · ` 前缀的棋谱不参与变着树，返回 None。"""
    if category and category.startswith(COLLECTION_PREFIX):
        return category[len(COLLECTION_PREFIX):]
    return None


def move_key(move: Move) -> str:
    return f"{move.x1},{move.y1},{move.x2},{move.y2}"


def build_steps(game):
    """重放一盘棋，产出每步入栈前的局面、着法与走后的局面。"""
    board = Board()
    board.load_fen(game.initial_fen)
    rows = []
    for ply, raw in enumerate(game.moves):
        from_key = fen_key(board.to_fen())
        move = Move.from_dict(raw)
        board.apply_move(move)
        rows.append(
            {
                "ply": ply,
                "fen_key": from_key,
                "move": move_key(move),
                "next_fen": fen_key(board.to_fen()),
            }
        )
    return rows
