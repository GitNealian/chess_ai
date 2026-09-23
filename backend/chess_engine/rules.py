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


# 相/象合法落点（各 7 个田字位）
ELEPHANT_SITES = {
    RED: {(2, 0), (6, 0), (0, 2), (4, 2), (8, 2), (2, 4), (6, 4)},
    BLACK: {(2, 9), (6, 9), (0, 7), (4, 7), (8, 7), (2, 5), (6, 5)},
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
                label = "帅/将" if kind == "K" else "仕/士"
                errors.append(f"{SIDE_NAMES[side]}{label}必须在九宫内")
            elif kind == "B":
                if (x, y) not in ELEPHANT_SITES[side]:
                    errors.append("红相必须落在象位" if side == RED else "黑象必须落在象位")
            elif kind == "P":
                if side == RED:
                    if y < 3:
                        errors.append("红兵不能出现在红方底线附近")
                    elif y in (3, 4) and x % 2 != 0:
                        errors.append("红兵未过河时必须在初始列上")
                else:
                    if y > 6:
                        errors.append("黑卒不能出现在黑方底线附近")
                    elif y in (5, 6) and x % 2 != 0:
                        errors.append("黑卒未过河时必须在初始列上")

    facing = board.kings_facing()
    if facing:
        errors.append("双方帅将不能照面")

    for side in (RED, BLACK):
        if facing or board.find_king(side) is None:
            continue
        if board.in_check(side):
            errors.append(f"{SIDE_NAMES[side]}处于被将军状态")

    return errors
