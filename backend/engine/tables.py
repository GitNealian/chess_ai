"""基础预生成表：马/象/士/将/兵、危险区与攻击限制表。

Java 参考：ChessInitialize.java 的 initKnightMove / initElephantMove /
initSoldier / preBitBoardKingMove / preBitBoardGuardMove /
preKingCheckedSoldierBitBoards / preBitBoardAttack，以及 SearchEngine.java
的 DangerMarginBit。

约定：
- 表为模块级 numpy 只读数组，导入时一次性构建；
- 马/象腿位折叠键一律调用 bitboard.check_sum_knight / check_sum_elephant，
  禁止内联公式；
- 马/象攻击限制表在 Java 枚举的非空空腿集之外，额外补充"全部腿位被占据"
  （空腿集为空集）的边界情形，Java 在该情形会 NPE。
"""

import itertools
import time

import numpy as np

from . import bitboard
from . import constants as C

__all__ = [
    "DANGER_MARGIN_HI",
    "DANGER_MARGIN_LO",
    "ELEPHANT_ATTACK_LIMIT_HI",
    "ELEPHANT_ATTACK_LIMIT_LO",
    "ELEPHANT_LEG_HI",
    "ELEPHANT_LEG_LO",
    "ELEPHANT_TARGET_HI",
    "ELEPHANT_TARGET_LO",
    "GUARD_TARGET_HI",
    "GUARD_TARGET_LO",
    "KING_CHECKED_SOLDIER_HI",
    "KING_CHECKED_SOLDIER_LO",
    "KING_TARGET_HI",
    "KING_TARGET_LO",
    "KNIGHT_ATTACK_LIMIT_HI",
    "KNIGHT_ATTACK_LIMIT_LO",
    "KNIGHT_LEG_HI",
    "KNIGHT_LEG_LO",
    "KNIGHT_MOBILITY",
    "KNIGHT_TARGET_HI",
    "KNIGHT_TARGET_LO",
    "MASK_SITE_HI",
    "MASK_SITE_LO",
    "SOLDIER_TARGET_HI",
    "SOLDIER_TARGET_LO",
    "count",
    "danger_margin",
    "elephant_leg_keys",
    "elephant_targets",
    "elephant_targets_limit",
    "empty",
    "fold_elephant_key",
    "fold_knight_key",
    "guard_targets",
    "king_checked_soldier_sites",
    "king_targets",
    "knight_leg_keys",
    "knight_targets",
    "knight_targets_limit",
    "lowest_site",
    "soldier_targets",
    "unpack_sites",
]

count = bitboard.count
empty = bitboard.empty
lowest_site = bitboard.lowest_site

_ATTACK_LIMIT_KEYS = 200

# 走法方向：(dr, dc, leg_dr, leg_dc)，顺序与 Java initKnightMove 的偏移顺序一致。
_KNIGHT_MOVES = (
    (-2, -1, -1, 0),
    (-2, 1, -1, 0),
    (-1, -2, 0, -1),
    (-1, 2, 0, 1),
    (1, -2, 0, -1),
    (1, 2, 0, 1),
    (2, -1, 1, 0),
    (2, 1, 1, 0),
)

# 走法方向：(dr, dc, eye_dr, eye_dc)，顺序与 Java initElephantMove 一致。
_ELEPHANT_MOVES = (
    (-2, -2, -1, -1),
    (-2, 2, -1, 1),
    (2, -2, 1, -1),
    (2, 2, 1, 1),
)

_KING_MOVES = ((-1, 0), (1, 0), (0, -1), (0, 1))
_GUARD_MOVES = ((-1, -1), (-1, 1), (1, -1), (1, 1))

# 士的合法位置（九宫四角 + 中心），对应 Java preBitBoardGuardMove 的 10 个 case
_GUARD_SITES = frozenset((3, 5, 13, 21, 23, 66, 68, 76, 84, 86))

# 与 Java SearchEngine.blackDangerMarginArray / redDangerMarginArray 逐值一致：
# 黑方 = row0-2 + row3 的 col3-5；红方 = row6 的 col3-5 + row7-9。
_BLACK_DANGER_SITES = list(range(0, 27)) + [30, 31, 32]
_RED_DANGER_SITES = [57, 58, 59] + list(range(63, 90))


def _in_palace(row, col):
    if not (0 <= row < 10 and 3 <= col <= 5):
        return False
    return row <= 2 or row >= 7


def _knight_moves(site):
    """返回 [(target, leg), ...]；腿位为"先走一格直线"的正交邻格。"""
    row, col = divmod(site, 9)
    moves = []
    for dr, dc, lr, lc in _KNIGHT_MOVES:
        tr, tc = row + dr, col + dc
        br, bc = row + lr, col + lc
        if 0 <= tr < 10 and 0 <= tc < 9 and 0 <= br < 10 and 0 <= bc < 9:
            moves.append((tr * 9 + tc, br * 9 + bc))
    return moves


