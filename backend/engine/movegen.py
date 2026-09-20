"""着法生成、将军检测与合法性校验。

Java 参考（`ChessMoveAbs.java`）：
- `genEatMoveList/genNopMoveList`（L452-481）与 `chessEatMove/chessNopMove`
  （L574-704）：查表两阶段生成，先全部吃子、再全部非吃子；
- `legalMove`（L226-302）：TT/killer 着法快速校验；
- `checked`（L312-370）：车、飞将、炮、马（验腿）、兵的将军检测；
- `getOppAttackSite/chessAttackSite`（L510-573）：对方全体攻击位并集。

与 Java 一致的约定：
- 第二阶段（非吃子）对车/炮用平移表，对其余棋子用攻击表 ∩ 空格
  （Java 写作 `attack ∩ all ⊕ attack`）；
- 每个棋子内部按 `BitBoard.MSB(play)` 顺序枚举目标：红方 site 升序
  0..89，黑方 81..89、54..80、27..53、0..26；
- 棋子遍历顺序为 `PIECE_STARTS[play]+1 .. +15` 后接将/帅；
- 生成阶段不过滤自将，合法性由 `gen_legal_moves*` 过滤。

与 Java 的防御性差异（正常局面不触发）：
- 己方将已被吃时 `in_check` 返回 True（Java 会越界读取）；
- 对方将已被吃时返回 False（与 Java `checked` L315-317 一致）。
"""

import numpy as np
from numba import njit

from . import bitboard
from . import constants as C
from . import position as _position
from . import tables

__all__ = [
    "MAX_MOVES",
    "gen_moves",
    "gen_moves_into",
    "gen_captures",
    "gen_captures_into",
    "gen_legal_moves",
    "gen_legal_moves_into",
    "in_check",
    "kings_facing",
    "opp_attack_site",
    "legal_move",
]

MAX_MOVES = 128

_PIECE_STARTS = np.array(C.PIECE_STARTS, dtype=np.int64)


@njit(cache=True, inline="always")
def _emit_bits(m, base, src, buf, limit, count):
    """按位序升序把局部掩码的目标写入 buf[count:]，返回新 count。"""
    while m != 0:
        low = m & -m
        idx = bitboard._ctz64(low)
        if count < limit:
            buf[count] = src | ((base + idx) << 7)
            count += 1
        m ^= low
    return count


@njit(cache=True)
def _emit_targets(lo, hi, src, play, buf, count):
    """按 MSB(play) 顺序把掩码中的目标写入 buf[count:]，返回新 count。

    红方（site 升序）：lo 的 bit0..63、hi 的 bit0..25；
    黑方：hi bit17..25（81..89）、lo bit54..63 + hi bit0..16（54..80）、
    lo bit27..53（27..53）、lo bit0..26（0..26）。
    """
    limit = buf.shape[0]
    if play == C.RED:
        count = _emit_bits(lo, 0, src, buf, limit, count)
        return _emit_bits(hi & 0x3FFFFFF, 64, src, buf, limit, count)
    count = _emit_bits((hi >> 17) & 0x1FF, 81, src, buf, limit, count)
    count = _emit_bits(
        ((lo >> 54) & 0x3FF) | ((hi & 0x1FFFF) << 10), 54, src, buf, limit, count
    )
    count = _emit_bits((lo >> 27) & 0x7FFFFFF, 27, src, buf, limit, count)
    return _emit_bits(lo & 0x7FFFFFF, 0, src, buf, limit, count)


