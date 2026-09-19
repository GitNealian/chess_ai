import pytest

from chess_engine.board import BLACK, RED, Board
from chess_engine.move import Move


def test_facing_kings_is_illegal():
    board = Board.empty()
    board.set_piece(4, 0, (RED, "K"))
    board.set_piece(4, 9, (BLACK, "K"))
    board.set_piece(0, 0, (RED, "R"))
    board.side_to_move = RED
    assert not board.is_legal(Move(4, 0, 4, 1))


def test_blocking_facing_kings_is_legal():
    board = Board.empty()
    board.set_piece(4, 0, (RED, "K"))
    board.set_piece(4, 9, (BLACK, "K"))
    board.set_piece(4, 4, (RED, "R"))
    board.side_to_move = RED
    assert board.is_legal(Move(4, 4, 4, 5))
    assert not board.is_legal(Move(4, 4, 3, 4))


def test_in_check_detection():
    board = Board.empty()
    board.set_piece(4, 0, (RED, "K"))
    board.set_piece(4, 9, (BLACK, "K"))
    board.set_piece(4, 5, (BLACK, "R"))
    board.side_to_move = RED
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
    assert board.side_to_move == BLACK


def test_legal_moves_excludes_self_check():
    board = Board.empty()
    board.set_piece(4, 0, (RED, "K"))
    board.set_piece(4, 9, (BLACK, "K"))
    board.set_piece(4, 2, (RED, "A"))
    board.set_piece(4, 5, (BLACK, "R"))
    board.side_to_move = RED
    moves = board.legal_moves(RED)
    assert Move(4, 2, 3, 1) not in moves
    assert Move(4, 2, 5, 1) not in moves


def test_checkmate_detection():
    board = Board.empty()
    board.set_piece(4, 0, (RED, "K"))
    board.set_piece(0, 9, (BLACK, "K"))
    board.set_piece(3, 9, (BLACK, "R"))
    board.set_piece(4, 8, (BLACK, "R"))
    board.set_piece(5, 9, (BLACK, "R"))
    board.side_to_move = RED
    assert board.in_check(RED)
    assert board.is_checkmate(RED)


def test_stalemate_detection():
    board = Board.empty()
    board.set_piece(4, 0, (RED, "K"))
    board.set_piece(0, 9, (BLACK, "K"))
    board.set_piece(3, 9, (BLACK, "R"))
    board.set_piece(5, 9, (BLACK, "R"))
    board.set_piece(2, 2, (BLACK, "N"))
    board.side_to_move = RED
    assert not board.in_check(RED)
    assert not board.has_legal_move(RED)
    assert board.is_stalemate(RED)
    assert not board.is_checkmate(RED)


def test_stalemate_no_check_no_moves():
    board = Board.empty()
    board.set_piece(4, 0, (RED, "K"))
    board.set_piece(0, 9, (BLACK, "K"))
    board.set_piece(3, 9, (BLACK, "R"))
    board.set_piece(5, 9, (BLACK, "R"))
    board.set_piece(6, 2, (BLACK, "N"))
    board.side_to_move = RED
    assert not board.in_check(RED)
    assert board.legal_moves(RED) == []
    assert board.is_stalemate(RED) is True
    assert board.is_checkmate(RED) is False


def test_apply_move_rejects_empty_origin():
    board = Board.empty()
    board.set_piece(4, 0, (RED, "K"))
    with pytest.raises(ValueError):
        board.apply_move(Move(3, 3, 4, 4))
