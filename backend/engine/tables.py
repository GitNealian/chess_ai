"""基础预生成表：马/象/士/将/兵、危险区、攻击限制表与车炮行列表。

Java 参考：ChessInitialize.java 的 initKnightMove / initElephantMove /
initSoldier / preBitBoardKingMove / preBitBoardGuardMove /
preKingCheckedSoldierBitBoards / preBitBoardAttack / initChariotGunVariedMove /
initGunFackEatMove / preGunAndChariotBitBoardAttack，以及 SearchEngine.java
的 DangerMarginBit。

约定：
- 表为模块级 numpy 只读数组，导入时一次性构建；
- 马/象腿位折叠键一律调用 bitboard.check_sum_knight / check_sum_elephant，
  禁止内联公式；
- 马/象攻击限制表覆盖全部腿位组合，包括"全部腿位被占据"（空腿集为空集）
  的边界：Java 的 getAllLegCombByLeg 只枚举非空腿位子集，该键在 Java 表中
  没有条目（以此键查表会取到空引用），Python 侧显式补齐；
- 折叠键碰撞时保持 Java 的后写覆盖语义（实测马 0 次、象 4 次碰撞）；
- 车炮行/列表第二维是行/列占据掩码：行掩码 boardBitRow 的 bit k 对应列 8-k
  （棋子自身位 = 1<<(8-col)），列掩码 boardBitCol 的 bit k 对应行 9-k
  （棋子自身位 = 1<<(9-row)）；掩码不含棋子自身位时该组合为空掩码。
"""

import itertools
import time

import numpy as np

from . import bitboard
from . import constants as C