@njit(cache=True)
def _target_mask(st, role, src, capture, play):
    """单棋子的目标掩码（未与对方/空格求交）。

    `capture=True` 取吃子表（车的阻挡格、炮的隔子格等），
    `capture=False` 取非吃子表（车/炮平移表，其余为攻击表）。
    """
    row = src // 9
    col = src % 9
    if role == C.RED_CHARIOT or role == C.BLACK_CHARIOT:
        rm = st.bit_row[row]
        cm = st.bit_col[col]
        if capture:
            return (
                tables.CHARIOT_ATTACK_ROW_LO[src, rm] ^ tables.CHARIOT_ATTACK_COL_LO[src, cm],
                tables.CHARIOT_ATTACK_ROW_HI[src, rm] ^ tables.CHARIOT_ATTACK_COL_HI[src, cm],
            )
        return (
            tables.MOVE_CHARIOT_GUN_ROW_LO[src, rm] ^ tables.MOVE_CHARIOT_GUN_COL_LO[src, cm],
            tables.MOVE_CHARIOT_GUN_ROW_HI[src, rm] ^ tables.MOVE_CHARIOT_GUN_COL_HI[src, cm],
        )
    if role == C.RED_GUN or role == C.BLACK_GUN:
        rm = st.bit_row[row]
        cm = st.bit_col[col]
        if capture:
            return (
                tables.GUN_ATTACK_ROW_LO[src, rm] ^ tables.GUN_ATTACK_COL_LO[src, cm],
                tables.GUN_ATTACK_ROW_HI[src, rm] ^ tables.GUN_ATTACK_COL_HI[src, cm],
            )
        return (
            tables.MOVE_CHARIOT_GUN_ROW_LO[src, rm] ^ tables.MOVE_CHARIOT_GUN_COL_LO[src, cm],
            tables.MOVE_CHARIOT_GUN_ROW_HI[src, rm] ^ tables.MOVE_CHARIOT_GUN_COL_HI[src, cm],
        )
    if role == C.RED_KNIGHT or role == C.BLACK_KNIGHT:
        key = bitboard.check_sum_knight(
            tables.KNIGHT_LEG_LO[src] & st.mask_all[0],
            tables.KNIGHT_LEG_HI[src] & st.mask_all[1],
        )
        return tables.KNIGHT_ATTACK_LIMIT_LO[src, key], tables.KNIGHT_ATTACK_LIMIT_HI[src, key]
    if role == C.RED_ELEPHANT or role == C.BLACK_ELEPHANT:
        key = bitboard.check_sum_elephant(
            tables.ELEPHANT_LEG_LO[src] & st.mask_all[0],
            tables.ELEPHANT_LEG_HI[src] & st.mask_all[1],
        )
        return (
            tables.ELEPHANT_ATTACK_LIMIT_LO[src, key],
            tables.ELEPHANT_ATTACK_LIMIT_HI[src, key],
        )
    if role == C.RED_KING or role == C.BLACK_KING:
        return tables.KING_TARGET_LO[src], tables.KING_TARGET_HI[src]
    if role == C.RED_GUARD or role == C.BLACK_GUARD:
        return tables.GUARD_TARGET_LO[src], tables.GUARD_TARGET_HI[src]
    return tables.SOLDIER_TARGET_LO[play, src], tables.SOLDIER_TARGET_HI[play, src]


@njit(cache=True)
def _emit_piece(st, piece, play, capture, opp0, opp1, empty0, empty1, buf, count):
    src = st.all_chess[piece]
    if src < 0:
        return count
    role = C.PIECE_ROLES[piece]
    lo, hi = _target_mask(st, role, src, capture, play)
    if capture:
        lo &= opp0
        hi &= opp1
    else:
        lo &= empty0
        hi &= empty1
    return _emit_targets(lo, hi, src, play, buf, count)


@njit(cache=True)
def _gen_stage(st, play, capture, opp0, opp1, empty0, empty1, buf, count):
    begin = _PIECE_STARTS[play]
    for offset in range(1, 16):
        count = _emit_piece(
            st, begin + offset, play, capture, opp0, opp1, empty0, empty1, buf, count
        )
    return _emit_piece(st, begin, play, capture, opp0, opp1, empty0, empty1, buf, count)


@njit(cache=True)
def gen_moves_into(st, play, buf, captures_only):
    """生成伪合法着法写入定长缓冲，返回着法数。

    顺序复刻 Java：阶段 A 全部吃子、阶段 B 全部非吃子；每阶段内按
    PIECE_STARTS[play]+1..+15 后接将/帅，目标按 MSB(play) 顺序。
    """
    opp0 = st.mask_personal[1 - play, 0]
    opp1 = st.mask_personal[1 - play, 1]
    empty0 = np.int64(0)
    empty1 = np.int64(0)
    if not captures_only:
        empty0, empty1 = bitboard.complement(st.mask_all[0], st.mask_all[1])
    count = _gen_stage(st, play, True, opp0, opp1, empty0, empty1, buf, 0)
    if not captures_only:
        count = _gen_stage(st, play, False, opp0, opp1, empty0, empty1, buf, count)
    return count


@njit(cache=True)
def gen_moves(st, play):
    """返回 (int32[MAX_MOVES] 缓冲, 伪合法着法数)。"""
    buf = np.empty(MAX_MOVES, dtype=np.int32)
    return buf, gen_moves_into(st, play, buf, False)


@njit(cache=True)
def gen_captures(st, play):
    """只生成吃子着法（阶段 A），返回 (缓冲, 着法数)；供静态搜索使用。"""
    buf = np.empty(MAX_MOVES, dtype=np.int32)
    return buf, gen_moves_into(st, play, buf, True)


@njit(cache=True)
def gen_captures_into(st, play, buf):
    """只生成吃子着法并写入调用方缓冲，返回着法数。"""
    return gen_moves_into(st, play, buf, True)


