import pytest

from chess_engine.board import Board
from chess_engine.parser import parse_iccs, parse_moves, parse_pgn


def test_parse_iccs():
    move = parse_iccs("h2e2")
    assert (move.x1, move.y1, move.x2, move.y2) == (7, 2, 4, 2)


def test_parse_moves_auto_detect_chinese():
    board = Board.initial()
    moves = parse_moves(board, "炮二平五 炮8平5")
    assert len(moves) == 2
    assert (moves[0].x1, moves[0].y1, moves[0].x2, moves[0].y2) == (7, 2, 4, 2)
    assert (moves[1].x1, moves[1].y1, moves[1].x2, moves[1].y2) == (7, 7, 4, 7)


def test_parse_moves_auto_detect_iccs():
    board = Board.initial()
    moves = parse_moves(board, "h2e2 h7e7")
    assert len(moves) == 2
    assert (moves[0].x1, moves[0].y1, moves[0].x2, moves[0].y2) == (7, 2, 4, 2)
    assert (moves[1].x1, moves[1].y1, moves[1].x2, moves[1].y2) == (7, 7, 4, 7)


def test_parse_iccs_uppercase():
    move = parse_iccs("H2E2")
    assert (move.x1, move.y1, move.x2, move.y2) == (7, 2, 4, 2)


def test_parse_iccs_with_dash():
    move = parse_iccs("H2-E2")
    assert (move.x1, move.y1, move.x2, move.y2) == (7, 2, 4, 2)


def test_parse_moves_iccs_with_dash():
    board = Board.initial()
    moves = parse_moves(board, "H2-E2 H7-E7")
    assert len(moves) == 2
    assert (moves[0].x1, moves[0].y1, moves[0].x2, moves[0].y2) == (7, 2, 4, 2)
    assert (moves[1].x1, moves[1].y1, moves[1].x2, moves[1].y2) == (7, 7, 4, 7)


def test_parse_moves_uppercase_iccs():
    board = Board.initial()
    moves = parse_moves(board, "H2E2 H7E7")
    assert len(moves) == 2
    assert (moves[0].x1, moves[0].y1, moves[0].x2, moves[0].y2) == (7, 2, 4, 2)
    assert (moves[1].x1, moves[1].y1, moves[1].x2, moves[1].y2) == (7, 7, 4, 7)


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


def test_parse_pgn_result_header():
    pgn = """[Result "1-0"]

1. 炮二平五 炮8平5
"""
    parsed = parse_pgn(pgn)
    assert parsed["result"] == "1-0"
    assert len(parsed["moves"]) == 2


def test_parse_pgn_empty_body():
    parsed = parse_pgn('[Event "测试"]')
    assert parsed["moves"] == []


def test_parse_pgn_with_fen_header():
    pgn = """[FEN "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"]

1. H2-E2 H7-E7
"""
    parsed = parse_pgn(pgn)
    assert len(parsed["moves"]) == 2


def test_parse_pgn_invalid_fen_header():
    pgn = """[FEN "not-a-fen"]

1. H2-E2
"""
    with pytest.raises(ValueError, match="FEN 头无效"):
        parse_pgn(pgn)


def test_parse_moves_ignores_result_token():
    board = Board.initial()
    moves = parse_moves(board, "炮二平五 炮8平5 1-0")
    assert len(moves) == 2
    assert (moves[0].x1, moves[0].y1, moves[0].x2, moves[0].y2) == (7, 2, 4, 2)
    assert (moves[1].x1, moves[1].y1, moves[1].x2, moves[1].y2) == (7, 7, 4, 7)


def test_parse_moves_ignores_draw_result_token():
    board = Board.initial()
    moves = parse_moves(board, "炮二平五 炮8平5 *")
    assert len(moves) == 2


def test_parse_moves_strips_brace_comment():
    board = Board.initial()
    moves = parse_moves(board, "炮二平五 {开局} 炮8平5")
    assert len(moves) == 2
    assert (moves[0].x1, moves[0].y1, moves[0].x2, moves[0].y2) == (7, 2, 4, 2)
    assert (moves[1].x1, moves[1].y1, moves[1].x2, moves[1].y2) == (7, 7, 4, 7)


def test_parse_moves_strips_semicolon_comment():
    board = Board.initial()
    moves = parse_moves(board, "炮二平五 ; 注释\n炮8平5")
    assert len(moves) == 2
    assert (moves[0].x1, moves[0].y1, moves[0].x2, moves[0].y2) == (7, 2, 4, 2)
    assert (moves[1].x1, moves[1].y1, moves[1].x2, moves[1].y2) == (7, 7, 4, 7)


def test_parse_moves_valid_sequence():
    board = Board.initial()
    moves = parse_moves(board, "炮二平五 炮8平5 马二进三 马8进7")
    assert len(moves) == 4
    assert (moves[0].x1, moves[0].y1, moves[0].x2, moves[0].y2) == (7, 2, 4, 2)
    assert (moves[1].x1, moves[1].y1, moves[1].x2, moves[1].y2) == (7, 7, 4, 7)
    assert (moves[2].x1, moves[2].y1, moves[2].x2, moves[2].y2) == (7, 0, 6, 2)
    assert (moves[3].x1, moves[3].y1, moves[3].x2, moves[3].y2) == (7, 9, 6, 7)


def test_parse_error_reports_step():
    board = Board.initial()
    with pytest.raises(ValueError, match="炮8进9"):
        parse_moves(board, "炮二平五 炮8进9")


def test_parse_error_reports_index():
    board = Board.initial()
    with pytest.raises(ValueError, match="第 2 步"):
        parse_moves(board, "炮二平五 炮8进9")
