from typing import Optional

from chess_engine.move import Move

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

    def apply_move(self, move):
        piece = self.piece_at(move.x1, move.y1)
        if piece is None:
            raise ValueError("起点无棋子")
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