@njit(cache=True)
def in_check(st, play):
    """play 方是否被将军（对应 Java `checked` L312-370）。

    检测顺序与 Java 一致：车 → 飞将 → 炮 → 马（逐匹验腿）→ 兵。
    """
    opp = 1 - play
    king_site = st.all_chess[_PIECE_STARTS[play]]
    if king_site < 0:
        return True
    opp_king_site = st.all_chess[_PIECE_STARTS[opp]]
    if opp_king_site < 0:
        return False

    row = king_site // 9
    col = king_site % 9
    rm = st.bit_row[row]
    cm = st.bit_col[col]

    # 对方车
    lo = tables.CHARIOT_ATTACK_ROW_LO[king_site, rm] ^ tables.CHARIOT_ATTACK_COL_LO[king_site, cm]
    hi = tables.CHARIOT_ATTACK_ROW_HI[king_site, rm] ^ tables.CHARIOT_ATTACK_COL_HI[king_site, cm]
    role = C.CHARIOT + 7 * (1 - opp)
    if ((lo & st.mask_role[role, 0]) | (hi & st.mask_role[role, 1])) != 0:
        return True

    # 飞将：对方将与己方将同列且中间无子
    if bitboard.has_site(
        tables.CHARIOT_ATTACK_COL_LO[king_site, cm],
        tables.CHARIOT_ATTACK_COL_HI[king_site, cm],
        opp_king_site,
    ):
        return True

    # 对方炮
    lo = tables.GUN_ATTACK_ROW_LO[king_site, rm] ^ tables.GUN_ATTACK_COL_LO[king_site, cm]
    hi = tables.GUN_ATTACK_ROW_HI[king_site, rm] ^ tables.GUN_ATTACK_COL_HI[king_site, cm]
    role = C.GUN + 7 * (1 - opp)
    if ((lo & st.mask_role[role, 0]) | (hi & st.mask_role[role, 1])) != 0:
        return True

    # 对方马：先用将的马目标表筛出候选马（马的攻击位对称），再逐匹验腿。
    role = C.KNIGHT + 7 * (1 - opp)
    cand_lo = tables.KNIGHT_TARGET_LO[king_site] & st.mask_role[role, 0]
    cand_hi = tables.KNIGHT_TARGET_HI[king_site] & st.mask_role[role, 1]
    while (cand_lo | cand_hi) != 0:
        cand_lo, cand_hi, knight_site = bitboard.pop_lowest(cand_lo, cand_hi)
        key = bitboard.check_sum_knight(
            tables.KNIGHT_LEG_LO[knight_site] & st.mask_all[0],
            tables.KNIGHT_LEG_HI[knight_site] & st.mask_all[1],
        )
        if bitboard.has_site(
            tables.KNIGHT_ATTACK_LIMIT_LO[knight_site, key],
            tables.KNIGHT_ATTACK_LIMIT_HI[knight_site, key],
            king_site,
        ):
            return True

    # 对方兵
    role = C.SOLDIER + 7 * (1 - opp)
    lo = tables.KING_CHECKED_SOLDIER_LO[king_site] & st.mask_role[role, 0]
    hi = tables.KING_CHECKED_SOLDIER_HI[king_site] & st.mask_role[role, 1]
    return (lo | hi) != 0


def kings_facing(st):
    """将帅同列且中间无子（测试与调试用；in_check 已覆盖飞将）。"""
    red = int(st.all_chess[C.RED_PIECES_START])
    black = int(st.all_chess[C.BLACK_PIECES_START])
    if red < 0 or black < 0 or red % 9 != black % 9:
        return False
    lo, hi = tables.chariot_attack_col(red, int(st.bit_col[red % 9]))
    return bitboard.has_site(lo, hi, black)


