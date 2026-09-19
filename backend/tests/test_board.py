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
