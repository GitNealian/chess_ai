"""中局评估（Task 7）。

Java 参考：
- `EvaluateCompute.java`：位置/分区表、`chessAllMove`、`chessMobility`、
  炮检测（`exposedCannon`/`bottomCannon`/`restChariot`）、攻防掩码；
- `EvaluateComputeMiddleGame.java` L35-218：主评估；
- `SearchEngine.java` L123-125：`roughEvaluate`。

约定与差异：
- 掩码一律用 (lo, hi) 打包；`msb` 复刻 Java `BitBoard.MSB(play)` 的四字
  扫描顺序（红方 0..89 升序；黑方 81..89、54..80、27..53、0..26）；
- Java 用静态分区评分表就地改写，Python 改为每次评估由
  `dynamic_partition_score` 局部重建，避免全局可变状态；
- 主评估 `evaluate` 只实现中局；残局（Task 8）暂未接入。
"""

import numpy as np
from numba import njit

from . import bitboard, tables
from . import constants as C
from . import eval_tables as T

# attach_score 定义在 position.py（njit，base_score 增量与全量共用），此处再导出。
from .position import attach_score

__all__ = [
    "attach_score",
    "bottom_cannon",
    "chess_all_move",
    "chess_mobility",
    "comp_partition_score",
    "dynamic_partition_score",
    "evaluate",
    "exposed_cannon",
    "msb",
    "rest_chariot",
    "rough_evaluate",
    "trim_partition_score",
]

_LO27 = 0x7FFFFFF
_HI9 = 0x1FF


@njit(cache=True)
def msb(lo, hi, play):
    """Java `BitBoard.MSB(play)`：取掩码中该方枚举顺序的第一个 site。

    红方：Low(0..26) → Mid1(27..53) → Mid2(54..80) → Hi(81..89)；
    黑方：Hi → Mid2 → Mid1 → Low。空掩码返回 -1。
    """
    if play == C.RED:
        low = lo & _LO27
        if low != 0:
            return bitboard._ctz64(low)
        mid1 = (lo >> 27) & _LO27
        if mid1 != 0:
            return 27 + bitboard._ctz64(mid1)
        mid2 = ((lo >> 54) & 0x3FF) | ((hi & 0x1FFFF) << 10)
        if mid2 != 0:
            return 54 + bitboard._ctz64(mid2)
        him = (hi >> 17) & _HI9
        if him != 0:
            return 81 + bitboard._ctz64(him)
        return -1
    him = (hi >> 17) & _HI9
    if him != 0:
        return 81 + bitboard._ctz64(him)
    mid2 = ((lo >> 54) & 0x3FF) | ((hi & 0x1FFFF) << 10)
    if mid2 != 0:
        return 54 + bitboard._ctz64(mid2)
    mid1 = (lo >> 27) & _LO27
    if mid1 != 0:
        return 27 + bitboard._ctz64(mid1)
    low = lo & _LO27
    if low != 0:
        return bitboard._ctz64(low)
    return -1


@njit(cache=True)
def _knight_attack(st, site):
    """马在 site 的受腿位限制攻击位（含己方/对方棋子，对应 Java 攻击限制表）。"""
    key = bitboard.check_sum_knight(
        tables.KNIGHT_LEG_LO[site] & st.mask_all[0],
        tables.KNIGHT_LEG_HI[site] & st.mask_all[1],
    )
    return (
        tables.KNIGHT_ATTACK_LIMIT_LO[site, key],
        tables.KNIGHT_ATTACK_LIMIT_HI[site, key],
    )


@njit(cache=True)
def _elephant_attack(st, site):
    """象在 site 的受象眼限制攻击位。"""
    key = bitboard.check_sum_elephant(
        tables.ELEPHANT_LEG_LO[site] & st.mask_all[0],
        tables.ELEPHANT_LEG_HI[site] & st.mask_all[1],
    )
    return (
        tables.ELEPHANT_ATTACK_LIMIT_LO[site, key],
        tables.ELEPHANT_ATTACK_LIMIT_HI[site, key],
    )


