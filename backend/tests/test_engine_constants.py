import numpy as np
import pytest

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


def test_attack_defense_classification():
    assert C.ATTACK_DEFENSE_INDEX[C.RED_SOLDIER] == 0
    assert C.ATTACK_DEFENSE_INDEX[C.RED_GUARD] == 1
    assert C.ATTACK_DEFENSE_INDEX[C.BLACK_KING] == 1
    assert C.ATTACK_DEFENSE_INDEX[C.BLACK_GUN] == 0


def test_coordinate_conversion():
    assert C.xy_to_site(0, 0) == 81
    assert C.xy_to_site(8, 9) == 8
    assert C.site_to_xy(81) == (0, 0)
    assert C.site_to_xy(8) == (8, 9)
    for site in range(90):
        x, y = C.site_to_xy(site)
        assert C.xy_to_site(x, y) == site


def test_move_packing():
    for src in (0, 81, 89):
        for dest in (0, 45, 89):
            m = C.pack_move(src, dest)
            assert C.move_src(m) == src
            assert C.move_dest(m) == dest


def test_base_scores():
    assert C.PIECE_SCORES[C.RED_KING] == 3000
    assert C.PIECE_SCORES[C.RED_CHARIOT] == 1300
    assert C.PIECE_SCORES[C.BLACK_SOLDIER] == 100
    assert C.MAX_SCORE == 9999
    assert C.LONG_CHECK_SCORE == 8888
