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


def test_red_advisor_generation_and_parse():
    board = Board.empty()
    board.side_to_move = RED
    board.set_piece(4, 1, (RED, "A"))
    assert move_to_chinese(board, Move(4, 1, 3, 0)) == "仕五退六"
    assert move_to_chinese(board, Move(4, 1, 5, 2)) == "仕五进四"
    assert parse_chinese(board, "仕五退六") == Move(4, 1, 3, 0)
    assert parse_chinese(board, "仕五进四") == Move(4, 1, 5, 2)


def test_black_advisor_generation_and_parse():
    board = Board.empty()
    board.side_to_move = BLACK
    board.set_piece(4, 8, (BLACK, "A"))
    assert move_to_chinese(board, Move(4, 8, 3, 9)) == "士5退4"
    assert move_to_chinese(board, Move(4, 8, 5, 7)) == "士5进6"
    assert parse_chinese(board, "士5退4") == Move(4, 8, 3, 9)
    assert parse_chinese(board, "士5进6") == Move(4, 8, 5, 7)


def test_red_rook_prefix_generation_and_parse():
    board = Board.empty()
    board.side_to_move = RED
    board.set_piece(0, 0, (RED, "R"))
    board.set_piece(0, 2, (RED, "R"))
    assert move_to_chinese(board, Move(0, 2, 0, 3)) == "前车进一"
    assert move_to_chinese(board, Move(0, 0, 0, 1)) == "后车进一"
    assert parse_chinese(board, "前车进一") == Move(0, 2, 0, 3)
    assert parse_chinese(board, "后车进一") == Move(0, 0, 0, 1)


def test_black_cannon_prefix_generation_and_parse():
    board = Board.empty()
    board.side_to_move = BLACK
    board.set_piece(0, 7, (BLACK, "C"))
    board.set_piece(0, 9, (BLACK, "C"))
    assert move_to_chinese(board, Move(0, 7, 0, 6)) == "前炮进1"
    assert move_to_chinese(board, Move(0, 9, 0, 8)) == "后炮进1"
    assert parse_chinese(board, "前炮进1") == Move(0, 7, 0, 6)
    assert parse_chinese(board, "后炮进1") == Move(0, 9, 0, 8)


def test_red_pawn_cross_river_sideways():
    board = Board.empty()
    board.side_to_move = RED
    board.set_piece(4, 5, (RED, "P"))
    assert move_to_chinese(board, Move(4, 5, 3, 5)) == "兵五平六"
    assert parse_chinese(board, "兵五平六") == Move(4, 5, 3, 5)


def test_black_rook_retreat():
    board = Board.empty()
    board.side_to_move = BLACK
    board.set_piece(0, 5, (BLACK, "R"))
    assert move_to_chinese(board, Move(0, 5, 0, 6)) == "车1退1"
    assert parse_chinese(board, "车1退1") == Move(0, 5, 0, 6)


def test_ambiguous_prefix_across_files_raises():
    board = Board.empty()
    board.side_to_move = RED
    for x in (0, 2):
        board.set_piece(x, 3, (RED, "P"))
        board.set_piece(x, 4, (RED, "P"))
    with pytest.raises(ValueError):
        parse_chinese(board, "前兵进一")


def test_three_same_file_pieces_middle_raises():
    board = Board.empty()
    board.side_to_move = RED
    for y in (2, 3, 4):
        board.set_piece(0, y, (RED, "P"))
    with pytest.raises(ValueError):
        move_to_chinese(board, Move(0, 3, 0, 5))