def _elephant_moves(site):
    """返回 [(target, eye), ...]；象不过河（目标须与起点同半场）。"""
    row, col = divmod(site, 9)
    moves = []
    for dr, dc, er, ec in _ELEPHANT_MOVES:
        tr, tc = row + dr, col + dc
        if not (0 <= tr < 10 and 0 <= tc < 9):
            continue
        if (row >= 5) != (tr >= 5):
            continue
        br, bc = row + er, col + ec
        if 0 <= br < 10 and 0 <= bc < 9:
            moves.append((tr * 9 + tc, br * 9 + bc))
    return moves


def _king_moves(site):
    """九宫内直一步；与 Java preBitBoardKingMove 一致，仅九宫内起点有目标。"""
    row, col = divmod(site, 9)
    if not _in_palace(row, col):
        return []
    moves = []
    for dr, dc in _KING_MOVES:
        tr, tc = row + dr, col + dc
        if _in_palace(tr, tc):
            moves.append(tr * 9 + tc)
    return moves


def _guard_moves(site):
    """九宫内斜一步；与 Java preBitBoardGuardMove 一致，仅 10 个合法士位有目标。"""
    if site not in _GUARD_SITES:
        return []
    row, col = divmod(site, 9)
    moves = []
    for dr, dc in _GUARD_MOVES:
        tr, tc = row + dr, col + dc
        if _in_palace(tr, tc):
            moves.append(tr * 9 + tc)
    return moves


def _soldier_moves(play, site):
    """黑卒前进 row+1、红兵前进 row-1；过河后可横走（顺序同 Java：前、左、右）。"""
    row, col = divmod(site, 9)
    if play == C.BLACK:
        targets = [(row + 1, col)]
        if row >= 5:
            targets += [(row, col - 1), (row, col + 1)]
    else:
        targets = [(row - 1, col)]
        if row <= 4:
            targets += [(row, col - 1), (row, col + 1)]
    return [tr * 9 + tc for tr, tc in targets if 0 <= tr < 10 and 0 <= tc < 9]


def _ordered_unique(values):
    seen = set()
    out = []
    for value in values:
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out


def _leg_combos(legs):
    """空腿位集合的枚举顺序（对齐 Java getAllLegCombByLeg）：
    非空子集按 size 1..n、组内字典序，最后追加空集（全部腿位被占据）。
    """
    combos = []
    for size in range(1, len(legs) + 1):
        combos.extend(itertools.combinations(range(len(legs)), size))
    combos.append(())
    return combos


def _store(lo_arr, hi_arr, index, sites):
    lo, hi = bitboard.mask_from_sites(sites)
    lo_arr[index] = lo
    hi_arr[index] = hi


def _fill_attack_limit(limit_lo, limit_hi, moves_fn, fold_fn, mobility):
    """按 Java preBitBoardAttack 语义填充 [site][legKey] → 攻击位。

    返回 (折叠键碰撞次数, 校验条目数)；碰撞时保持后写覆盖。
    """
    collisions = 0
    checked = 0
    for site in range(90):
        moves = moves_fn(site)
        legs = _ordered_unique([leg for _, leg in moves])
        combos = _leg_combos(legs)
        assert len(combos) == 2 ** len(legs)
        expected = {}
        for comb in combos:
            empty_legs = {legs[i] for i in comb}
            att_lo, att_hi = bitboard.mask_from_sites(
                [t for t, leg in moves if leg in empty_legs]
            )
            occ_lo, occ_hi = bitboard.mask_from_sites(
                [leg for _, leg in moves if leg not in empty_legs]
            )
            key = int(fold_fn(occ_lo, occ_hi))
            if not 0 <= key < limit_lo.shape[1]:
                raise AssertionError(f"腿位折叠键越界：site={site} key={key}")
            if key in expected and expected[key] != (int(att_lo), int(att_hi)):
                collisions += 1
            expected[key] = (int(att_lo), int(att_hi))
            limit_lo[site, key] = att_lo
            limit_hi[site, key] = att_hi
            if mobility is not None:
                mobility[site, key] = int(bitboard.count(att_lo, att_hi))
        # 自检：全部 2^n 种腿位组合均已写入，且后写覆盖结果与表一致
        for key, (want_lo, want_hi) in expected.items():
            assert int(limit_lo[site, key]) == want_lo
            assert int(limit_hi[site, key]) == want_hi
            checked += 1
    return collisions, checked


