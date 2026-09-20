import numpy as np
from numba import njit

SOLDIER = 1
GUARD = 2
ELEPHANT = 3
GUN = 4
KNIGHT = 5
CHARIOT = 6
KING = 7

RED = 1
BLACK = 0

RED_SOLDIER = SOLDIER
RED_GUARD = GUARD
RED_ELEPHANT = ELEPHANT
RED_GUN = GUN
RED_KNIGHT = KNIGHT
RED_CHARIOT = CHARIOT
RED_KING = KING

BLACK_SOLDIER = SOLDIER + 7
BLACK_GUARD = GUARD + 7
BLACK_ELEPHANT = ELEPHANT + 7
BLACK_GUN = GUN + 7
BLACK_KNIGHT = KNIGHT + 7
BLACK_CHARIOT = CHARIOT + 7
BLACK_KING = KING + 7

BLACK_PIECES_START = 16
RED_PIECES_START = 32

PIECE_STARTS = (BLACK_PIECES_START, RED_PIECES_START)

EMPTY = 0
NOTHING = -1

PIECE_ROLES = np.zeros(48, dtype=np.int8)
PIECE_ROLES[16] = BLACK_KING
PIECE_ROLES[17:19] = BLACK_CHARIOT
PIECE_ROLES[19:21] = BLACK_KNIGHT
PIECE_ROLES[21:23] = BLACK_GUN
PIECE_ROLES[23:25] = BLACK_ELEPHANT
PIECE_ROLES[25:27] = BLACK_GUARD
PIECE_ROLES[27:32] = BLACK_SOLDIER
PIECE_ROLES[32] = RED_KING
PIECE_ROLES[33:35] = RED_CHARIOT
PIECE_ROLES[35:37] = RED_KNIGHT
PIECE_ROLES[37:39] = RED_GUN
PIECE_ROLES[39:41] = RED_ELEPHANT
PIECE_ROLES[41:43] = RED_GUARD
PIECE_ROLES[43:48] = RED_SOLDIER

PIECE_KINDS = np.array(
    [0] * 16
    + [
        KING,
        CHARIOT,
        CHARIOT,
        KNIGHT,
        KNIGHT,
        GUN,
        GUN,
        ELEPHANT,
        ELEPHANT,
        GUARD,
        GUARD,
        SOLDIER,
        SOLDIER,
        SOLDIER,
        SOLDIER,
        SOLDIER,
    ]
    * 2,
    dtype=np.int8,
)

ATTACK_DEFENSE_INDEX = np.array(
    [0, 0, 1, 1, 0, 0, 0, 1, 0, 1, 1, 0, 0, 0, 1], dtype=np.int8
)

_BASE_SCORES = [0, 100, 200, 200, 610, 490, 1300, 3000]
PIECE_SCORES = np.array(_BASE_SCORES + _BASE_SCORES[1:], dtype=np.int32)

for _table in (PIECE_ROLES, PIECE_KINDS, ATTACK_DEFENSE_INDEX, PIECE_SCORES):
    _table.setflags(write=False)
del _table

MAX_SCORE = 9999
LONG_CHECK_SCORE = 8888
DRAW_SCORE = 0
MAX_DEPTH = 64
ROOT_START_DEPTH = 4
DEFAULT_START_DEPTH = 6
DEFAULT_MAX_DEPTH = 16
DEFAULT_TIME_LIMIT_MS = 2000


def role_of(kind, play):
    return kind + 7 * (1 - play)


def xy_to_site(x, y):
    return (9 - y) * 9 + x


def site_to_xy(site):
    return site % 9, 9 - site // 9


@njit(cache=True)
def pack_move(src, dest):
    return np.int64(src) | (np.int64(dest) << np.int64(7))


@njit(cache=True)
def move_src(move):
    return np.int64(move) & np.int64(127)


@njit(cache=True)
def move_dest(move):
    return np.int64(move) >> np.int64(7)


def play_of_piece(idx):
    return RED if idx >= RED_PIECES_START else BLACK


def play_of_site(site):
    return RED if site >= 45 else BLACK
