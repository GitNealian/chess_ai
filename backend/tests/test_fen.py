import pytest

from chess_engine.board import BLACK, RED
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


def test_parse_rejects_wrong_row_count():
    with pytest.raises(ValueError):
        parse_fen("9/9/9/9/9/9/9/9/9 w - - 0 1")


def test_parse_rejects_too_many_columns():
    with pytest.raises(ValueError):
        parse_fen("rnbakabnrr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1")


def test_parse_rejects_too_few_columns():
    with pytest.raises(ValueError):
        parse_fen("rnbakabn/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1")


def test_parse_rejects_illegal_piece_char():
    with pytest.raises(ValueError):
        parse_fen("4x4/9/9/9/9/9/9/9/9/4K4 w - - 0 1")


def test_parse_rejects_empty_fen():
    with pytest.raises(ValueError):
        parse_fen("")


def test_parse_rejects_whitespace_fen():
    with pytest.raises(ValueError):
        parse_fen("   ")


def test_empty_board_round_trip():
    fen = "9/9/9/9/9/9/9/9/9/9 w - - 0 1"
    assert to_fen(parse_fen(fen)) == fen


def test_round_trip_black_to_move():
    fen = "4k4/9/9/9/9/9/9/9/9/4K4 b - - 0 1"
    assert to_fen(parse_fen(fen)) == fen