_BUILD_START = time.perf_counter()

MASK_SITE_LO = np.zeros(90, dtype=np.int64)
MASK_SITE_HI = np.zeros(90, dtype=np.int64)
KNIGHT_TARGET_LO = np.zeros(90, dtype=np.int64)
KNIGHT_TARGET_HI = np.zeros(90, dtype=np.int64)
KNIGHT_LEG_LO = np.zeros(90, dtype=np.int64)
KNIGHT_LEG_HI = np.zeros(90, dtype=np.int64)
ELEPHANT_TARGET_LO = np.zeros(90, dtype=np.int64)
ELEPHANT_TARGET_HI = np.zeros(90, dtype=np.int64)
ELEPHANT_LEG_LO = np.zeros(90, dtype=np.int64)
ELEPHANT_LEG_HI = np.zeros(90, dtype=np.int64)
KING_TARGET_LO = np.zeros(90, dtype=np.int64)
KING_TARGET_HI = np.zeros(90, dtype=np.int64)
GUARD_TARGET_LO = np.zeros(90, dtype=np.int64)
GUARD_TARGET_HI = np.zeros(90, dtype=np.int64)
SOLDIER_TARGET_LO = np.zeros((2, 90), dtype=np.int64)
SOLDIER_TARGET_HI = np.zeros((2, 90), dtype=np.int64)
KING_CHECKED_SOLDIER_LO = np.zeros(90, dtype=np.int64)
KING_CHECKED_SOLDIER_HI = np.zeros(90, dtype=np.int64)
DANGER_MARGIN_LO = np.zeros(2, dtype=np.int64)
DANGER_MARGIN_HI = np.zeros(2, dtype=np.int64)
KNIGHT_ATTACK_LIMIT_LO = np.zeros((90, _ATTACK_LIMIT_KEYS), dtype=np.int64)
KNIGHT_ATTACK_LIMIT_HI = np.zeros((90, _ATTACK_LIMIT_KEYS), dtype=np.int64)
KNIGHT_MOBILITY = np.zeros((90, _ATTACK_LIMIT_KEYS), dtype=np.int16)
ELEPHANT_ATTACK_LIMIT_LO = np.zeros((90, _ATTACK_LIMIT_KEYS), dtype=np.int64)
ELEPHANT_ATTACK_LIMIT_HI = np.zeros((90, _ATTACK_LIMIT_KEYS), dtype=np.int64)

for _site in range(90):
    _mask_lo, _mask_hi = bitboard.site_mask(_site)
    MASK_SITE_LO[_site] = _mask_lo
    MASK_SITE_HI[_site] = _mask_hi

    _moves = _knight_moves(_site)
    _store(KNIGHT_TARGET_LO, KNIGHT_TARGET_HI, _site, [t for t, _ in _moves])
    _store(KNIGHT_LEG_LO, KNIGHT_LEG_HI, _site, [leg for _, leg in _moves])

    _moves = _elephant_moves(_site)
    _store(ELEPHANT_TARGET_LO, ELEPHANT_TARGET_HI, _site, [t for t, _ in _moves])
    _store(ELEPHANT_LEG_LO, ELEPHANT_LEG_HI, _site, [eye for _, eye in _moves])

    _store(KING_TARGET_LO, KING_TARGET_HI, _site, _king_moves(_site))
    _store(GUARD_TARGET_LO, GUARD_TARGET_HI, _site, _guard_moves(_site))

    # Java preKingCheckedSoldierBitBoards：正交邻格，Count==4 时去掉背向邻格
    _legs = _ordered_unique([leg for _, leg in _knight_moves(_site)])
    if len(_legs) == 4:
        _drop = _site - 9 if _site < 45 else _site + 9
        _legs = [leg for leg in _legs if leg != _drop]
    _store(KING_CHECKED_SOLDIER_LO, KING_CHECKED_SOLDIER_HI, _site, _legs)

for _play in (C.BLACK, C.RED):
    for _site in range(90):
        _store(
            SOLDIER_TARGET_LO,
            SOLDIER_TARGET_HI,
            (_play, _site),
            _soldier_moves(_play, _site),
        )

_store(DANGER_MARGIN_LO, DANGER_MARGIN_HI, C.BLACK, _BLACK_DANGER_SITES)
_store(DANGER_MARGIN_LO, DANGER_MARGIN_HI, C.RED, _RED_DANGER_SITES)

_FOLD_COLLISIONS, _FOLD_CHECKED = _fill_attack_limit(
    KNIGHT_ATTACK_LIMIT_LO,
    KNIGHT_ATTACK_LIMIT_HI,
    _knight_moves,
    bitboard.check_sum_knight,
    KNIGHT_MOBILITY,
)
_fill_attack_limit(
    ELEPHANT_ATTACK_LIMIT_LO,
    ELEPHANT_ATTACK_LIMIT_HI,
    _elephant_moves,
    bitboard.check_sum_elephant,
    None,
)

