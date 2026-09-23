"""摆子规则 `validate_setup` 单元测试。"""

from chess_engine.board import BLACK, RED, Board
from chess_engine.rules import validate_setup


def board_with(pieces, side=RED):
    board = Board.empty()
    for x, y, s, kind in pieces:
        board.set_piece(x, y, (s, kind))
    board.side_to_move = side
    return board


def minimal_ok():
    return [(4, 0, RED, "K"), (3, 9, BLACK, "K")]


def test_valid_minimal_position():
    assert validate_setup(board_with(minimal_ok())) == []


def test_requires_exactly_one_king_each_side():
    errors = validate_setup(board_with([(4, 0, RED, "K")]))
    assert any("黑方" in e and "将" in e for e in errors)
    # 缺帅时不额外报「被将军」（该方已由缺帅错误覆盖）
    assert not any("被将军" in e for e in errors)
    errors = validate_setup(
        board_with([(4, 0, RED, "K"), (3, 9, BLACK, "K"), (5, 0, RED, "K")])
    )
    assert any("红方" in e and "帅" in e for e in errors)


def test_king_must_stay_in_palace():
    errors = validate_setup(board_with([(4, 5, RED, "K"), (3, 9, BLACK, "K")]))
    assert any("红方" in e for e in errors)


def test_advisor_must_stay_in_palace():
    errors = validate_setup(board_with(minimal_ok() + [(0, 0, RED, "A")]))
    assert any("红方" in e for e in errors)


def test_elephant_must_be_on_site():
    errors = validate_setup(board_with(minimal_ok() + [(2, 5, RED, "B")]))
    assert any("红相" in e for e in errors)
    errors = validate_setup(board_with(minimal_ok() + [(2, 4, BLACK, "B")]))
    assert any("黑象" in e for e in errors)
    # 合法象位不报错
    errors = validate_setup(
        board_with(minimal_ok() + [(4, 2, RED, "B"), (4, 7, BLACK, "B")])
    )
    assert not any("象" in e for e in errors)


def test_soldier_position_bounds():
    errors = validate_setup(board_with(minimal_ok() + [(0, 2, RED, "P")]))
    assert any("红兵" in e for e in errors)
    errors = validate_setup(board_with(minimal_ok() + [(0, 7, BLACK, "P")]))
    assert any("黑卒" in e for e in errors)
    # 未过河必须在初始偶数列
    errors = validate_setup(board_with(minimal_ok() + [(1, 3, RED, "P")]))
    assert any("红兵" in e for e in errors)
    errors = validate_setup(board_with(minimal_ok() + [(1, 6, BLACK, "P")]))
    assert any("黑卒" in e for e in errors)
    # 过河后可落在任意列
    errors = validate_setup(
        board_with(minimal_ok() + [(1, 5, RED, "P"), (1, 4, BLACK, "P")])
    )
    assert not any("兵" in e or "卒" in e for e in errors)
    # 未过河初始偶数列合法
    errors = validate_setup(
        board_with(minimal_ok() + [(2, 3, RED, "P"), (2, 6, BLACK, "P")])
    )
    assert not any("兵" in e or "卒" in e for e in errors)


def test_piece_count_limits():
    pieces = minimal_ok() + [(i, 3, RED, "P") for i in range(6)]
    errors = validate_setup(board_with(pieces))
    assert any("红方" in e and "兵" in e for e in errors)


def test_kings_facing_rejected():
    errors = validate_setup(
        board_with([(4, 0, RED, "K"), (4, 9, BLACK, "K")], side=RED)
    )
    assert any("照面" in e for e in errors)


def test_side_in_check_rejected():
    # 黑车 (4, 5) 正对红帅 (4, 0)，中间无子 → 红被将军
    errors = validate_setup(board_with(minimal_ok() + [(4, 5, BLACK, "R")]))
    assert any("红方" in e and "将军" in e for e in errors)