@njit(cache=True)
def chess_all_move(st, role, site, play):
    """该子的控制范围（对应 Java `EvaluateCompute.chessAllMove`）。

    车的吃子位与平移位取 XOR（两表不相交）；炮的吃子位与压制位同理；
    马/象取腿位限制攻击表；将/士/兵取目标表。返回 (lo, hi)。
    """
    if role == C.RED_CHARIOT or role == C.BLACK_CHARIOT:
        rm = st.bit_row[site // 9]
        cm = st.bit_col[site % 9]
        alo = (
            tables.CHARIOT_ATTACK_ROW_LO[site, rm]
            ^ tables.CHARIOT_ATTACK_COL_LO[site, cm]
        )
        ahi = (
            tables.CHARIOT_ATTACK_ROW_HI[site, rm]
            ^ tables.CHARIOT_ATTACK_COL_HI[site, cm]
        )
        mlo = (
            tables.MOVE_CHARIOT_GUN_ROW_LO[site, rm]
            ^ tables.MOVE_CHARIOT_GUN_COL_LO[site, cm]
        )
        mhi = (
            tables.MOVE_CHARIOT_GUN_ROW_HI[site, rm]
            ^ tables.MOVE_CHARIOT_GUN_COL_HI[site, cm]
        )
        return alo ^ mlo, ahi ^ mhi
    if role == C.RED_KNIGHT or role == C.BLACK_KNIGHT:
        return _knight_attack(st, site)
    if role == C.RED_GUN or role == C.BLACK_GUN:
        rm = st.bit_row[site // 9]
        cm = st.bit_col[site % 9]
        alo = tables.GUN_ATTACK_ROW_LO[site, rm] ^ tables.GUN_ATTACK_COL_LO[site, cm]
        ahi = tables.GUN_ATTACK_ROW_HI[site, rm] ^ tables.GUN_ATTACK_COL_HI[site, cm]
        flo = (
            tables.GUN_FAKE_ATTACK_ROW_LO[site, rm]
            ^ tables.GUN_FAKE_ATTACK_COL_LO[site, cm]
        )
        fhi = (
            tables.GUN_FAKE_ATTACK_ROW_HI[site, rm]
            ^ tables.GUN_FAKE_ATTACK_COL_HI[site, cm]
        )
        return alo ^ flo, ahi ^ fhi
    if role == C.RED_ELEPHANT or role == C.BLACK_ELEPHANT:
        return _elephant_attack(st, site)
    if role == C.RED_KING or role == C.BLACK_KING:
        return tables.KING_TARGET_LO[site], tables.KING_TARGET_HI[site]
    if role == C.RED_GUARD or role == C.BLACK_GUARD:
        return tables.GUARD_TARGET_LO[site], tables.GUARD_TARGET_HI[site]
    return tables.SOLDIER_TARGET_LO[play, site], tables.SOLDIER_TARGET_HI[play, site]


@njit(cache=True)
def chess_mobility(st, role, site, own_lo, own_hi):
    """机动性（对应 Java `EvaluateCompute.chessMobility`）。

    车/炮取行/列平移表 popcount 之和；马为受腿位限制攻击位中非己方子的数量；
    将为九宫内未被占据的邻格数；其余棋子 Java 未定义（返回 0）。
    """
    if (
        role == C.RED_CHARIOT
        or role == C.BLACK_CHARIOT
        or role == C.RED_GUN
        or role == C.BLACK_GUN
    ):
        rm = st.bit_row[site // 9]
        cm = st.bit_col[site % 9]
        return np.int32(
            tables.CHARIOT_GUN_MOBILITY_ROW[site, rm]
            + tables.CHARIOT_GUN_MOBILITY_COL[site, cm]
        )
    if role == C.RED_KNIGHT or role == C.BLACK_KNIGHT:
        alo, ahi = _knight_attack(st, site)
        return np.int32(
            bitboard.count(alo, ahi) - bitboard.count(alo & own_lo, ahi & own_hi)
        )
    if role == C.RED_KING or role == C.BLACK_KING:
        klo = tables.KING_TARGET_LO[site]
        khi = tables.KING_TARGET_HI[site]
        # Java：kingMove = K ∩ 全体棋子；再 K XOR kingMove，即九宫内的空格数
        return np.int32(
            bitboard.count(klo ^ (klo & st.mask_all[0]), khi ^ (khi & st.mask_all[1]))
        )
    return np.int32(0)


@njit(cache=True)
def dynamic_partition_score(st):
    """按士象数量动态调整分区评分表（对应 Java `dynamicCMPChessPartitionScore`）。

    返回 (attack[48], defense[48]) 两个新数组；基础值与 Java 静态数组一致，
    每次评估重建，避免 Java 就地改写静态表的共享状态。
    """
    attack = np.copy(T.ATTACK_PARTITION_SCORE)
    defense = np.copy(T.DEFENSE_PARTITION_SCORE)
    red_guard = st.remain[C.RED_GUARD]
    red_elephant = st.remain[C.RED_ELEPHANT]
    black_guard = st.remain[C.BLACK_GUARD]
    black_elephant = st.remain[C.BLACK_ELEPHANT]

    defense[23] = T.GUARD_ELEPHANT_NUM_SCORE[black_elephant]
    defense[24] = T.GUARD_ELEPHANT_NUM_SCORE[black_elephant]
    defense[25] = T.GUARD_ELEPHANT_NUM_SCORE[black_guard]
    defense[26] = T.GUARD_ELEPHANT_NUM_SCORE[black_guard]
    defense[39] = T.GUARD_ELEPHANT_NUM_SCORE[red_elephant]
    defense[40] = T.GUARD_ELEPHANT_NUM_SCORE[red_elephant]
    defense[41] = T.GUARD_ELEPHANT_NUM_SCORE[red_guard]
    defense[42] = T.GUARD_ELEPHANT_NUM_SCORE[red_guard]

    attack[19] = T.KNIGHT_NUM_SCORE_DEPEND_GUARD[red_guard]
    attack[20] = T.KNIGHT_NUM_SCORE_DEPEND_GUARD[red_guard]
    attack[21] = T.GUN_NUM_SCORE_DEPEND_GUARD[red_guard]
    attack[22] = T.GUN_NUM_SCORE_DEPEND_GUARD[red_guard]
    attack[35] = T.KNIGHT_NUM_SCORE_DEPEND_GUARD[black_guard]
    attack[36] = T.KNIGHT_NUM_SCORE_DEPEND_GUARD[black_guard]
    attack[37] = T.GUN_NUM_SCORE_DEPEND_GUARD[black_guard]
    attack[38] = T.GUN_NUM_SCORE_DEPEND_GUARD[black_guard]
    return attack, defense


@njit(cache=True)
def comp_partition_score(play, site, chess, partition, attack_tab, defense_tab):
    """按棋子的分区代号累加分区评分（对应 Java `compPartitionScore`）。

    红方 attack 分区 = 1/2/3（左/右/中）、defense = 4/5/6；
    黑方相反；31/32/33 与 64/65/66 是跨两/三路的展开代号。
    """
    par = T.ROLE_PARTITION_SITE[C.PIECE_ROLES[chess], site]
    if play == C.RED:
        if par == 1:
            partition[1] += attack_tab[chess]
        elif par == 2:
            partition[2] += attack_tab[chess]
        elif par == 3:
            partition[3] += attack_tab[chess]
        elif par == 31:
            partition[3] += attack_tab[chess]
            partition[1] += attack_tab[chess]
        elif par == 32:
            partition[3] += attack_tab[chess]
            partition[2] += attack_tab[chess]
        elif par == 33:
            partition[3] += attack_tab[chess]
            partition[2] += attack_tab[chess]
            partition[1] += attack_tab[chess]
        elif par == 4:
            partition[4] += defense_tab[chess]
        elif par == 5:
            partition[5] += defense_tab[chess]
        elif par == 6:
            partition[6] += defense_tab[chess]
        elif par == 64:
            partition[6] += defense_tab[chess]
            partition[4] += defense_tab[chess]
        elif par == 65:
            partition[6] += defense_tab[chess]
            partition[5] += defense_tab[chess]
        elif par == 66:
            partition[6] += defense_tab[chess]
            partition[5] += defense_tab[chess]
            partition[4] += defense_tab[chess]
    else:
        if par == 1:
            partition[1] += defense_tab[chess]
        elif par == 2:
            partition[2] += defense_tab[chess]
        elif par == 3:
            partition[3] += defense_tab[chess]
        elif par == 31:
            partition[3] += defense_tab[chess]
            partition[1] += defense_tab[chess]
        elif par == 32:
            partition[3] += defense_tab[chess]
            partition[2] += defense_tab[chess]
        elif par == 33:
            partition[3] += defense_tab[chess]
            partition[2] += defense_tab[chess]
            partition[1] += defense_tab[chess]
        elif par == 4:
            partition[4] += attack_tab[chess]
        elif par == 5:
            partition[5] += attack_tab[chess]
        elif par == 6:
            partition[6] += attack_tab[chess]
        elif par == 64:
            partition[6] += attack_tab[chess]
            partition[4] += attack_tab[chess]
        elif par == 65:
            partition[6] += attack_tab[chess]
            partition[5] += attack_tab[chess]
        elif par == 66:
            partition[6] += attack_tab[chess]
            partition[5] += attack_tab[chess]
            partition[4] += attack_tab[chess]


@njit(cache=True)
def trim_partition_score(partition_score, attack_partition, defense_partition):
    """分区评分拆成三路攻防（对应 Java `trimPartitionScore`）。

    红方 attack=[1,2,3]、defense=[4,5,6]；黑方 attack=[4,5,6]、defense=[1,2,3]；
    每路顺序为 LEFTSITE=0、RIGHTSITE=1、MIDSITE=2。
    """
    attack_partition[C.RED, 0] = partition_score[C.RED, 1]
    attack_partition[C.RED, 1] = partition_score[C.RED, 2]
    attack_partition[C.RED, 2] = partition_score[C.RED, 3]
    defense_partition[C.RED, 0] = partition_score[C.RED, 4]
    defense_partition[C.RED, 1] = partition_score[C.RED, 5]
    defense_partition[C.RED, 2] = partition_score[C.RED, 6]
    attack_partition[C.BLACK, 0] = partition_score[C.BLACK, 4]
    attack_partition[C.BLACK, 1] = partition_score[C.BLACK, 5]
    attack_partition[C.BLACK, 2] = partition_score[C.BLACK, 6]
    defense_partition[C.BLACK, 0] = partition_score[C.BLACK, 1]
    defense_partition[C.BLACK, 1] = partition_score[C.BLACK, 2]
    defense_partition[C.BLACK, 2] = partition_score[C.BLACK, 3]


@njit(cache=True)
def exposed_cannon(st, play, opp_king_site, row, col):
    """空头炮：对方将所在行列的第一个阻挡位置是己方炮（对应 `exposedCannon`）。

    row/col 是对方将位置的 `boardBitRow/boardBitCol` 掩码（与 Java 参数一致）。
    返回该炮 site，找不到返回 -1。
    """
    lo = (
        tables.CHARIOT_ATTACK_ROW_LO[opp_king_site, row]
        ^ tables.CHARIOT_ATTACK_COL_LO[opp_king_site, col]
    )
    hi = (
        tables.CHARIOT_ATTACK_ROW_HI[opp_king_site, row]
        ^ tables.CHARIOT_ATTACK_COL_HI[opp_king_site, col]
    )
    role = C.GUN + 7 * (1 - play)
    lo &= st.mask_role[role, 0]
    hi &= st.mask_role[role, 1]
    if (lo | hi) == 0:
        return -1
    return msb(lo, hi, play)


@njit(cache=True)
def bottom_cannon(st, play, opp_king_site, row, col):
    """沉底炮：对方将所在行列的第三个阻挡位置是己方炮（隔两子攻击表）。"""
    lo = (
        tables.GUN_MORE_REST_ATTACK_ROW_LO[opp_king_site, row]
        ^ tables.GUN_MORE_REST_ATTACK_COL_LO[opp_king_site, col]
    )
    hi = (
        tables.GUN_MORE_REST_ATTACK_ROW_HI[opp_king_site, row]
        ^ tables.GUN_MORE_REST_ATTACK_COL_HI[opp_king_site, col]
    )
    role = C.GUN + 7 * (1 - play)
    lo &= st.mask_role[role, 0]
    hi &= st.mask_role[role, 1]
    if (lo | hi) == 0:
        return -1
    return msb(lo, hi, play)


@njit(cache=True)
def rest_chariot(st, play, opp_king_site, row, col):
    """残车：对方将所在行列的第二个阻挡位置是己方车（炮攻击表语义）。"""
    lo = (
        tables.GUN_ATTACK_ROW_LO[opp_king_site, row]
        ^ tables.GUN_ATTACK_COL_LO[opp_king_site, col]
    )
    hi = (
        tables.GUN_ATTACK_ROW_HI[opp_king_site, row]
        ^ tables.GUN_ATTACK_COL_HI[opp_king_site, col]
    )
    role = C.CHARIOT + 7 * (1 - play)
    lo &= st.mask_role[role, 0]
    hi &= st.mask_role[role, 1]
    if (lo | hi) == 0:
        return -1
    return msb(lo, hi, play)


@njit(cache=True)
def evaluate(st, play, endgame=False):
    """中局评估，返回 play 视角分数（对应 `EvaluateComputeMiddleGame.evaluate`）。"""
    if endgame:
        raise NotImplementedError("endgame evaluation is Task 8")
    score = np.empty(2, dtype=np.int32)
    score[C.RED] = st.base_score[C.RED]
    score[C.BLACK] = st.base_score[C.BLACK]

    attack_tab, defense_tab = dynamic_partition_score(st)
    partition = np.zeros((2, 7), dtype=np.int32)
    move_lo = np.zeros(2, dtype=np.int64)
    move_hi = np.zeros(2, dtype=np.int64)
    king_unmove = np.zeros(2, dtype=np.bool_)

    for chess in range(16, 48):
        site = st.all_chess[chess]
        if site < 0:
            continue
        if chess < 32:
            currplay = C.BLACK
        else:
            currplay = C.RED
        role = C.PIECE_ROLES[chess]
        alo, ahi = chess_all_move(st, role, site, currplay)
        comp_partition_score(
            currplay, site, chess, partition[currplay], attack_tab, defense_tab
        )
        move_lo[currplay] |= alo
        move_hi[currplay] |= ahi
        if T.MIN_MOBILITY[chess] > 0:
            mobility = chess_mobility(
                st,
                role,
                site,
                st.mask_personal[currplay, 0],
                st.mask_personal[currplay, 1],
            )
            if mobility < T.MIN_MOBILITY[chess]:
                score[currplay] -= (
                    T.MIN_MOBILITY[chess] - mobility
                ) * T.MOBILITY_REWARDS[chess]
                if role == C.RED_KING:
                    king_unmove[C.RED] = True
                elif role == C.BLACK_KING:
                    king_unmove[C.BLACK] = True

    attack_partition = np.zeros((2, 3), dtype=np.int32)
    defense_partition = np.zeros((2, 3), dtype=np.int32)
    trim_partition_score(partition, attack_partition, defense_partition)

    for i in range(2):
        opp = 1 - i
        main_lo = (
            st.mask_role[C.CHARIOT + 7 * (1 - i), 0]
            | st.mask_role[C.KNIGHT + 7 * (1 - i), 0]
            | st.mask_role[C.GUN + 7 * (1 - i), 0]
        )
        main_hi = (
            st.mask_role[C.CHARIOT + 7 * (1 - i), 1]
            | st.mask_role[C.KNIGHT + 7 * (1 - i), 1]
            | st.mask_role[C.GUN + 7 * (1 - i), 1]
        )
        def_lo = (
            st.mask_role[C.ELEPHANT + 7 * (1 - i), 0]
            | st.mask_role[C.GUARD + 7 * (1 - i), 0]
            | st.mask_role[C.SOLDIER + 7 * (1 - i), 0]
        )
        def_hi = (
            st.mask_role[C.ELEPHANT + 7 * (1 - i), 1]
            | st.mask_role[C.GUARD + 7 * (1 - i), 1]
            | st.mask_role[C.SOLDIER + 7 * (1 - i), 1]
        )
        opp_main_lo = (
            st.mask_role[C.CHARIOT + 7 * i, 0]
            | st.mask_role[C.KNIGHT + 7 * i, 0]
            | st.mask_role[C.GUN + 7 * i, 0]
        )
        opp_main_hi = (
            st.mask_role[C.CHARIOT + 7 * i, 1]
            | st.mask_role[C.KNIGHT + 7 * i, 1]
            | st.mask_role[C.GUN + 7 * i, 1]
        )
        opp_def_lo = (
            st.mask_role[C.ELEPHANT + 7 * i, 0]
            | st.mask_role[C.GUARD + 7 * i, 0]
            | st.mask_role[C.SOLDIER + 7 * i, 0]
        )
        opp_def_hi = (
            st.mask_role[C.ELEPHANT + 7 * i, 1]
            | st.mask_role[C.GUARD + 7 * i, 1]
            | st.mask_role[C.SOLDIER + 7 * i, 1]
        )
        # 控制位加成：己方主攻子位 ×10、己方防御子位 ×6、对方主攻子位 ×18、对方防御子位 ×9
        score[i] += bitboard.count(move_lo[i] & main_lo, move_hi[i] & main_hi) * 10
        score[i] += bitboard.count(move_lo[i] & def_lo, move_hi[i] & def_hi) * 6
        score[i] += (
            bitboard.count(move_lo[i] & opp_main_lo, move_hi[i] & opp_main_hi) * 18
        )
        score[i] += bitboard.count(move_lo[i] & opp_def_lo, move_hi[i] & opp_def_hi) * 9

        gun_num = st.remain[C.GUN + 7 * (1 - i)]
        opp_king_site = st.all_chess[16 + 16 * opp]
        row = st.bit_row[opp_king_site // 9]
        col = st.bit_col[opp_king_site % 9]
        weakness = False
        opp_all_num = st.attack_def[opp, 0] + st.attack_def[opp, 1] - 1
        if gun_num > 0:
            gun_site = exposed_cannon(st, i, opp_king_site, row, col)
            if opp_all_num > 5 and gun_site != -1:
                extend = (opp_king_site // 9 - gun_site // 9) + (
                    opp_king_site % 9 - gun_site % 9
                )
                if extend < 0:
                    extend = -extend
                score[i] += extend * 45
                weakness = True
            gun_site = bottom_cannon(st, i, opp_king_site, row, col)
            if gun_site != -1:
                extend = (opp_king_site // 9 - gun_site // 9) + (
                    opp_king_site % 9 - gun_site % 9
                )
                if extend < 0:
                    extend = -extend
                if extend <= 3:
                    score[i] += 100
                    weakness = True
        if rest_chariot(st, i, opp_king_site, row, col) != 1:
            score[i] += 30

        if weakness:
            defense_partition[opp, 0] -= 1
            defense_partition[opp, 1] -= 1
            defense_partition[opp, 2] -= 1
        if king_unmove[opp]:
            v = 1
            if weakness:
                v = 2
            defense_partition[opp, 0] -= v
            defense_partition[opp, 1] -= v
            defense_partition[opp, 2] -= v

        king_col = opp_king_site % 9
        if king_col == 3:
            defense_partition[opp, 0] -= 1
        elif king_col == 5:
            defense_partition[opp, 1] -= 1
        elif king_col == 4:
            king_row = opp_king_site // 9
            if king_row == 1 or king_row == 2 or king_row == 8 or king_row == 7:
                defense_partition[opp, 2] -= 1

        for side in range(3):
            if attack_partition[i, side] > defense_partition[opp, side]:
                score[i] += (
                    attack_partition[i, side] - defense_partition[opp, side]
                ) * 30

        chariot_num = st.remain[C.CHARIOT + 7 * (1 - i)]
        knight_num = st.remain[C.KNIGHT + 7 * (1 - i)]
        opp_elephant_num = st.remain[C.ELEPHANT + 7 * i]
        opp_guard_num = st.remain[C.GUARD + 7 * i]
        # Java 为嵌套 if：缺象且士全且有炮 / 缺士且有马
        if opp_elephant_num < 2 and opp_guard_num >= 2 and gun_num > 0:
            score[i] += 60
        if opp_guard_num < 2 and knight_num > 0:
            score[i] += 60
        if chariot_num > 0:
            score[i] += 100
        if knight_num > 0:
            score[i] += 100
        if gun_num > 0:
            score[i] += 100

    return score[play] - score[1 - play]


@njit(cache=True)
def rough_evaluate(st, play):
    """粗评估（对应 Java `SearchEngine.roughEvaluate`）：base_score 之差。"""
    return st.base_score[play] - st.base_score[1 - play]