_READONLY_TABLES = (
    MASK_SITE_LO,
    MASK_SITE_HI,
    KNIGHT_TARGET_LO,
    KNIGHT_TARGET_HI,
    KNIGHT_LEG_LO,
    KNIGHT_LEG_HI,
    ELEPHANT_TARGET_LO,
    ELEPHANT_TARGET_HI,
    ELEPHANT_LEG_LO,
    ELEPHANT_LEG_HI,
    KING_TARGET_LO,
    KING_TARGET_HI,
    GUARD_TARGET_LO,
    GUARD_TARGET_HI,
    SOLDIER_TARGET_LO,
    SOLDIER_TARGET_HI,
    KING_CHECKED_SOLDIER_LO,
    KING_CHECKED_SOLDIER_HI,
    DANGER_MARGIN_LO,
    DANGER_MARGIN_HI,
    KNIGHT_ATTACK_LIMIT_LO,
    KNIGHT_ATTACK_LIMIT_HI,
    KNIGHT_MOBILITY,
    ELEPHANT_ATTACK_LIMIT_LO,
    ELEPHANT_ATTACK_LIMIT_HI,
)
for _table in _READONLY_TABLES:
    _table.setflags(write=False)

BUILD_SECONDS = time.perf_counter() - _BUILD_START

del _table, _site, _play, _moves, _legs, _drop, _mask_lo, _mask_hi


def unpack_sites(lo, hi):
    """展开 (lo, hi) 掩码为 site 列表（复用 bitboard.iter_sites）。"""
    return list(bitboard.iter_sites(lo, hi))


def fold_knight_key(leg_sites):
    """被占据腿位集合 → 折叠键（内部调用 bitboard.check_sum_knight）。"""
    lo, hi = bitboard.mask_from_sites(leg_sites)
    return int(bitboard.check_sum_knight(lo, hi))


def fold_elephant_key(leg_sites):
    """被占据象眼集合 → 折叠键（内部调用 bitboard.check_sum_elephant）。"""
    lo, hi = bitboard.mask_from_sites(leg_sites)
    return int(bitboard.check_sum_elephant(lo, hi))


def _leg_sites(site):
    """该站点全部马走法的腿位（按走法顺序，可含重复）。"""
    return [leg for _, leg in _knight_moves(site)]


def _knight_moves_with_legs(site):
    """该站点全部马走法 [(target, leg), ...]。"""
    return _knight_moves(site)


def knight_targets(site):
    return int(KNIGHT_TARGET_LO[site]), int(KNIGHT_TARGET_HI[site])


def knight_targets_limit(site, key):
    return int(KNIGHT_ATTACK_LIMIT_LO[site, key]), int(KNIGHT_ATTACK_LIMIT_HI[site, key])


def elephant_targets(site):
    return int(ELEPHANT_TARGET_LO[site]), int(ELEPHANT_TARGET_HI[site])


def elephant_targets_limit(site, key):
    return int(ELEPHANT_ATTACK_LIMIT_LO[site, key]), int(ELEPHANT_ATTACK_LIMIT_HI[site, key])


def guard_targets(site):
    return int(GUARD_TARGET_LO[site]), int(GUARD_TARGET_HI[site])


def king_targets(site):
    return int(KING_TARGET_LO[site]), int(KING_TARGET_HI[site])


def soldier_targets(play, site):
    return int(SOLDIER_TARGET_LO[play, site]), int(SOLDIER_TARGET_HI[play, site])


def king_checked_soldier_sites(site):
    return int(KING_CHECKED_SOLDIER_LO[site]), int(KING_CHECKED_SOLDIER_HI[site])


def danger_margin(play):
    return int(DANGER_MARGIN_LO[play]), int(DANGER_MARGIN_HI[play])


def _leg_keys(site, moves, fold_fn):
    """该站点全部腿位组合的键（含空集，长度 2^n，顺序同 Java 枚举 + 空集）。"""
    legs = _ordered_unique([leg for _, leg in moves])
    keys = []
    for comb in _leg_combos(legs):
        empty_legs = {legs[i] for i in comb}
        occupied = [leg for leg in legs if leg not in empty_legs]
        keys.append(fold_fn(occupied))
    return keys


def knight_leg_keys(site):
    return _leg_keys(site, _knight_moves(site), fold_knight_key)


def elephant_leg_keys(site):
    return _leg_keys(site, _elephant_moves(site), fold_elephant_key)
