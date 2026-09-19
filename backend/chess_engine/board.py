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
