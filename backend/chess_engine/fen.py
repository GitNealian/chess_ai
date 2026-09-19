from chess_engine.board import BLACK, RED, Board


def _letter_to_piece(ch):
    kind = ch.upper()
    if kind not in "KABNRCP":
        raise ValueError(f"FEN 含非法棋子字符：{ch}")
    side = RED if ch.isupper() else BLACK
    return (side, kind)


def _piece_to_letter(piece):
    side, kind = piece
    return kind if side == RED else kind.lower()


def parse_fen(fen):
    parts = fen.split()
    if not parts:
        raise ValueError("FEN 不能为空")
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
