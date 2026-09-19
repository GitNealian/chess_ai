from chess_engine.board import BLACK, RED, Board


def _targets(board, x, y):
    return sorted((m.x2, m.y2) for m in board.pseudo_moves_from(x, y))


def test_rook_moves_straight():
    board = Board.empty()
    board.set_piece(4, 4, (RED, "R"))
    board.set_piece(4, 0, (RED, "K"))
    board.set_piece(4, 9, (BLACK, "K"))
    board.set_piece(4, 6, (BLACK, "P"))
    assert _targets(board, 4, 4) == [
        (0, 4), (1, 4), (2, 4), (3, 4),
        (4, 1), (4, 2), (4, 3), (4, 5), (4, 6),
        (5, 4), (6, 4), (7, 4), (8, 4),
    ]


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