@njit(cache=True)
def opp_attack_site(st, play):
    """对方（1-play）全体棋子的攻击位并集，返回 (lo, hi)。

    对应 Java `getOppAttackSite/chessAttackSite`：车 = 吃子位 ∪ 平移位，
    炮 = 吃子位 ∪ 压制位，其余棋子为各自的攻击表。
    """
    opp = 1 - play
    begin = _PIECE_STARTS[opp]
    lo = np.int64(0)
    hi = np.int64(0)
    for offset in range(16):
        piece = begin + offset
        src = st.all_chess[piece]
        if src < 0:
            continue
        role = C.PIECE_ROLES[piece]
        row = src // 9
        col = src % 9
        if role == C.RED_CHARIOT or role == C.BLACK_CHARIOT:
            rm = st.bit_row[row]
            cm = st.bit_col[col]
            lo |= tables.CHARIOT_ATTACK_ROW_LO[src, rm] ^ tables.CHARIOT_ATTACK_COL_LO[src, cm]
            hi |= tables.CHARIOT_ATTACK_ROW_HI[src, rm] ^ tables.CHARIOT_ATTACK_COL_HI[src, cm]
            lo |= tables.MOVE_CHARIOT_GUN_ROW_LO[src, rm] ^ tables.MOVE_CHARIOT_GUN_COL_LO[src, cm]
            hi |= tables.MOVE_CHARIOT_GUN_ROW_HI[src, rm] ^ tables.MOVE_CHARIOT_GUN_COL_HI[src, cm]
        elif role == C.RED_GUN or role == C.BLACK_GUN:
            rm = st.bit_row[row]
            cm = st.bit_col[col]
            lo |= tables.GUN_ATTACK_ROW_LO[src, rm] ^ tables.GUN_ATTACK_COL_LO[src, cm]
            hi |= tables.GUN_ATTACK_ROW_HI[src, rm] ^ tables.GUN_ATTACK_COL_HI[src, cm]
            lo |= tables.GUN_FAKE_ATTACK_ROW_LO[src, rm] ^ tables.GUN_FAKE_ATTACK_COL_LO[src, cm]
            hi |= tables.GUN_FAKE_ATTACK_ROW_HI[src, rm] ^ tables.GUN_FAKE_ATTACK_COL_HI[src, cm]
        elif role == C.RED_KNIGHT or role == C.BLACK_KNIGHT:
            key = bitboard.check_sum_knight(
                tables.KNIGHT_LEG_LO[src] & st.mask_all[0],
                tables.KNIGHT_LEG_HI[src] & st.mask_all[1],
            )
            lo |= tables.KNIGHT_ATTACK_LIMIT_LO[src, key]
            hi |= tables.KNIGHT_ATTACK_LIMIT_HI[src, key]
        elif role == C.RED_ELEPHANT or role == C.BLACK_ELEPHANT:
            key = bitboard.check_sum_elephant(
                tables.ELEPHANT_LEG_LO[src] & st.mask_all[0],
                tables.ELEPHANT_LEG_HI[src] & st.mask_all[1],
            )
            lo |= tables.ELEPHANT_ATTACK_LIMIT_LO[src, key]
            hi |= tables.ELEPHANT_ATTACK_LIMIT_HI[src, key]
        elif role == C.RED_KING or role == C.BLACK_KING:
            lo |= tables.KING_TARGET_LO[src]
            hi |= tables.KING_TARGET_HI[src]
        elif role == C.RED_GUARD or role == C.BLACK_GUARD:
            lo |= tables.GUARD_TARGET_LO[src]
            hi |= tables.GUARD_TARGET_HI[src]
        else:
            lo |= tables.SOLDIER_TARGET_LO[opp, src]
            hi |= tables.SOLDIER_TARGET_HI[opp, src]
    return lo, hi


@njit(cache=True)
def legal_move(st, play, m):
    """TT/killer 着法快速校验（对应 Java `legalMove` L226-302）。

    检查源子属于走子方、目标不是己方子，且目标在该子的合法目标表内。
    """
    src = C.move_src(m)
    dest = C.move_dest(m)
    if src < 0 or src >= 90 or dest < 0 or dest >= 90 or src == dest:
        return False
    src_chess = st.board[src]
    if src_chess == 0 or (_PIECE_STARTS[play] & src_chess) == 0:
        return False
    dest_chess = st.board[dest]
    if dest_chess != 0 and (_PIECE_STARTS[play] & dest_chess) != 0:
        return False
    role = C.PIECE_ROLES[src_chess]
    lo, hi = _target_mask(st, role, src, dest_chess != 0, play)
    return bitboard.has_site(lo, hi, dest)


@njit(cache=True)
def gen_legal_moves_into(st, play, buf):
    """生成全部合法着法写入 buf（原地压缩），返回数量。

    对每个伪合法着法 make → `in_check(play)` → unmake，过滤自将与飞将。
    """
    n = gen_moves_into(st, play, buf, False)
    out = 0
    for i in range(n):
        m = buf[i]
        undo = _position.make_move(st, m)
        ok = not in_check(st, play)
        _position.unmake_move(st, m, undo)
        if ok:
            buf[out] = m
            out += 1
    return out


@njit(cache=True)
def gen_legal_moves(st, play):
    """返回合法着法的 int32 数组（长度 = 着法数）。"""
    buf = np.empty(MAX_MOVES, dtype=np.int32)
    n = gen_legal_moves_into(st, play, buf)
    return buf[:n].copy()
