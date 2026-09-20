import numpy as np

from engine import constants as C


def test_role_encoding():
    assert C.RED_SOLDIER == 1 and C.RED_KING == 7
    assert C.BLACK_SOLDIER == 8 and C.BLACK_KING == 14
    for kind in range(1, 8):
        assert C.role_of(kind, C.RED) == kind
        assert C.role_of(kind, C.BLACK) == kind + 7


def test_piece_index_layout():
    assert C.RED_PIECES_START == 32 and C.BLACK_PIECES_START == 16
    assert C.PIECE_ROLES[16] == C.BLACK_KING
    assert C.PIECE_ROLES[32] == C.RED_KING
    assert len(C.PIECE_ROLES) == 48
    assert C.PIECE_ROLES[0] == 0


def test_piece_starts():
    assert C.BLACK_PIECES_START == 16 and C.RED_PIECES_START == 32
    assert C.PIECE_STARTS == (16, 32)
    assert C.PIECE_STARTS[C.BLACK] == C.BLACK_PIECES_START
    assert C.PIECE_STARTS[C.RED] == C.RED_PIECES_START


def test_piece_roles_full_table():
    expected = [
        0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
        14, 13, 13, 12, 12, 11, 11, 10, 10, 9, 9, 8, 8, 8, 8, 8,
        7, 6, 6, 5, 5, 4, 4, 3, 3, 2, 2, 1, 1, 1, 1, 1,
    ]
    assert len(C.PIECE_ROLES) == 48
    for i, value in enumerate(expected):
        assert C.PIECE_ROLES[i] == value, f"PIECE_ROLES[{i}]"


def test_piece_kinds_full_table():
    expected = [
        0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
        7, 6, 6, 5, 5, 4, 4, 3, 3, 2, 2, 1, 1, 1, 1, 1,
        7, 6, 6, 5, 5, 4, 4, 3, 3, 2, 2, 1, 1, 1, 1, 1,
    ]
    assert len(C.PIECE_KINDS) == 48
    for i, value in enumerate(expected):
        assert C.PIECE_KINDS[i] == value, f"PIECE_KINDS[{i}]"


def test_attack_defense_full_table():
    expected = [0, 0, 1, 1, 0, 0, 0, 1, 0, 1, 1, 0, 0, 0, 1]
    assert len(C.ATTACK_DEFENSE_INDEX) == 15
    for i, value in enumerate(expected):
        assert C.ATTACK_DEFENSE_INDEX[i] == value, f"ATTACK_DEFENSE_INDEX[{i}]"


def test_piece_scores_full_table():
    expected = [
        0,
        100, 200, 200, 610, 490, 1300, 3000,
        100, 200, 200, 610, 490, 1300, 3000,
    ]
    assert len(C.PIECE_SCORES) == 15
    for i, value in enumerate(expected):
        assert C.PIECE_SCORES[i] == value, f"PIECE_SCORES[{i}]"


def test_global_tables_are_readonly():
    for table in (C.PIECE_ROLES, C.PIECE_KINDS, C.ATTACK_DEFENSE_INDEX, C.PIECE_SCORES):
        assert table.flags.writeable is False
        with np.testing.assert_raises(ValueError):
            table[0] = 1


def test_coordinate_conversion():
    assert C.xy_to_site(0, 0) == 81
    assert C.xy_to_site(8, 9) == 8
    assert C.site_to_xy(81) == (0, 0)
    assert C.site_to_xy(8) == (8, 9)
    for site in range(90):
        x, y = C.site_to_xy(site)
        assert C.xy_to_site(x, y) == site


def test_play_of_site():
    assert C.play_of_site(C.xy_to_site(4, 0)) == C.RED
    assert C.play_of_site(C.xy_to_site(4, 9)) == C.BLACK
    assert C.play_of_site(44) == C.BLACK
    assert C.play_of_site(45) == C.RED


def test_play_of_piece():
    for idx in range(16, 32):
        assert C.play_of_piece(idx) == C.BLACK
    for idx in range(32, 48):
        assert C.play_of_piece(idx) == C.RED


def test_move_packing_full_enumeration():
    for src in range(90):
        for dest in range(90):
            m = C.pack_move(src, dest)
            assert C.move_src(m) == src
            assert C.move_dest(m) == dest


def test_move_packing_numpy_scalars():
    for src, dest in ((np.int8(10), np.int8(20)), (np.int64(88), np.int64(89))):
        m = C.pack_move(src, dest)
        assert isinstance(m, int)
        assert C.move_src(m) == src
        assert C.move_dest(m) == dest


def test_base_scores():
    assert C.PIECE_SCORES[C.RED_KING] == 3000
    assert C.PIECE_SCORES[C.RED_CHARIOT] == 1300
    assert C.PIECE_SCORES[C.BLACK_SOLDIER] == 100
    assert C.MAX_SCORE == 9999
    assert C.LONG_CHECK_SCORE == 8888