__all__ = [
    "BUILD_SECONDS",
    "CHARIOT_ATTACK_COL_HI",
    "CHARIOT_ATTACK_COL_LO",
    "CHARIOT_ATTACK_ROW_HI",
    "CHARIOT_ATTACK_ROW_LO",
    "CHARIOT_GUN_MOBILITY_COL",
    "CHARIOT_GUN_MOBILITY_ROW",
    "DANGER_MARGIN_HI",
    "DANGER_MARGIN_LO",
    "ELEPHANT_ATTACK_LIMIT_HI",
    "ELEPHANT_ATTACK_LIMIT_LO",
    "ELEPHANT_LEG_HI",
    "ELEPHANT_LEG_LO",
    "ELEPHANT_TARGET_HI",
    "ELEPHANT_TARGET_LO",
    "FOLD_CHECKED",
    "FOLD_COLLISIONS",
    "GUARD_TARGET_HI",
    "GUARD_TARGET_LO",
    "GUN_ATTACK_COL_HI",
    "GUN_ATTACK_COL_LO",
    "GUN_ATTACK_ROW_HI",
    "GUN_ATTACK_ROW_LO",
    "GUN_FAKE_ATTACK_COL_HI",
    "GUN_FAKE_ATTACK_COL_LO",
    "GUN_FAKE_ATTACK_ROW_HI",
    "GUN_FAKE_ATTACK_ROW_LO",
    "GUN_MORE_REST_ATTACK_COL_HI",
    "GUN_MORE_REST_ATTACK_COL_LO",
    "GUN_MORE_REST_ATTACK_ROW_HI",
    "GUN_MORE_REST_ATTACK_ROW_LO",
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
    "MOVE_CHARIOT_GUN_COL_HI",
    "MOVE_CHARIOT_GUN_COL_LO",
    "MOVE_CHARIOT_GUN_ROW_HI",
    "MOVE_CHARIOT_GUN_ROW_LO",
    "SOLDIER_TARGET_HI",
    "SOLDIER_TARGET_LO",
    "chariot_attack_col",
    "chariot_attack_row",
    "chariot_gun_mobility_col",
    "chariot_gun_mobility_row",
    "count",
    "danger_margin",
    "elephant_leg_keys",
    "elephant_targets",
    "elephant_targets_limit",
    "empty",
    "fold_elephant_key",
    "fold_knight_key",
    "guard_targets",
    "gun_attack_col",
    "gun_attack_row",
    "gun_fake_attack_col",
    "gun_fake_attack_row",
    "gun_more_rest_attack_col",
    "gun_more_rest_attack_row",
    "king_checked_soldier_sites",
    "king_targets",
    "knight_leg_keys",
    "knight_targets",
    "knight_targets_limit",
    "lowest_site",
    "move_chariot_gun_col",
    "move_chariot_gun_row",
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

    返回 (折叠键碰撞次数, 覆盖的组合总数)；碰撞时保持后写覆盖。
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
        checked += len(combos)
    return collisions, checked


# ---- 车炮行/列预生成表（Java initChariotGunVariedMove / initGunFackEatMove）----
#
# 第二维是"该行/该列的占据掩码"，与 Java 一致：
# - 行：boardBitRow 的 bit k 对应真实列 8-k，共 2^9 = 512 种；
# - 列：boardBitCol 的 bit k 对应真实行 9-k，共 2^10 = 1024 种。
# Java 先生成"按棋子所在列/行索引的本地相对偏移表"，再由
# preGunAndChariotBitBoardAttack 展开为 90 坐标；此处直接输出 (lo, hi)。

_ROW_MASK_BITS = 9
_COL_MASK_BITS = 10
_ROW_MASK_COUNT = 1 << _ROW_MASK_BITS
_COL_MASK_COUNT = 1 << _COL_MASK_BITS

_MODES = ("chariot", "move", "gun", "fake", "more")
_ROW_TABLE_NAMES = {
    "chariot": "CHARIOT_ATTACK_ROW",
    "move": "MOVE_CHARIOT_GUN_ROW",
    "gun": "GUN_ATTACK_ROW",
    "fake": "GUN_FAKE_ATTACK_ROW",
    "more": "GUN_MORE_REST_ATTACK_ROW",
}
_COL_TABLE_NAMES = {
    mode: name.replace("_ROW", "_COL") for mode, name in _ROW_TABLE_NAMES.items()
}

_POW2_TO_BIT = [0] * (_COL_MASK_COUNT + 1)
for _k in range(_COL_MASK_BITS + 1):
    _POW2_TO_BIT[1 << _k] = _k
del _k


def _scan_local_bits(mask, index, size, mode):
    """局部掩码扫描（对应 Java 沿 i±1 两个方向的循环）。

    mask：行/列占据掩码；index：棋子自身位索引；size：位宽（行 9 / 列 10）。
    返回落点的局部位掩码：方向 A = 位索引增大（行向左 / 列向上），
    方向 B = 位索引减小（行向右 / 列向下），两方向结果取并集。
    """
    s = 1 << index
    full = (1 << size) - 1
    above = mask & ~((s << 1) - 1)
    below = mask & (s - 1)
    first_up = above & -above
    first_down = 0 if below == 0 else 1 << (below.bit_length() - 1)
    out = 0
    if mode == "move":
        # 平移：记录空格，遇第一个阻挡停（不含阻挡格）
        out |= (
            (full ^ ((s << 1) - 1))
            if first_up == 0
            else ((first_up - 1) ^ ((s << 1) - 1))
        )
    elif mode == "chariot":
        # 车吃子：记录第一个阻挡并停
        out |= first_up
    elif mode == "gun":
        # 炮吃子：跳过第一个阻挡（炮架），记录第二个阻挡
        if first_up:
            rest = above & ~((first_up << 1) - 1)
            out |= rest & -rest
    elif mode == "fake":
        # 压制位：炮架之后的空位，直到第二个阻挡
        if first_up:
            rest = above & ~((first_up << 1) - 1)
            second_up = rest & -rest
            out |= (
                (full ^ ((first_up << 1) - 1))
                if second_up == 0
                else ((second_up - 1) ^ ((first_up << 1) - 1))
            )
    elif first_up:
        # 隔两子：跳过前两个阻挡，记录第三个阻挡
        rest = above & ~((first_up << 1) - 1)
        second_up = rest & -rest
        if second_up:
            rest2 = rest & ~((second_up << 1) - 1)
            out |= rest2 & -rest2
    if mode == "move":
        out |= (
            (s - 1)
            if first_down == 0
            else ((s - 1) ^ ((first_down << 1) - 1))
        )
    elif mode == "chariot":
        out |= first_down
    elif mode == "gun":
        if first_down:
            rest = below & (first_down - 1)
            if rest:
                out |= 1 << (rest.bit_length() - 1)
    elif mode == "fake":
        if first_down:
            rest = below & (first_down - 1)
            second_down = 0 if rest == 0 else 1 << (rest.bit_length() - 1)
            out |= (
                (first_down - 1)
                if second_down == 0
                else ((first_down - 1) ^ ((second_down << 1) - 1))
            )
    elif first_down:
        rest = below & (first_down - 1)
        second_down = 0 if rest == 0 else 1 << (rest.bit_length() - 1)
        if second_down:
            rest2 = rest & (second_down - 1)
            if rest2:
                out |= 1 << (rest2.bit_length() - 1)
    return out


def _local_bits_to_mask(bits, site, axis):
    """局部位掩码 → 90 坐标 (lo, hi)。

    axis 0（行）：bit k ↔ 列 8-k；axis 1（列）：bit k ↔ 行 9-k。
    lo 的 bit63（site 63）按 int64 位模式以负数存储，与 bitboard.site_mask 一致。
    """
    lo = 0
    hi = 0
    if axis == 0:
        row = site // 9
        while bits:
            bit = bits & -bits
            dest = row * 9 + (8 - _POW2_TO_BIT[bit])
            bits ^= bit
            if dest < 64:
                lo |= 1 << dest
            else:
                hi |= 1 << (dest - 64)
    else:
        col = site % 9
        while bits:
            bit = bits & -bits
            dest = (9 - _POW2_TO_BIT[bit]) * 9 + col
            bits ^= bit
            if dest < 64:
                lo |= 1 << dest
            else:
                hi |= 1 << (dest - 64)
    if lo >= 1 << 63:
        lo -= 1 << 64
    return lo, hi


def _build_chariot_gun_tables():
    """构建全部 [site][mask] 组合的车炮行列表，返回 {表名: ndarray}。"""
    row_lo = {mode: [0] * (90 * _ROW_MASK_COUNT) for mode in _MODES}
    row_hi = {mode: [0] * (90 * _ROW_MASK_COUNT) for mode in _MODES}
    col_lo = {mode: [0] * (90 * _COL_MASK_COUNT) for mode in _MODES}
    col_hi = {mode: [0] * (90 * _COL_MASK_COUNT) for mode in _MODES}
    row_mobility = [0] * (90 * _ROW_MASK_COUNT)
    col_mobility = [0] * (90 * _COL_MASK_COUNT)

    for site in range(90):
        row, col = divmod(site, 9)
        index_row = 8 - col
        index_col = 9 - row
        own_row = 1 << index_row
        own_col = 1 << index_col
        base_row = site * _ROW_MASK_COUNT
        base_col = site * _COL_MASK_COUNT
        for mask in range(_ROW_MASK_COUNT):
            if not mask & own_row:
                continue
            move_bits = _scan_local_bits(mask, index_row, _ROW_MASK_BITS, "move")
            row_mobility[base_row + mask] = move_bits.bit_count()
            for mode in _MODES:
                bits = (
                    move_bits
                    if mode == "move"
                    else _scan_local_bits(mask, index_row, _ROW_MASK_BITS, mode)
                )
                lo, hi = _local_bits_to_mask(bits, site, 0)
                row_lo[mode][base_row + mask] = lo
                row_hi[mode][base_row + mask] = hi
        for mask in range(_COL_MASK_COUNT):
            if not mask & own_col:
                continue
            move_bits = _scan_local_bits(mask, index_col, _COL_MASK_BITS, "move")
            col_mobility[base_col + mask] = move_bits.bit_count()
            for mode in _MODES:
                bits = (
                    move_bits
                    if mode == "move"
                    else _scan_local_bits(mask, index_col, _COL_MASK_BITS, mode)
                )
                lo, hi = _local_bits_to_mask(bits, site, 1)
                col_lo[mode][base_col + mask] = lo
                col_hi[mode][base_col + mask] = hi

    tables = {}
    for mode in _MODES:
        row_name = _ROW_TABLE_NAMES[mode]
        col_name = _COL_TABLE_NAMES[mode]
        tables[f"{row_name}_LO"] = np.array(
            row_lo[mode], dtype=np.int64
        ).reshape(90, _ROW_MASK_COUNT)
        tables[f"{row_name}_HI"] = np.array(
            row_hi[mode], dtype=np.int64
        ).reshape(90, _ROW_MASK_COUNT)
        tables[f"{col_name}_LO"] = np.array(
            col_lo[mode], dtype=np.int64
        ).reshape(90, _COL_MASK_COUNT)
        tables[f"{col_name}_HI"] = np.array(
            col_hi[mode], dtype=np.int64
        ).reshape(90, _COL_MASK_COUNT)
    tables["CHARIOT_GUN_MOBILITY_ROW"] = np.array(
        row_mobility, dtype=np.int16
    ).reshape(90, _ROW_MASK_COUNT)
    tables["CHARIOT_GUN_MOBILITY_COL"] = np.array(
        col_mobility, dtype=np.int16
    ).reshape(90, _COL_MASK_COUNT)
    return tables


def _build_basic_tables():
    """构建全部预生成表并自检，返回 (表字典, 折叠键碰撞数, 覆盖组合总数)。"""
    mask_site_lo = np.zeros(90, dtype=np.int64)
    mask_site_hi = np.zeros(90, dtype=np.int64)
    knight_target_lo = np.zeros(90, dtype=np.int64)
    knight_target_hi = np.zeros(90, dtype=np.int64)
    knight_leg_lo = np.zeros(90, dtype=np.int64)
    knight_leg_hi = np.zeros(90, dtype=np.int64)
    elephant_target_lo = np.zeros(90, dtype=np.int64)
    elephant_target_hi = np.zeros(90, dtype=np.int64)
    elephant_leg_lo = np.zeros(90, dtype=np.int64)
    elephant_leg_hi = np.zeros(90, dtype=np.int64)
    king_target_lo = np.zeros(90, dtype=np.int64)
    king_target_hi = np.zeros(90, dtype=np.int64)
    guard_target_lo = np.zeros(90, dtype=np.int64)
    guard_target_hi = np.zeros(90, dtype=np.int64)
    soldier_target_lo = np.zeros((2, 90), dtype=np.int64)
    soldier_target_hi = np.zeros((2, 90), dtype=np.int64)
    king_checked_soldier_lo = np.zeros(90, dtype=np.int64)
    king_checked_soldier_hi = np.zeros(90, dtype=np.int64)
    danger_margin_lo = np.zeros(2, dtype=np.int64)
    danger_margin_hi = np.zeros(2, dtype=np.int64)
    knight_attack_limit_lo = np.zeros((90, _ATTACK_LIMIT_KEYS), dtype=np.int64)
    knight_attack_limit_hi = np.zeros((90, _ATTACK_LIMIT_KEYS), dtype=np.int64)
    knight_mobility = np.zeros((90, _ATTACK_LIMIT_KEYS), dtype=np.int16)
    elephant_attack_limit_lo = np.zeros((90, _ATTACK_LIMIT_KEYS), dtype=np.int64)
    elephant_attack_limit_hi = np.zeros((90, _ATTACK_LIMIT_KEYS), dtype=np.int64)

    for site in range(90):
        mask_lo, mask_hi = bitboard.site_mask(site)
        mask_site_lo[site] = mask_lo
        mask_site_hi[site] = mask_hi

        moves = _knight_moves(site)
        _store(knight_target_lo, knight_target_hi, site, [t for t, _ in moves])
        _store(knight_leg_lo, knight_leg_hi, site, [leg for _, leg in moves])

        moves = _elephant_moves(site)
        _store(elephant_target_lo, elephant_target_hi, site, [t for t, _ in moves])
        _store(elephant_leg_lo, elephant_leg_hi, site, [eye for _, eye in moves])

        _store(king_target_lo, king_target_hi, site, _king_moves(site))
        _store(guard_target_lo, guard_target_hi, site, _guard_moves(site))

        # Java preKingCheckedSoldierBitBoards：正交邻格，Count==4 时去掉背向邻格
        legs = _ordered_unique([leg for _, leg in _knight_moves(site)])
        if len(legs) == 4:
            drop = site - 9 if site < 45 else site + 9
            legs = [leg for leg in legs if leg != drop]
        _store(king_checked_soldier_lo, king_checked_soldier_hi, site, legs)

    for play in (C.BLACK, C.RED):
        for site in range(90):
            _store(
                soldier_target_lo,
                soldier_target_hi,
                (play, site),
                _soldier_moves(play, site),
            )

    _store(danger_margin_lo, danger_margin_hi, C.BLACK, _BLACK_DANGER_SITES)
    _store(danger_margin_lo, danger_margin_hi, C.RED, _RED_DANGER_SITES)

    knight_collisions, knight_checked = _fill_attack_limit(
        knight_attack_limit_lo,
        knight_attack_limit_hi,
        _knight_moves,
        bitboard.check_sum_knight,
        knight_mobility,
    )
    elephant_collisions, elephant_checked = _fill_attack_limit(
        elephant_attack_limit_lo,
        elephant_attack_limit_hi,
        _elephant_moves,
        bitboard.check_sum_elephant,
        None,
    )

    tables = {
        "MASK_SITE_LO": mask_site_lo,
        "MASK_SITE_HI": mask_site_hi,
        "KNIGHT_TARGET_LO": knight_target_lo,
        "KNIGHT_TARGET_HI": knight_target_hi,
        "KNIGHT_LEG_LO": knight_leg_lo,
        "KNIGHT_LEG_HI": knight_leg_hi,
        "ELEPHANT_TARGET_LO": elephant_target_lo,
        "ELEPHANT_TARGET_HI": elephant_target_hi,
        "ELEPHANT_LEG_LO": elephant_leg_lo,
        "ELEPHANT_LEG_HI": elephant_leg_hi,
        "KING_TARGET_LO": king_target_lo,
        "KING_TARGET_HI": king_target_hi,
        "GUARD_TARGET_LO": guard_target_lo,
        "GUARD_TARGET_HI": guard_target_hi,
        "SOLDIER_TARGET_LO": soldier_target_lo,
        "SOLDIER_TARGET_HI": soldier_target_hi,
        "KING_CHECKED_SOLDIER_LO": king_checked_soldier_lo,
        "KING_CHECKED_SOLDIER_HI": king_checked_soldier_hi,
        "DANGER_MARGIN_LO": danger_margin_lo,
        "DANGER_MARGIN_HI": danger_margin_hi,
        "KNIGHT_ATTACK_LIMIT_LO": knight_attack_limit_lo,
        "KNIGHT_ATTACK_LIMIT_HI": knight_attack_limit_hi,
        "KNIGHT_MOBILITY": knight_mobility,
        "ELEPHANT_ATTACK_LIMIT_LO": elephant_attack_limit_lo,
        "ELEPHANT_ATTACK_LIMIT_HI": elephant_attack_limit_hi,
    }
    tables.update(_build_chariot_gun_tables())
    folds = {
        "knight": (knight_collisions, knight_checked),
        "elephant": (elephant_collisions, elephant_checked),
    }
    return tables, folds


def _build_and_freeze():
    start = time.perf_counter()
    tables, folds = _build_basic_tables()
    for table in tables.values():
        table.setflags(write=False)
    return tables, folds, time.perf_counter() - start


_TABLES, _FOLDS, BUILD_SECONDS = _build_and_freeze()

FOLD_COLLISIONS = {name: collisions for name, (collisions, _) in _FOLDS.items()}
FOLD_CHECKED = {name: checked for name, (_, checked) in _FOLDS.items()}
assert FOLD_COLLISIONS["knight"] == 0, "马腿位折叠键不应碰撞"

MASK_SITE_LO = _TABLES["MASK_SITE_LO"]
MASK_SITE_HI = _TABLES["MASK_SITE_HI"]
KNIGHT_TARGET_LO = _TABLES["KNIGHT_TARGET_LO"]
KNIGHT_TARGET_HI = _TABLES["KNIGHT_TARGET_HI"]
KNIGHT_LEG_LO = _TABLES["KNIGHT_LEG_LO"]
KNIGHT_LEG_HI = _TABLES["KNIGHT_LEG_HI"]
ELEPHANT_TARGET_LO = _TABLES["ELEPHANT_TARGET_LO"]
ELEPHANT_TARGET_HI = _TABLES["ELEPHANT_TARGET_HI"]
ELEPHANT_LEG_LO = _TABLES["ELEPHANT_LEG_LO"]
ELEPHANT_LEG_HI = _TABLES["ELEPHANT_LEG_HI"]
KING_TARGET_LO = _TABLES["KING_TARGET_LO"]
KING_TARGET_HI = _TABLES["KING_TARGET_HI"]
GUARD_TARGET_LO = _TABLES["GUARD_TARGET_LO"]
GUARD_TARGET_HI = _TABLES["GUARD_TARGET_HI"]
SOLDIER_TARGET_LO = _TABLES["SOLDIER_TARGET_LO"]
SOLDIER_TARGET_HI = _TABLES["SOLDIER_TARGET_HI"]
KING_CHECKED_SOLDIER_LO = _TABLES["KING_CHECKED_SOLDIER_LO"]
KING_CHECKED_SOLDIER_HI = _TABLES["KING_CHECKED_SOLDIER_HI"]
DANGER_MARGIN_LO = _TABLES["DANGER_MARGIN_LO"]
DANGER_MARGIN_HI = _TABLES["DANGER_MARGIN_HI"]
KNIGHT_ATTACK_LIMIT_LO = _TABLES["KNIGHT_ATTACK_LIMIT_LO"]
KNIGHT_ATTACK_LIMIT_HI = _TABLES["KNIGHT_ATTACK_LIMIT_HI"]
KNIGHT_MOBILITY = _TABLES["KNIGHT_MOBILITY"]
ELEPHANT_ATTACK_LIMIT_LO = _TABLES["ELEPHANT_ATTACK_LIMIT_LO"]
ELEPHANT_ATTACK_LIMIT_HI = _TABLES["ELEPHANT_ATTACK_LIMIT_HI"]
CHARIOT_ATTACK_ROW_LO = _TABLES["CHARIOT_ATTACK_ROW_LO"]
CHARIOT_ATTACK_ROW_HI = _TABLES["CHARIOT_ATTACK_ROW_HI"]
MOVE_CHARIOT_GUN_ROW_LO = _TABLES["MOVE_CHARIOT_GUN_ROW_LO"]
MOVE_CHARIOT_GUN_ROW_HI = _TABLES["MOVE_CHARIOT_GUN_ROW_HI"]
GUN_ATTACK_ROW_LO = _TABLES["GUN_ATTACK_ROW_LO"]
GUN_ATTACK_ROW_HI = _TABLES["GUN_ATTACK_ROW_HI"]
GUN_FAKE_ATTACK_ROW_LO = _TABLES["GUN_FAKE_ATTACK_ROW_LO"]
GUN_FAKE_ATTACK_ROW_HI = _TABLES["GUN_FAKE_ATTACK_ROW_HI"]
GUN_MORE_REST_ATTACK_ROW_LO = _TABLES["GUN_MORE_REST_ATTACK_ROW_LO"]
GUN_MORE_REST_ATTACK_ROW_HI = _TABLES["GUN_MORE_REST_ATTACK_ROW_HI"]
CHARIOT_GUN_MOBILITY_ROW = _TABLES["CHARIOT_GUN_MOBILITY_ROW"]
CHARIOT_ATTACK_COL_LO = _TABLES["CHARIOT_ATTACK_COL_LO"]
CHARIOT_ATTACK_COL_HI = _TABLES["CHARIOT_ATTACK_COL_HI"]
MOVE_CHARIOT_GUN_COL_LO = _TABLES["MOVE_CHARIOT_GUN_COL_LO"]
MOVE_CHARIOT_GUN_COL_HI = _TABLES["MOVE_CHARIOT_GUN_COL_HI"]
GUN_ATTACK_COL_LO = _TABLES["GUN_ATTACK_COL_LO"]
GUN_ATTACK_COL_HI = _TABLES["GUN_ATTACK_COL_HI"]
GUN_FAKE_ATTACK_COL_LO = _TABLES["GUN_FAKE_ATTACK_COL_LO"]
GUN_FAKE_ATTACK_COL_HI = _TABLES["GUN_FAKE_ATTACK_COL_HI"]
GUN_MORE_REST_ATTACK_COL_LO = _TABLES["GUN_MORE_REST_ATTACK_COL_LO"]
GUN_MORE_REST_ATTACK_COL_HI = _TABLES["GUN_MORE_REST_ATTACK_COL_HI"]
CHARIOT_GUN_MOBILITY_COL = _TABLES["CHARIOT_GUN_MOBILITY_COL"]


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


def chariot_attack_row(site, mask):
    return int(CHARIOT_ATTACK_ROW_LO[site, mask]), int(CHARIOT_ATTACK_ROW_HI[site, mask])


def move_chariot_gun_row(site, mask):
    return int(MOVE_CHARIOT_GUN_ROW_LO[site, mask]), int(MOVE_CHARIOT_GUN_ROW_HI[site, mask])


def gun_attack_row(site, mask):
    return int(GUN_ATTACK_ROW_LO[site, mask]), int(GUN_ATTACK_ROW_HI[site, mask])


def gun_fake_attack_row(site, mask):
    return int(GUN_FAKE_ATTACK_ROW_LO[site, mask]), int(GUN_FAKE_ATTACK_ROW_HI[site, mask])


def gun_more_rest_attack_row(site, mask):
    return int(GUN_MORE_REST_ATTACK_ROW_LO[site, mask]), int(
        GUN_MORE_REST_ATTACK_ROW_HI[site, mask]
    )


def chariot_gun_mobility_row(site, mask):
    return int(CHARIOT_GUN_MOBILITY_ROW[site, mask])


def chariot_attack_col(site, mask):
    return int(CHARIOT_ATTACK_COL_LO[site, mask]), int(CHARIOT_ATTACK_COL_HI[site, mask])


def move_chariot_gun_col(site, mask):
    return int(MOVE_CHARIOT_GUN_COL_LO[site, mask]), int(MOVE_CHARIOT_GUN_COL_HI[site, mask])


def gun_attack_col(site, mask):
    return int(GUN_ATTACK_COL_LO[site, mask]), int(GUN_ATTACK_COL_HI[site, mask])


def gun_fake_attack_col(site, mask):
    return int(GUN_FAKE_ATTACK_COL_LO[site, mask]), int(GUN_FAKE_ATTACK_COL_HI[site, mask])


def gun_more_rest_attack_col(site, mask):
    return int(GUN_MORE_REST_ATTACK_COL_LO[site, mask]), int(
        GUN_MORE_REST_ATTACK_COL_HI[site, mask]
    )


def chariot_gun_mobility_col(site, mask):
    return int(CHARIOT_GUN_MOBILITY_COL[site, mask])


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
