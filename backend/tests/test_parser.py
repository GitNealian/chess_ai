from chess_engine.board import Board
from chess_engine.parser import parse_iccs, parse_moves, parse_pgn


def test_parse_iccs():
    move = parse_iccs("h2e2")
    assert (move.x1, move.y1, move.x2, move.y2) == (7, 2, 4, 2)


def test_parse_moves_auto_detect_chinese():
    board = Board.initial()
    moves = parse_moves(board, "炮二平五 炮8平5")
    assert len(moves) == 2


def test_parse_moves_auto_detect_iccs():
    board = Board.initial()
    moves = parse_moves(board, "h2e2 h7e7")
    assert len(moves) == 2


def test_parse_pgn_with_headers():
    pgn = """[Event "测试"]
[Red "甲"]
[Black "乙"]

1. 炮二平五 炮8平5
2. 马二进三 马8进7
"""
    parsed = parse_pgn(pgn)
    assert parsed["event"] == "测试"
    assert parsed["red_player"] == "甲"
    assert parsed["black_player"] == "乙"
    assert len(parsed["moves"]) == 4


def test_parse_error_reports_step():
    board = Board.initial()
    try:
        parse_moves(board, "炮二平五 炮8进9")
        assert False
    except ValueError as exc:
        assert "2" in str(exc)
