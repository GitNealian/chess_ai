import pytest

from chess_engine.board import BLACK, RED, Board
from chess_engine.move import Move
from chess_engine.notation import move_to_chinese, parse_chinese


def test_cannon_opening_move():
    board = Board.initial()
    board.side_to_move = RED
    assert move_to_chinese(board, Move(7, 2, 4, 2)) == "炮二平五"


def test_horse_opening_move():
    board = Board.initial()
    board.side_to_move = RED
    assert move_to_chinese(board, Move(1, 0, 2, 2)) == "马八进七"


def test_pawn_forward():
    board = Board.initial()
    board.side_to_move = RED
    assert move_to_chinese(board, Move(0, 3, 0, 4)) == "兵九进一"


def test_black_cannon_move():
    board = Board.initial()
    board.side_to_move = BLACK
    assert move_to_chinese(board, Move(7, 7, 4, 7)) == "炮8平5"


def test_parse_and_round_trip_initial_sequence():
    board = Board.initial()
    texts = ["炮二平五", "炮8平5", "马二进三", "马8进7"]
    moves = []
    for text in texts:
        move = parse_chinese(board, text)
        moves.append(move)
        board.apply_move(move)
    assert [(m.x1, m.y1, m.x2, m.y2) for m in moves] == [
        (7, 2, 4, 2), (7, 7, 4, 7), (7, 0, 6, 2), (7, 9, 6, 7),
    ]


def test_parse_invalid_raises():
    board = Board.initial()
    board.side_to_move = RED
    with pytest.raises(ValueError):
        parse_chinese(board, "马二进五")
