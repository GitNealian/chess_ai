from chess_engine.board import BLACK, PIECE_NAMES, RED
from chess_engine.move import Move

_CN_DIGITS = "一二三四五六七八九"
_CN_TO_NUM = {ch: i + 1 for i, ch in enumerate(_CN_DIGITS)}

_NAME_TO_KIND = {}
for (_side, _kind), _name in PIECE_NAMES.items():
    _NAME_TO_KIND.setdefault(_side, {})[_name] = _kind

_STRAIGHT_KINDS = ("R", "C", "P", "K")


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
            raise ValueError(f"无效的纵线/步数：{text}")
        return _CN_TO_NUM[text]
    if not text.isdigit() or not 1 <= int(text) <= 9:
        raise ValueError(f"无效的纵线/步数：{text}")
    return int(text)


def _same_file_pieces(board, side, kind, x):
    return sorted(
        py for (px, py), piece in board.grid.items()
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
        if len(_same_file_pieces(board, side, kind, move.x1)) >= 3:
            raise ValueError(f"{name}同列多子暂不支持生成记谱")
        head = name + _num_text(file_number(move.x1, side), side)

    dy = move.y2 - move.y1
    if dy == 0:
        action = "平"
        target = _num_text(file_number(move.x2, side), side)
    else:
        forward = dy > 0 if side == RED else dy < 0
        action = "进" if forward else "退"
        if kind in _STRAIGHT_KINDS:
            target = _num_text(abs(dy), side)
        else:
            target = _num_text(file_number(move.x2, side), side)
    return head + action + target


def parse_chinese(board, text):
    text = text.strip()
    side = board.side_to_move
    if len(text) < 2:
        raise ValueError(f"着法格式错误：{text}")

    if text[:1] in ("前", "后"):
        prefix = text[0]
        name = text[1]
        kind = _NAME_TO_KIND.get(side, {}).get(name)
        if kind is None:
            raise ValueError(f"未知棋子：{name}")
        groups = {}
        for (x, y), piece in board.grid.items():
            if piece == (side, kind):
                groups.setdefault(x, []).append(y)
        candidates = []
        for x, ys in groups.items():
            if len(ys) < 2:
                continue
            ordered = sorted(ys, reverse=(side == RED))
            pick = ordered[0] if prefix == "前" else ordered[-1]
            candidates.append((x, pick))
        if not candidates:
            raise ValueError(f"找不到可区分前后的棋子：{text}")
        if len(candidates) > 1:
            raise ValueError(f"{text}：存在多个可匹配的{name}，无法区分")
        x1, y1 = candidates[0]
        rest = text[2:]
    else:
        name = text[0]
        kind = _NAME_TO_KIND.get(side, {}).get(name)
        if kind is None:
            raise ValueError(f"未知棋子：{name}")
        number = _parse_number(text[1], side)
        x1 = file_to_x(number, side)
        ys = _same_file_pieces(board, side, kind, x1)
        if not ys:
            raise ValueError(f"{text}：该纵线没有{name}")
        y1 = ys[0]
        rest = text[2:]

    if len(rest) < 2:
        raise ValueError(f"着法格式错误：{text}")
    action = rest[0]
    if action not in ("进", "退", "平"):
        raise ValueError(f"{text}：未知动作 {action}")
    number = _parse_number(rest[1:], side)

    if action == "平":
        x2 = file_to_x(number, side)
        y2 = y1
    elif kind in _STRAIGHT_KINDS:
        x2 = x1
        if side == RED:
            y2 = y1 + number if action == "进" else y1 - number
        else:
            y2 = y1 - number if action == "进" else y1 + number
    else:
        x2 = file_to_x(number, side)
        want_up = (action == "进") == (side == RED)
        candidates = [
            m for m in board.pseudo_moves_from(x1, y1)
            if m.x2 == x2 and ((m.y2 - y1) > 0) == want_up
        ]
        if not candidates:
            raise ValueError(f"{text}：不是合法着法")
        return candidates[0]

    move = Move(x1, y1, x2, y2)
    if move not in board.pseudo_moves_from(x1, y1):
        raise ValueError(f"{text}：不是合法着法")
    return move
