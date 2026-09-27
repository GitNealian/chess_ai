# cython: language_level=3, boundscheck=False, wraparound=False, cdivision=True, initializedcheck=False, nonecheck=False
"""Cython 核心 MVP 探针：BoardState + make/unmake。

阶段 1 验收：make+unmake <= 0.06µs（当前 numba 0.13µs，Java 0.027µs）。
表由 Python 侧经 init_tables 注入（只读 memoryview）。
"""
import numpy as np
cimport numpy as cnp
from libc.stdint cimport int64_t, int32_t, int8_t, int16_t
from libc.stdlib cimport calloc, free
from libc.stdio cimport fprintf, stderr

cnp.import_array()

cdef long long _M1 = 0x5555555555555555
cdef long long _M2 = 0x3333333333333333
cdef long long _M4 = 0x0F0F0F0F0F0F0F0F
cdef long long _M8 = 0x0101010101010101

# ---- 只读表（Python 注入）----
cdef const int64_t[:, ::1] _Z64
cdef const int64_t[:, ::1] _Z32
cdef const int32_t[:, ::1] _MID_RED
cdef const int32_t[:, ::1] _MID_BLK
cdef const int32_t[:, ::1] _END_RED
cdef const int32_t[:, ::1] _END_BLK
cdef const int8_t[:] _PIECE_ROLES
cdef const int8_t[:] _AD_INDEX
cdef long long* _MASK_LO = NULL
cdef long long* _MASK_HI = NULL
cdef object _keep_alive = None

# ---- 评估所需表（Python 侧 init_eval_tables 注入）----
cdef const int64_t[:, ::1] _CH_ATK_R_LO, _CH_ATK_R_HI, _CH_ATK_C_LO, _CH_ATK_C_HI
cdef const int64_t[:, ::1] _MV_R_LO, _MV_R_HI, _MV_C_LO, _MV_C_HI
cdef const int64_t[:, ::1] _GUN_ATK_R_LO, _GUN_ATK_R_HI, _GUN_ATK_C_LO, _GUN_ATK_C_HI
cdef const int64_t[:, ::1] _GUN_FK_R_LO, _GUN_FK_R_HI, _GUN_FK_C_LO, _GUN_FK_C_HI
cdef const int64_t[:, ::1] _GUN_MR_R_LO, _GUN_MR_R_HI, _GUN_MR_C_LO, _GUN_MR_C_HI
cdef const int64_t[:] _KN_LEG_LO, _KN_LEG_HI
cdef const int64_t[:, ::1] _KN_ATK_LO, _KN_ATK_HI
cdef const int64_t[:] _EL_LEG_LO, _EL_LEG_HI
cdef const int64_t[:, ::1] _EL_ATK_LO, _EL_ATK_HI
cdef const int64_t[:] _KING_LO, _KING_HI, _GUARD_LO, _GUARD_HI
cdef const int64_t[:, ::1] _SOL_LO, _SOL_HI
cdef const int64_t[:] _KCS_LO, _KCS_HI
cdef const int64_t[:] _KN_TGT_LO, _KN_TGT_HI
cdef const int8_t[:] _PIECE_KINDS
cdef const int64_t[:] _DANGER_LO, _DANGER_HI
cdef const int16_t[:, ::1] _CG_MOB_R, _CG_MOB_C
cdef const int32_t[:] _ATK_PART, _DEF_PART, _MIN_MOB, _MOB_REW, _SOL_PROT, _GUN_NG, _KN_NG
cdef const int32_t[:] _GE_NUM, _GUN_DEP, _KN_DEP
cdef const int8_t[:, ::1] _ROLE_PART


cdef inline int _popcount64(long long x) noexcept nogil:
    x = x - ((x >> 1) & _M1)
    x = (x & _M2) + ((x >> 2) & _M2)
    x = (x + (x >> 4)) & _M4
    return <int>((x * _M8) >> 56)


cdef inline int _ctz64(long long x) noexcept nogil:
    return _popcount64((x & -x) - 1)


cdef inline int _csum_knight(long long lo, long long hi) noexcept nogil:
    cdef long long t = ((lo & 0x7FFFFFF) ^ ((lo >> 27) & 0x7FFFFFF)
                        ^ (((lo >> 54) & 0x3FF) | ((hi & 0x1FFFF) << 10))
                        ^ ((hi >> 17) & 0x1FF))
    return <int>((t & 0x7F) + ((t >> 7) & 0x7F) + ((t >> 14) & 0x7F) + ((t >> 21) & 0x7F))


cdef inline int _csum_elephant(long long lo, long long hi) noexcept nogil:
    cdef long long t = ((lo & 0x7FFFFFF) ^ ((lo >> 27) & 0x7FFFFFF)
                        ^ (((lo >> 54) & 0x3FF) | ((hi & 0x1FFFF) << 10))
                        ^ ((hi >> 17) & 0x1FF))
    return <int>((t & 0x7F) + ((t >> 6) & 0x7F) + ((t >> 13) & 0x7F) + ((t >> 19) & 0x7F))


cdef inline int _msb_play(long long lo, long long hi, int play) noexcept nogil:
    cdef long long low, mid1, mid2, him
    if play == 1:
        low = lo & 0x7FFFFFF
        if low != 0:
            return _ctz64(low)
        mid1 = (lo >> 27) & 0x7FFFFFF
        if mid1 != 0:
            return 27 + _ctz64(mid1)
        mid2 = ((lo >> 54) & 0x3FF) | ((hi & 0x1FFFF) << 10)
        if mid2 != 0:
            return 54 + _ctz64(mid2)
        him = (hi >> 17) & 0x1FF
        if him != 0:
            return 81 + _ctz64(him)
        return -1
    him = (hi >> 17) & 0x1FF
    if him != 0:
        return 81 + _ctz64(him)
    mid2 = ((lo >> 54) & 0x3FF) | ((hi & 0x1FFFF) << 10)
    if mid2 != 0:
        return 54 + _ctz64(mid2)
    mid1 = (lo >> 27) & 0x7FFFFFF
    if mid1 != 0:
        return 27 + _ctz64(mid1)
    low = lo & 0x7FFFFFF
    if low != 0:
        return _ctz64(low)
    return -1


cdef inline void _emit_red(long long lo, long long hi, int src, long long* buf, int* count) noexcept nogil:
    cdef long long m = lo
    cdef int idx
    while m != 0:
        idx = _ctz64(m)
        buf[count[0]] = <long long>src | (<long long>idx << 7)
        count[0] += 1
        m &= m - 1
    m = hi & 0x3FFFFFF
    while m != 0:
        idx = _ctz64(m)
        buf[count[0]] = <long long>src | (<long long>(64 + idx) << 7)
        count[0] += 1
        m &= m - 1


cdef inline void _emit_black(long long lo, long long hi, int src, long long* buf, int* count) noexcept nogil:
    cdef long long m = (hi >> 17) & 0x1FF
    cdef int idx
    while m != 0:
        idx = _ctz64(m)
        buf[count[0]] = <long long>src | (<long long>(81 + idx) << 7)
        count[0] += 1
        m &= m - 1
    m = ((lo >> 54) & 0x3FF) | ((hi & 0x1FFFF) << 10)
    while m != 0:
        idx = _ctz64(m)
        buf[count[0]] = <long long>src | (<long long>(54 + idx) << 7)
        count[0] += 1
        m &= m - 1
    m = (lo >> 27) & 0x7FFFFFF
    while m != 0:
        idx = _ctz64(m)
        buf[count[0]] = <long long>src | (<long long>(27 + idx) << 7)
        count[0] += 1
        m &= m - 1
    m = lo & 0x7FFFFFF
    while m != 0:
        idx = _ctz64(m)
        buf[count[0]] = <long long>src | (<long long>idx << 7)
        count[0] += 1
        m &= m - 1


cdef inline int _has_site(long long lo, long long hi, int site) noexcept nogil:
    if site < 64:
        return <int>((lo >> site) & 1)
    return <int>((hi >> (site - 64)) & 1)


cdef int MAX_SCORE = 9999
cdef int LONG_CHECK_SCORE = 8888
cdef int DRAW_SCORE = 0
cdef int MATE_BOUND = 9899
cdef int QUIESC_GOOD = 150
cdef int HASH_BETA = 1
cdef int HASH_ALPHA = 2
cdef int HASH_PV = 3
cdef int MAX_PLY = 64
cdef int FAIL_SENTINEL = -2147483647


cdef inline int _radapt(int depth) noexcept nogil:
    if depth <= 6:
        return 2
    if depth <= 8:
        return 3
    return 4


cdef inline int _futility(int d, int k) noexcept nogil:
    return <int>((<double>d * 1.29 * 155.0)) - k * d * 10


cdef inline long long _pack_tt(int etype, int value, int depth, int move) noexcept nogil:
    return ((<long long>value) & (<long long>0xFFFFFFFF)) | ((<long long>etype) << 32) | ((<long long>depth) << 34) | ((<long long>move) << 42)


cdef inline int _tt_value(long long d) noexcept nogil:
    cdef long long v = d & (<long long>0xFFFFFFFF)
    if v >= (<long long>0x80000000):
        v -= (<long long>0x100000000)
    return <int>v


cpdef init_eval_tables(dict t):
    global _CH_ATK_R_LO, _CH_ATK_R_HI, _CH_ATK_C_LO, _CH_ATK_C_HI
    global _MV_R_LO, _MV_R_HI, _MV_C_LO, _MV_C_HI
    global _GUN_ATK_R_LO, _GUN_ATK_R_HI, _GUN_ATK_C_LO, _GUN_ATK_C_HI
    global _GUN_FK_R_LO, _GUN_FK_R_HI, _GUN_FK_C_LO, _GUN_FK_C_HI
    global _GUN_MR_R_LO, _GUN_MR_R_HI, _GUN_MR_C_LO, _GUN_MR_C_HI
    global _KN_LEG_LO, _KN_LEG_HI, _KN_ATK_LO, _KN_ATK_HI
    global _EL_LEG_LO, _EL_LEG_HI, _EL_ATK_LO, _EL_ATK_HI
    global _KING_LO, _KING_HI, _GUARD_LO, _GUARD_HI, _SOL_LO, _SOL_HI, _KCS_LO, _KCS_HI
    global _KN_TGT_LO, _KN_TGT_HI, _PIECE_KINDS, _DANGER_LO, _DANGER_HI
    global _CG_MOB_R, _CG_MOB_C
    global _ATK_PART, _DEF_PART, _MIN_MOB, _MOB_REW, _GE_NUM, _GUN_DEP, _KN_DEP
    global _ROLE_PART, _SOL_PROT, _GUN_NG, _KN_NG
    _CH_ATK_R_LO = t["CHARIOT_ATTACK_ROW_LO"]
    _CH_ATK_R_HI = t["CHARIOT_ATTACK_ROW_HI"]
    _CH_ATK_C_LO = t["CHARIOT_ATTACK_COL_LO"]
    _CH_ATK_C_HI = t["CHARIOT_ATTACK_COL_HI"]
    _MV_R_LO = t["MOVE_CHARIOT_GUN_ROW_LO"]
    _MV_R_HI = t["MOVE_CHARIOT_GUN_ROW_HI"]
    _MV_C_LO = t["MOVE_CHARIOT_GUN_COL_LO"]
    _MV_C_HI = t["MOVE_CHARIOT_GUN_COL_HI"]
    _GUN_ATK_R_LO = t["GUN_ATTACK_ROW_LO"]
    _GUN_ATK_R_HI = t["GUN_ATTACK_ROW_HI"]
    _GUN_ATK_C_LO = t["GUN_ATTACK_COL_LO"]
    _GUN_ATK_C_HI = t["GUN_ATTACK_COL_HI"]
    _GUN_FK_R_LO = t["GUN_FAKE_ATTACK_ROW_LO"]
    _GUN_FK_R_HI = t["GUN_FAKE_ATTACK_ROW_HI"]
    _GUN_FK_C_LO = t["GUN_FAKE_ATTACK_COL_LO"]
    _GUN_FK_C_HI = t["GUN_FAKE_ATTACK_COL_HI"]
    _GUN_MR_R_LO = t["GUN_MORE_REST_ATTACK_ROW_LO"]
    _GUN_MR_R_HI = t["GUN_MORE_REST_ATTACK_ROW_HI"]
    _GUN_MR_C_LO = t["GUN_MORE_REST_ATTACK_COL_LO"]
    _GUN_MR_C_HI = t["GUN_MORE_REST_ATTACK_COL_HI"]
    _KN_LEG_LO = t["KNIGHT_LEG_LO"]
    _KN_LEG_HI = t["KNIGHT_LEG_HI"]
    _KN_ATK_LO = t["KNIGHT_ATTACK_LIMIT_LO"]
    _KN_ATK_HI = t["KNIGHT_ATTACK_LIMIT_HI"]
    _EL_LEG_LO = t["ELEPHANT_LEG_LO"]
    _EL_LEG_HI = t["ELEPHANT_LEG_HI"]
    _EL_ATK_LO = t["ELEPHANT_ATTACK_LIMIT_LO"]
    _EL_ATK_HI = t["ELEPHANT_ATTACK_LIMIT_HI"]
    _KING_LO = t["KING_TARGET_LO"]
    _KING_HI = t["KING_TARGET_HI"]
    _GUARD_LO = t["GUARD_TARGET_LO"]
    _GUARD_HI = t["GUARD_TARGET_HI"]
    _SOL_LO = t["SOLDIER_TARGET_LO"]
    _SOL_HI = t["SOLDIER_TARGET_HI"]
    _KCS_LO = t["KING_CHECKED_SOLDIER_LO"]
    _KCS_HI = t["KING_CHECKED_SOLDIER_HI"]
    _KN_TGT_LO = t["KNIGHT_TARGET_LO"]
    _KN_TGT_HI = t["KNIGHT_TARGET_HI"]
    _PIECE_KINDS = t["PIECE_KINDS"]
    _DANGER_LO = t["DANGER_MARGIN_LO"]
    _DANGER_HI = t["DANGER_MARGIN_HI"]
    _CG_MOB_R = t["CHARIOT_GUN_MOBILITY_ROW"]
    _CG_MOB_C = t["CHARIOT_GUN_MOBILITY_COL"]
    _ATK_PART = t["ATTACK_PARTITION_SCORE"]
    _DEF_PART = t["DEFENSE_PARTITION_SCORE"]
    _MIN_MOB = t["MIN_MOBILITY"]
    _MOB_REW = t["MOBILITY_REWARDS"]
    _GE_NUM = t["GUARD_ELEPHANT_NUM_SCORE"]
    _GUN_DEP = t["GUN_NUM_SCORE_DEPEND_GUARD"]
    _KN_DEP = t["KNIGHT_NUM_SCORE_DEPEND_GUARD"]
    _ROLE_PART = t["ROLE_PARTITION_SITE"]
    _SOL_PROT = t["SOLDIERS_PROTECTED"]
    _GUN_NG = t["GUN_OPPT_NOT_GUARD"]
    _KN_NG = t["KNIGHT_OPPT_NOT_GUARD"]


cpdef init_tables(z64, z32, mid_red, mid_blk, end_red, end_blk,
                  piece_roles, ad_index, mask_lo, mask_hi):
    global _Z64, _Z32, _MID_RED, _MID_BLK, _END_RED, _END_BLK
    global _PIECE_ROLES, _AD_INDEX, _MASK_LO, _MASK_HI, _keep_alive
    _Z64 = z64
    _Z32 = z32
    _MID_RED = mid_red
    _MID_BLK = mid_blk
    _END_RED = end_red
    _END_BLK = end_blk
    _PIECE_ROLES = piece_roles
    _AD_INDEX = ad_index
    import numpy as _np
    ml = _np.ascontiguousarray(mask_lo, dtype=_np.int64)
    mh = _np.ascontiguousarray(mask_hi, dtype=_np.int64)
    _keep_alive = (ml, mh)
    _MASK_LO = <long long*>cnp.PyArray_DATA(ml)
    _MASK_HI = <long long*>cnp.PyArray_DATA(mh)


cdef class BoardState:
    cdef:
        int board[90]
        int all_chess[48]
        int remain[15]
        int attack_def[2][2]
        int base_score[17]
        long long mask_all[2]
        long long mask_personal[2][2]
        long long mask_role[15][2]
        short bit_row[10]
        short bit_col[9]
        long long zob[2]
        int phase
        int side_to_move
        int attack[48]
        int defense[48]

    cpdef load_from_state(self, object st):
        cdef int i, j
        cdef object board = st.board
        cdef object allc = st.all_chess
        cdef object remain = st.remain
        cdef object ad = st.attack_def
        cdef object base = st.base_score
        cdef object ma = st.mask_all
        cdef object mp = st.mask_personal
        cdef object mr = st.mask_role
        cdef object br = st.bit_row
        cdef object bc = st.bit_col
        cdef object zob = st.zob
        cdef object stm = st.side_to_move
        for i in range(90):
            self.board[i] = <int>board[i]
        for i in range(48):
            self.all_chess[i] = <int>allc[i]
        for i in range(15):
            self.remain[i] = <int>remain[i]
        for i in range(2):
            for j in range(2):
                self.attack_def[i][j] = <int>ad[i, j]
        for i in range(17):
            self.base_score[i] = <int>base[i]
        for i in range(2):
            self.mask_all[i] = <long long>ma[i]
            for j in range(2):
                self.mask_personal[i][j] = <long long>mp[i, j]
        for i in range(15):
            self.mask_role[i][0] = <long long>mr[i, 0]
            self.mask_role[i][1] = <long long>mr[i, 1]
        for i in range(10):
            self.bit_row[i] = <short>br[i]
        for i in range(9):
            self.bit_col[i] = <short>bc[i]
        for i in range(2):
            self.zob[i] = <long long>zob[i]
        self.phase = <int>stm[1]
        self.side_to_move = <int>stm[0]

    cdef inline int _attach(self, int role, int site) noexcept nogil:
        if self.phase == 0:
            if role <= 7:
                return _MID_RED[role - 1, site]
            return _MID_BLK[role - 8, site]
        if role <= 7:
            return _END_RED[role - 1, site]
        return _END_BLK[role - 8, site]

    cdef inline void make(self, long long m, int* out_dest_chess, int* out_play) noexcept nogil:
        cdef int src = <int>(m & 127)
        cdef int dest = <int>(m >> 7)
        cdef int chess = self.board[src]
        cdef int role = _PIECE_ROLES[chess]
        cdef int play = 0 if chess < 32 else 1
        cdef int dest_chess = self.board[dest]
        cdef int dest_role = 0
        cdef long long lo_src = _MASK_LO[src]
        cdef long long hi_src = _MASK_HI[src]
        cdef long long lo_dest = _MASK_LO[dest]
        cdef long long hi_dest = _MASK_HI[dest]
        cdef int dest_play, src_row, src_col, dest_row, dest_col
        if dest_chess != 0:
            dest_role = _PIECE_ROLES[dest_chess]

        self.base_score[play] -= self._attach(role, src)
        self.base_score[play] += self._attach(role, dest)
        if dest_chess != 0:
            dest_play = 1 - play
            self.base_score[dest_play] -= self.base_score[2 + dest_role]
            self.base_score[dest_play] -= self._attach(dest_role, dest)

        self.mask_all[0] ^= lo_src
        self.mask_all[1] ^= hi_src
        self.mask_all[0] |= lo_dest
        self.mask_all[1] |= hi_dest
        self.mask_personal[play][0] ^= lo_src
        self.mask_personal[play][1] ^= hi_src
        self.mask_personal[play][0] ^= lo_dest
        self.mask_personal[play][1] ^= hi_dest
        self.mask_role[role][0] ^= lo_src
        self.mask_role[role][1] ^= hi_src
        self.mask_role[role][0] ^= lo_dest
        self.mask_role[role][1] ^= hi_dest
        if dest_chess != 0:
            self.mask_personal[1 - play][0] ^= lo_dest
            self.mask_personal[1 - play][1] ^= hi_dest
            self.mask_role[dest_role][0] ^= lo_dest
            self.mask_role[dest_role][1] ^= hi_dest
            self.remain[dest_role] -= 1
            self.attack_def[1 - play][_AD_INDEX[dest_role]] -= 1
            self.all_chess[dest_chess] = -1

        self.board[src] = 0
        self.board[dest] = chess
        self.all_chess[chess] = dest

        src_row = src // 9
        src_col = src - src_row * 9
        dest_row = dest // 9
        dest_col = dest - dest_row * 9
        self.bit_row[dest_row] = self.bit_row[dest_row] | (1 << (8 - dest_col))
        self.bit_col[dest_col] = self.bit_col[dest_col] | (1 << (9 - dest_row))
        self.bit_row[src_row] = self.bit_row[src_row] ^ (1 << (8 - src_col))
        self.bit_col[src_col] = self.bit_col[src_col] ^ (1 << (9 - src_row))

        self.zob[0] ^= _Z32[src, role]
        self.zob[0] ^= _Z32[dest, role]
        self.zob[1] ^= _Z64[src, role]
        self.zob[1] ^= _Z64[dest, role]
        if dest_chess != 0:
            self.zob[0] ^= _Z32[dest, dest_role]
            self.zob[1] ^= _Z64[dest, dest_role]

        self.side_to_move = 1 - self.side_to_move
        out_dest_chess[0] = dest_chess
        out_play[0] = play

    cdef inline void unmake(self, long long m, int dest_chess, int play) noexcept nogil:
        cdef int src = <int>(m & 127)
        cdef int dest = <int>(m >> 7)
        cdef int chess = self.board[dest]
        cdef int role = _PIECE_ROLES[chess]
        cdef int dest_role = 0
        cdef long long lo_src = _MASK_LO[src]
        cdef long long hi_src = _MASK_HI[src]
        cdef long long lo_dest = _MASK_LO[dest]
        cdef long long hi_dest = _MASK_HI[dest]
        cdef int src_row, src_col, dest_row, dest_col
        if dest_chess != 0:
            dest_role = _PIECE_ROLES[dest_chess]

        self.base_score[play] -= self._attach(role, dest)
        self.base_score[play] += self._attach(role, src)
        if dest_chess != 0:
            self.base_score[1 - play] += self.base_score[2 + dest_role]
            self.base_score[1 - play] += self._attach(dest_role, dest)

        self.mask_personal[play][0] ^= lo_dest
        self.mask_personal[play][1] ^= hi_dest
        self.mask_personal[play][0] ^= lo_src
        self.mask_personal[play][1] ^= hi_src
        self.mask_role[role][0] ^= lo_dest
        self.mask_role[role][1] ^= hi_dest
        self.mask_role[role][0] ^= lo_src
        self.mask_role[role][1] ^= hi_src
        self.mask_all[0] ^= lo_src
        self.mask_all[1] ^= hi_src
        if dest_chess == 0:
            self.mask_all[0] ^= lo_dest
            self.mask_all[1] ^= hi_dest
        else:
            self.mask_personal[1 - play][0] ^= lo_dest
            self.mask_personal[1 - play][1] ^= hi_dest
            self.mask_role[dest_role][0] ^= lo_dest
            self.mask_role[dest_role][1] ^= hi_dest
            self.remain[dest_role] += 1
            self.attack_def[1 - play][_AD_INDEX[dest_role]] += 1
            self.all_chess[dest_chess] = dest

        self.board[dest] = dest_chess
        self.board[src] = chess
        self.all_chess[chess] = src

        src_row = src // 9
        src_col = src - src_row * 9
        dest_row = dest // 9
        dest_col = dest - dest_row * 9
        self.bit_row[src_row] = self.bit_row[src_row] | (1 << (8 - src_col))
        self.bit_col[src_col] = self.bit_col[src_col] | (1 << (9 - src_row))
        if dest_chess == 0:
            self.bit_row[dest_row] = self.bit_row[dest_row] ^ (1 << (8 - dest_col))
            self.bit_col[dest_col] = self.bit_col[dest_col] ^ (1 << (9 - dest_row))

        self.zob[0] ^= _Z32[src, role]
        self.zob[0] ^= _Z32[dest, role]
        self.zob[1] ^= _Z64[src, role]
        self.zob[1] ^= _Z64[dest, role]
        if dest_chess != 0:
            self.zob[0] ^= _Z32[dest, dest_role]
            self.zob[1] ^= _Z64[dest, dest_role]

        self.side_to_move = 1 - self.side_to_move

    cpdef bench_make_unmake(self, object moves, int n):
        cdef int cnt = len(moves)
        cdef long long[256] buf
        cdef int i, k, dc = 0, pl = 0
        cdef long long s = 0
        cdef object mv
        for i in range(cnt):
            mv = moves[i]
            buf[i] = <long long>mv
        with nogil:
            for k in range(n):
                i = k % cnt
                self.make(buf[i], &dc, &pl)
                self.unmake(buf[i], dc, pl)
                s += dc
        return s

    cpdef make_move_py(self, long long m):
        cdef int dc = 0, pl = 0
        self.make(m, &dc, &pl)
        return (dc, pl)

    cpdef unmake_move_py(self, long long m, int dc, int pl):
        self.unmake(m, dc, pl)

    cpdef dump(self):
        cdef int i
        return {
            "zob": [self.zob[0], self.zob[1]],
            "base_score": [self.base_score[i] for i in range(17)],
            "board": [self.board[i] for i in range(90)],
            "all_chess": [self.all_chess[i] for i in range(48)],
            "remain": [self.remain[i] for i in range(15)],
            "bit_row": [self.bit_row[i] for i in range(10)],
            "bit_col": [self.bit_col[i] for i in range(9)],
            "side_to_move": self.side_to_move,
        }

    cdef inline void _dyn_partition(self) noexcept nogil:
        cdef int i
        for i in range(48):
            self.attack[i] = _ATK_PART[i]
            self.defense[i] = _DEF_PART[i]
        cdef int rg = self.remain[2]
        cdef int re = self.remain[3]
        cdef int bg = self.remain[9]
        cdef int be = self.remain[10]
        self.defense[23] = _GE_NUM[be]
        self.defense[24] = _GE_NUM[be]
        self.defense[25] = _GE_NUM[bg]
        self.defense[26] = _GE_NUM[bg]
        self.defense[39] = _GE_NUM[re]
        self.defense[40] = _GE_NUM[re]
        self.defense[41] = _GE_NUM[rg]
        self.defense[42] = _GE_NUM[rg]
        self.attack[19] = _KN_DEP[rg]
        self.attack[20] = _KN_DEP[rg]
        self.attack[21] = _GUN_DEP[rg]
        self.attack[22] = _GUN_DEP[rg]
        self.attack[35] = _KN_DEP[bg]
        self.attack[36] = _KN_DEP[bg]
        self.attack[37] = _GUN_DEP[bg]
        self.attack[38] = _GUN_DEP[bg]

    cdef inline void _all_move(self, int role, int site, int play, long long* olo, long long* ohi) noexcept nogil:
        cdef int br = role % 7
        cdef int rm, cm, key
        if br == 6:
            rm = self.bit_row[site // 9]
            cm = self.bit_col[site % 9]
            olo[0] = _CH_ATK_R_LO[site, rm] ^ _CH_ATK_C_LO[site, cm] ^ _MV_R_LO[site, rm] ^ _MV_C_LO[site, cm]
            ohi[0] = _CH_ATK_R_HI[site, rm] ^ _CH_ATK_C_HI[site, cm] ^ _MV_R_HI[site, rm] ^ _MV_C_HI[site, cm]
        elif br == 5:
            key = _csum_knight(_KN_LEG_LO[site] & self.mask_all[0], _KN_LEG_HI[site] & self.mask_all[1])
            olo[0] = _KN_ATK_LO[site, key]
            ohi[0] = _KN_ATK_HI[site, key]
        elif br == 4:
            rm = self.bit_row[site // 9]
            cm = self.bit_col[site % 9]
            olo[0] = _GUN_ATK_R_LO[site, rm] ^ _GUN_ATK_C_LO[site, cm] ^ _GUN_FK_R_LO[site, rm] ^ _GUN_FK_C_LO[site, cm]
            ohi[0] = _GUN_ATK_R_HI[site, rm] ^ _GUN_ATK_C_HI[site, cm] ^ _GUN_FK_R_HI[site, rm] ^ _GUN_FK_C_HI[site, cm]
        elif br == 3:
            key = _csum_elephant(_EL_LEG_LO[site] & self.mask_all[0], _EL_LEG_HI[site] & self.mask_all[1])
            olo[0] = _EL_ATK_LO[site, key]
            ohi[0] = _EL_ATK_HI[site, key]
        elif br == 2:
            olo[0] = _GUARD_LO[site]
            ohi[0] = _GUARD_HI[site]
        elif br == 1:
            olo[0] = _SOL_LO[play, site]
            ohi[0] = _SOL_HI[play, site]
        else:
            olo[0] = _KING_LO[site]
            ohi[0] = _KING_HI[site]

    cdef inline int _mobility(self, int role, int site, long long own_lo, long long own_hi) noexcept nogil:
        cdef int br = role % 7
        cdef int rm, cm, key
        cdef long long alo, ahi, klo, khi
        if br == 6 or br == 4:
            rm = self.bit_row[site // 9]
            cm = self.bit_col[site % 9]
            return _CG_MOB_R[site, rm] + _CG_MOB_C[site, cm]
        if br == 5:
            key = _csum_knight(_KN_LEG_LO[site] & self.mask_all[0], _KN_LEG_HI[site] & self.mask_all[1])
            alo = _KN_ATK_LO[site, key]
            ahi = _KN_ATK_HI[site, key]
            return _popcount64(alo) + _popcount64(ahi) - _popcount64(alo & own_lo) - _popcount64(ahi & own_hi)
        if br == 0:
            klo = _KING_LO[site]
            khi = _KING_HI[site]
            return _popcount64(klo ^ (klo & self.mask_all[0])) + _popcount64(khi ^ (khi & self.mask_all[1]))
        return 0

    cdef inline void _comp_partition(self, int play, int site, int chess, int* part) noexcept nogil:
        cdef int par = _ROLE_PART[_PIECE_ROLES[chess], site]
        cdef int a = self.attack[chess]
        cdef int d = self.defense[chess]
        if play == 1:
            if par == 1:
                part[1] += a
            elif par == 2:
                part[2] += a
            elif par == 3:
                part[3] += a
            elif par == 31:
                part[3] += a; part[1] += a
            elif par == 32:
                part[3] += a; part[2] += a
            elif par == 33:
                part[3] += a; part[2] += a; part[1] += a
            elif par == 4:
                part[4] += d
            elif par == 5:
                part[5] += d
            elif par == 6:
                part[6] += d
            elif par == 64:
                part[6] += d; part[4] += d
            elif par == 65:
                part[6] += d; part[5] += d
            elif par == 66:
                part[6] += d; part[5] += d; part[4] += d
        else:
            if par == 1:
                part[1] += d
            elif par == 2:
                part[2] += d
            elif par == 3:
                part[3] += d
            elif par == 31:
                part[3] += d; part[1] += d
            elif par == 32:
                part[3] += d; part[2] += d
            elif par == 33:
                part[3] += d; part[2] += d; part[1] += d
            elif par == 4:
                part[4] += a
            elif par == 5:
                part[5] += a
            elif par == 6:
                part[6] += a
            elif par == 64:
                part[6] += a; part[4] += a
            elif par == 65:
                part[6] += a; part[5] += a
            elif par == 66:
                part[6] += a; part[5] += a; part[4] += a

    cdef inline int _exposed(self, int play, int ks, int row, int col) noexcept nogil:
        cdef long long lo = _CH_ATK_R_LO[ks, row] ^ _CH_ATK_C_LO[ks, col]
        cdef long long hi = _CH_ATK_R_HI[ks, row] ^ _CH_ATK_C_HI[ks, col]
        cdef int role = 4 + 7 * (1 - play)
        lo &= self.mask_role[role][0]
        hi &= self.mask_role[role][1]
        if (lo | hi) == 0:
            return -1
        return _msb_play(lo, hi, play)

    cdef inline int _bottom(self, int play, int ks, int row, int col) noexcept nogil:
        cdef long long lo = _GUN_MR_R_LO[ks, row] ^ _GUN_MR_C_LO[ks, col]
        cdef long long hi = _GUN_MR_R_HI[ks, row] ^ _GUN_MR_C_HI[ks, col]
        cdef int role = 4 + 7 * (1 - play)
        lo &= self.mask_role[role][0]
        hi &= self.mask_role[role][1]
        if (lo | hi) == 0:
            return -1
        return _msb_play(lo, hi, play)

    cdef inline int _rest(self, int play, int ks, int row, int col) noexcept nogil:
        cdef long long lo = _GUN_ATK_R_LO[ks, row] ^ _GUN_ATK_C_LO[ks, col]
        cdef long long hi = _GUN_ATK_R_HI[ks, row] ^ _GUN_ATK_C_HI[ks, col]
        cdef int role = 6 + 7 * (1 - play)
        lo &= self.mask_role[role][0]
        hi &= self.mask_role[role][1]
        if (lo | hi) == 0:
            return -1
        return _msb_play(lo, hi, play)

    cdef inline int _abs(self, int x) noexcept nogil:
        return x if x >= 0 else -x

    cdef int _evaluate(self, int play) noexcept nogil:
        cdef int score[2]
        cdef int part[2][7]
        cdef long long mlo[2]
        cdef long long mhi[2]
        cdef signed char kunmove[2]
        cdef int ap[2][3]
        cdef int dp[2][3]
        cdef int i, j, side, chess, site, role, currplay, mobility
        cdef long long alo, ahi, mlo_i, mhi_i
        cdef int opp, gun_num, opp_ks, row, col, opp_all, extend, v, king_col, king_row
        cdef int weakness, chariot_num, knight_num, opp_ele, opp_guard
        cdef int gs
        for i in range(2):
            score[i] = self.base_score[i]
            for j in range(7):
                part[i][j] = 0
            mlo[i] = 0
            mhi[i] = 0
            kunmove[i] = 0
        self._dyn_partition()
        for chess in range(16, 48):
            site = self.all_chess[chess]
            if site < 0:
                continue
            currplay = 0 if chess < 32 else 1
            role = _PIECE_ROLES[chess]
            self._all_move(role, site, currplay, &alo, &ahi)
            self._comp_partition(currplay, site, chess, part[currplay])
            mlo[currplay] |= alo
            mhi[currplay] |= ahi
            if _MIN_MOB[chess] > 0:
                mobility = self._mobility(role, site, self.mask_personal[currplay][0], self.mask_personal[currplay][1])
                if mobility < _MIN_MOB[chess]:
                    score[currplay] -= (_MIN_MOB[chess] - mobility) * _MOB_REW[chess]
                    if role == 7:
                        kunmove[1] = 1
                    elif role == 14:
                        kunmove[0] = 1
        ap[1][0] = part[1][1]; ap[1][1] = part[1][2]; ap[1][2] = part[1][3]
        dp[1][0] = part[1][4]; dp[1][1] = part[1][5]; dp[1][2] = part[1][6]
        ap[0][0] = part[0][4]; ap[0][1] = part[0][5]; ap[0][2] = part[0][6]
        dp[0][0] = part[0][1]; dp[0][1] = part[0][2]; dp[0][2] = part[0][3]

        for i in range(2):
            opp = 1 - i
            mlo_i = mlo[i]
            mhi_i = mhi[i]
            score[i] += (_popcount64(mlo_i & (self.mask_role[6 + 7 * (1 - i)][0] | self.mask_role[5 + 7 * (1 - i)][0] | self.mask_role[4 + 7 * (1 - i)][0]))
                         + _popcount64(mhi_i & (self.mask_role[6 + 7 * (1 - i)][1] | self.mask_role[5 + 7 * (1 - i)][1] | self.mask_role[4 + 7 * (1 - i)][1]))) * 10
            score[i] += (_popcount64(mlo_i & (self.mask_role[3 + 7 * (1 - i)][0] | self.mask_role[2 + 7 * (1 - i)][0] | self.mask_role[1 + 7 * (1 - i)][0]))
                         + _popcount64(mhi_i & (self.mask_role[3 + 7 * (1 - i)][1] | self.mask_role[2 + 7 * (1 - i)][1] | self.mask_role[1 + 7 * (1 - i)][1]))) * 6
            score[i] += (_popcount64(mlo_i & (self.mask_role[6 + 7 * i][0] | self.mask_role[5 + 7 * i][0] | self.mask_role[4 + 7 * i][0]))
                         + _popcount64(mhi_i & (self.mask_role[6 + 7 * i][1] | self.mask_role[5 + 7 * i][1] | self.mask_role[4 + 7 * i][1]))) * 18
            score[i] += (_popcount64(mlo_i & (self.mask_role[3 + 7 * i][0] | self.mask_role[2 + 7 * i][0] | self.mask_role[1 + 7 * i][0]))
                         + _popcount64(mhi_i & (self.mask_role[3 + 7 * i][1] | self.mask_role[2 + 7 * i][1] | self.mask_role[1 + 7 * i][1]))) * 9

            gun_num = self.remain[4 + 7 * (1 - i)]
            opp_ks = self.all_chess[16 + 16 * opp]
            row = self.bit_row[opp_ks // 9]
            col = self.bit_col[opp_ks % 9]
            opp_all = self.attack_def[opp][0] + self.attack_def[opp][1] - 1
            weakness = 0
            if gun_num > 0:
                gs = self._exposed(i, opp_ks, row, col)
                if opp_all > 5 and gs != -1:
                    extend = self._abs((opp_ks // 9 - gs // 9) + (opp_ks % 9 - gs % 9))
                    score[i] += extend * 45
                    weakness = 1
                gs = self._bottom(i, opp_ks, row, col)
                if gs != -1:
                    extend = self._abs((opp_ks // 9 - gs // 9) + (opp_ks % 9 - gs % 9))
                    if extend <= 3:
                        score[i] += 100
                        weakness = 1
            if self._rest(i, opp_ks, row, col) != 1:
                score[i] += 30
            if weakness:
                dp[opp][0] -= 1; dp[opp][1] -= 1; dp[opp][2] -= 1
            if kunmove[opp]:
                v = 1
                if weakness:
                    v = 2
                dp[opp][0] -= v; dp[opp][1] -= v; dp[opp][2] -= v
            king_col = opp_ks % 9
            if king_col == 3:
                dp[opp][0] -= 1
            elif king_col == 5:
                dp[opp][1] -= 1
            elif king_col == 4:
                king_row = opp_ks // 9
                if king_row == 1 or king_row == 2 or king_row == 8 or king_row == 7:
                    dp[opp][2] -= 1
            for side in range(3):
                if ap[i][side] > dp[opp][side]:
                    score[i] += (ap[i][side] - dp[opp][side]) * 30
            chariot_num = self.remain[6 + 7 * (1 - i)]
            knight_num = self.remain[5 + 7 * (1 - i)]
            opp_ele = self.remain[3 + 7 * i]
            opp_guard = self.remain[2 + 7 * i]
            if opp_ele < 2 and opp_guard >= 2 and gun_num > 0:
                score[i] += 60
            if opp_guard < 2 and knight_num > 0:
                score[i] += 60
            if chariot_num > 0:
                score[i] += 100
            if knight_num > 0:
                score[i] += 100
            if gun_num > 0:
                score[i] += 100
        return score[play] - score[1 - play]

    cdef int _evaluate_endgame(self, int play) noexcept nogil:
        cdef int score[2]
        cdef int curplay, role_soldier, soldier_num, gun_num, knight_num, opp_guard
        cdef int site, chess, cnt
        cdef long long alo, ahi, a2lo, a2hi, plo, phi
        score[0] = self.base_score[0]
        score[1] = self.base_score[1]
        for curplay in range(2):
            role_soldier = 1 + 7 * (1 - curplay)
            soldier_num = self.remain[role_soldier]
            gun_num = self.remain[4 + 7 * (1 - curplay)]
            knight_num = self.remain[5 + 7 * (1 - curplay)]
            if soldier_num >= 2:
                alo = 0
                ahi = 0
                for chess in range(27 + 16 * curplay, 32 + 16 * curplay):
                    site = self.all_chess[chess]
                    if site < 0:
                        continue
                    self._all_move(role_soldier, site, curplay, &a2lo, &a2hi)
                    alo |= a2lo
                    ahi |= a2hi
                plo = alo & self.mask_role[role_soldier][0]
                phi = ahi & self.mask_role[role_soldier][1]
                cnt = _popcount64(plo) + _popcount64(phi)
                score[curplay] += _SOL_PROT[cnt]
            opp_guard = self.remain[2 + 7 * curplay]
            if gun_num > 0:
                if gun_num == 2:
                    score[curplay] += <int>(_GUN_NG[opp_guard] * 1.7)
                else:
                    score[curplay] += _GUN_NG[opp_guard]
            if knight_num > 0:
                if knight_num == 2:
                    score[curplay] += <int>(_KN_NG[opp_guard] * 1.7)
                else:
                    score[curplay] += _KN_NG[opp_guard]
        return score[play] - score[1 - play]

    cpdef int evaluate_py(self, int play):
        cdef int r
        with nogil:
            if self.phase == 1:
                r = self._evaluate_endgame(play)
            else:
                r = self._evaluate(play)
        return r

    cdef inline void _target_mask(self, int role, int src, int capture, int play,
                                  long long* olo, long long* ohi) noexcept nogil:
        cdef int br = role % 7
        cdef int rm, cm, key
        if br == 6:
            rm = self.bit_row[src // 9]
            cm = self.bit_col[src % 9]
            if capture:
                olo[0] = _CH_ATK_R_LO[src, rm] ^ _CH_ATK_C_LO[src, cm]
                ohi[0] = _CH_ATK_R_HI[src, rm] ^ _CH_ATK_C_HI[src, cm]
            else:
                olo[0] = _MV_R_LO[src, rm] ^ _MV_C_LO[src, cm]
                ohi[0] = _MV_R_HI[src, rm] ^ _MV_C_HI[src, cm]
        elif br == 4:
            rm = self.bit_row[src // 9]
            cm = self.bit_col[src % 9]
            if capture:
                olo[0] = _GUN_ATK_R_LO[src, rm] ^ _GUN_ATK_C_LO[src, cm]
                ohi[0] = _GUN_ATK_R_HI[src, rm] ^ _GUN_ATK_C_HI[src, cm]
            else:
                olo[0] = _MV_R_LO[src, rm] ^ _MV_C_LO[src, cm]
                ohi[0] = _MV_R_HI[src, rm] ^ _MV_C_HI[src, cm]
        elif br == 5:
            key = _csum_knight(_KN_LEG_LO[src] & self.mask_all[0], _KN_LEG_HI[src] & self.mask_all[1])
            olo[0] = _KN_ATK_LO[src, key]
            ohi[0] = _KN_ATK_HI[src, key]
        elif br == 3:
            key = _csum_elephant(_EL_LEG_LO[src] & self.mask_all[0], _EL_LEG_HI[src] & self.mask_all[1])
            olo[0] = _EL_ATK_LO[src, key]
            ohi[0] = _EL_ATK_HI[src, key]
        elif br == 0:
            olo[0] = _KING_LO[src]
            ohi[0] = _KING_HI[src]
        elif br == 2:
            olo[0] = _GUARD_LO[src]
            ohi[0] = _GUARD_HI[src]
        else:
            olo[0] = _SOL_LO[play, src]
            ohi[0] = _SOL_HI[play, src]

    cdef inline void _gen_piece(self, int piece, int play, int capture,
                                long long opp0, long long opp1,
                                long long empty0, long long empty1,
                                long long* buf, int* count) noexcept nogil:
        cdef int src = self.all_chess[piece]
        cdef int role
        cdef long long lo, hi
        if src < 0:
            return
        role = _PIECE_ROLES[piece]
        self._target_mask(role, src, capture, play, &lo, &hi)
        if capture:
            lo &= opp0
            hi &= opp1
        else:
            lo &= empty0
            hi &= empty1
        if play == 1:
            _emit_red(lo, hi, src, buf, count)
        else:
            _emit_black(lo, hi, src, buf, count)

    cdef int _gen_moves(self, int play, long long* buf, int captures_only) noexcept nogil:
        cdef int begin = 16 if play == 0 else 32
        cdef int i, count = 0
        cdef long long opp0, opp1, empty0 = 0, empty1 = 0
        opp0 = self.mask_personal[1 - play][0]
        opp1 = self.mask_personal[1 - play][1]
        if not captures_only:
            empty0 = ~self.mask_all[0]
            empty1 = (~self.mask_all[1]) & 0x3FFFFFF
        for i in range(1, 16):
            self._gen_piece(begin + i, play, 1, opp0, opp1, empty0, empty1, buf, &count)
        self._gen_piece(begin, play, 1, opp0, opp1, empty0, empty1, buf, &count)
        if not captures_only:
            for i in range(1, 16):
                self._gen_piece(begin + i, play, 0, opp0, opp1, empty0, empty1, buf, &count)
            self._gen_piece(begin, play, 0, opp0, opp1, empty0, empty1, buf, &count)
        return count

    cpdef object gen_moves_py(self, int play, int captures_only):
        cdef long long[256] buf
        cdef int n, i
        cdef list out = []
        with nogil:
            n = self._gen_moves(play, buf, captures_only)
        for i in range(n):
            out.append(int(buf[i]))
        return out

    cpdef bench_gen(self, int play, int n):
        cdef long long[256] buf
        cdef int i, c = 0
        with nogil:
            for i in range(n):
                c = self._gen_moves(play, buf, 0)
        return c

    cdef int _in_check(self, int play) noexcept nogil:
        cdef int opp = 1 - play
        cdef int ks = self.all_chess[32 if play == 1 else 16]
        cdef int oks, row, col, rm, cm, role
        cdef long long lo, hi, cnd_lo, cnd_hi
        cdef int i, ksite, key
        if ks < 0:
            return 1
        oks = self.all_chess[32 if opp == 1 else 16]
        if oks < 0:
            return 0
        row = ks // 9
        col = ks % 9
        rm = self.bit_row[row]
        cm = self.bit_col[col]
        role = 6 + 7 * (1 - opp)
        lo = _CH_ATK_R_LO[ks, rm] ^ _CH_ATK_C_LO[ks, cm]
        hi = _CH_ATK_R_HI[ks, rm] ^ _CH_ATK_C_HI[ks, cm]
        if ((lo & self.mask_role[role][0]) | (hi & self.mask_role[role][1])) != 0:
            return 1
        if _has_site(_CH_ATK_C_LO[ks, cm], _CH_ATK_C_HI[ks, cm], oks) != 0:
            return 1
        role = 4 + 7 * (1 - opp)
        lo = _GUN_ATK_R_LO[ks, rm] ^ _GUN_ATK_C_LO[ks, cm]
        hi = _GUN_ATK_R_HI[ks, rm] ^ _GUN_ATK_C_HI[ks, cm]
        if ((lo & self.mask_role[role][0]) | (hi & self.mask_role[role][1])) != 0:
            return 1
        role = 5 + 7 * (1 - opp)
        cnd_lo = _KN_TGT_LO[ks] & self.mask_role[role][0]
        cnd_hi = _KN_TGT_HI[ks] & self.mask_role[role][1]
        if (cnd_lo | cnd_hi) != 0:
            for i in range(2):
                ksite = self.all_chess[(16 if opp == 0 else 32) + 3 + i]
                if ksite < 0:
                    continue
                if _has_site(cnd_lo, cnd_hi, ksite) == 0:
                    continue
                key = _csum_knight(_KN_LEG_LO[ksite] & self.mask_all[0], _KN_LEG_HI[ksite] & self.mask_all[1])
                if _has_site(_KN_ATK_LO[ksite, key], _KN_ATK_HI[ksite, key], ks) != 0:
                    return 1
        role = 1 + 7 * (1 - opp)
        lo = _KCS_LO[ks] & self.mask_role[role][0]
        hi = _KCS_HI[ks] & self.mask_role[role][1]
        return 1 if (lo | hi) != 0 else 0

    cpdef int in_check_py(self, int play):
        cdef int r
        with nogil:
            r = self._in_check(play)
        return r

    cpdef bench_incheck(self, int play, int n):
        cdef int i, s = 0
        with nogil:
            for i in range(n):
                s += self._in_check(play)
        return s


cdef inline void _select_best(long long* buf, int* score, int index, int count) noexcept nogil:
    cdef int best = index, i, tm, ts
    cdef long long tmv
    for i in range(index + 1, count):
        if score[i] > score[best]:
            best = i
    if best != index:
        tmv = buf[index]; buf[index] = buf[best]; buf[best] = tmv
        ts = score[index]; score[index] = score[best]; score[best] = ts


cdef class Searcher:
    cdef:
        BoardState st
        long long* tt_key
        long long* tt_data
        int tt_slots
        int killer[64][2]
        int history[8][256]
        long long z32[68]
        long long z64[68]
        signed char is_eat[68]
        signed char chk[68]
        signed char is_null_[68]
        int pv[68][68]
        long long nodes
        int* stop_ptr
        int owns_stop
        long long movebuf[68][256]
        long long eatbuf[68][256]
        int eatscore[68][256]
        long long genbuf[68][256]
        int genscore[68][256]
        long long goodbuf[68][256]
        int goodscore[68][256]
        long long gbuf[68][256]
        int gscore[68][256]
        long long tmpbuf[68][256]
        long long rootmoves[256]
        int rootscores[256]
        int root_count
        int root_inited
        int owns_tt

    def __cinit__(self, int hash_pow=19):
        cdef int slots = 1 << hash_pow
        self.st = BoardState()
        self.tt_slots = slots
        self.tt_key = <long long*>calloc(4 * slots, sizeof(long long))
        self.tt_data = <long long*>calloc(4 * slots, sizeof(long long))
        self.owns_tt = 1
        self.stop_ptr = <int*>calloc(1, sizeof(int))
        self.owns_stop = 1
        if self.tt_key == NULL or self.tt_data == NULL or self.stop_ptr == NULL:
            raise MemoryError()

    def __dealloc__(self):
        if self.owns_stop == 1:
            if self.stop_ptr != NULL:
                free(self.stop_ptr)
        if self.owns_tt == 1:
            if self.tt_key != NULL:
                free(self.tt_key)
            if self.tt_data != NULL:
                free(self.tt_data)

    cpdef attach_tt(self, Searcher src):
        if self.owns_tt == 1:
            if self.tt_key != NULL:
                free(self.tt_key)
            if self.tt_data != NULL:
                free(self.tt_data)
        self.tt_key = src.tt_key
        self.tt_data = src.tt_data
        self.tt_slots = src.tt_slots
        self.owns_tt = 0

    cpdef attach_stop(self, Searcher src):
        if self.owns_stop == 1 and self.stop_ptr != NULL:
            free(self.stop_ptr)
        self.stop_ptr = src.stop_ptr
        self.owns_stop = 0

    cpdef request_stop(self):
        self.stop_ptr[0] = 1

    cpdef reset_stop(self):
        self.stop_ptr[0] = 0

    cpdef load(self, object st):
        cdef int i, j, n4
        self.st.load_from_state(st)
        for i in range(64):
            self.killer[i][0] = 0
            self.killer[i][1] = 0
        for i in range(8):
            for j in range(256):
                self.history[i][j] = 0
        for i in range(68):
            self.z32[i] = 0
            self.z64[i] = 0
            self.is_eat[i] = 0
            self.chk[i] = 0
            self.is_null_[i] = 0
        if self.owns_tt == 1:
            n4 = 4 * self.tt_slots
            for i in range(n4):
                self.tt_key[i] = 0
                self.tt_data[i] = 0
        self.nodes = 0
        if self.owns_stop == 1:
            self.stop_ptr[0] = 0
        self.root_inited = 0
        self.z32[0] = self.st.zob[0]
        self.z64[0] = self.st.zob[1]

    cdef inline void _write_straight(self, int ki, long long zob64, int etype, int value, int depth, int move) noexcept nogil:
        cdef long long old = self.tt_data[ki]
        cdef int old_move = <int>((old >> 42) & 0x3FFF)
        cdef int m = move if move != 0 else old_move
        self.tt_data[ki] = _pack_tt(etype, value, depth, m)
        self.tt_key[ki] = zob64

    cdef inline int _probe_slot(self, int play, int kind, int slot, int depth, int alpha, int beta, long long* out_move, int* out_value) noexcept nogil:
        cdef int idx = (play * 2 + kind) * self.tt_slots + slot
        cdef long long d = self.tt_data[idx]
        cdef int value = _tt_value(d)
        cdef int edepth = <int>((d >> 34) & 0xFF)
        cdef int etype = <int>((d >> 32) & 3)
        if value > MATE_BOUND:
            value -= depth - edepth
        elif value < -MATE_BOUND:
            value += depth - edepth
        elif edepth < depth:
            return FAIL_SENTINEL
        if etype == HASH_PV:
            return value
        if etype == HASH_BETA and value >= beta:
            return value
        if etype == HASH_ALPHA and value <= alpha:
            return value
        return FAIL_SENTINEL

    cdef inline int _get_tt(self, int play, int zob32, long long zob64, int depth, int alpha, int beta, long long* out_move, int* out_value) noexcept nogil:
        cdef int slot = zob32 & (self.tt_slots - 1)
        cdef int si = (play * 2 + 1) * self.tt_slots + slot
        cdef int ki = (play * 2 + 0) * self.tt_slots + slot
        cdef long long sk, rk
        cdef int v, v2, step_ok = 0
        out_value[0] = 0
        out_move[0] = 0
        sk = self.tt_key[si]
        if sk == zob64 and sk != 0:
            v = self._probe_slot(play, 1, slot, depth, alpha, beta, out_move, out_value)
            # 共享 TT 无锁读复核：条目正被并发覆盖（key 与首读不一致）则视为未命中。
            # 写者把 key 放在最后写，依赖 x86 TSO 的 store-store 顺序。
            if self.tt_key[si] != sk:
                sk = 0
            else:
                if v != FAIL_SENTINEL:
                    out_move[0] = (self.tt_data[si] >> 42) & 0x3FFF
                    return v
                out_move[0] = (self.tt_data[si] >> 42) & 0x3FFF
                out_value[0] = _tt_value(self.tt_data[si])
                step_ok = 1
        rk = self.tt_key[ki]
        if rk == zob64 and rk != 0:
            v2 = self._probe_slot(play, 0, slot, depth, alpha, beta, out_move, out_value)
            if self.tt_key[ki] != rk:
                rk = 0
            else:
                if v2 != FAIL_SENTINEL:
                    out_move[0] = (self.tt_data[ki] >> 42) & 0x3FFF
                    return v2
                out_move[0] = (self.tt_data[ki] >> 42) & 0x3FFF
                if (step_ok == 0) or (((self.tt_data[si] >> 34) & 0xFF) < ((self.tt_data[ki] >> 34) & 0xFF)):
                    out_value[0] = _tt_value(self.tt_data[ki])
        return FAIL_SENTINEL

    cdef inline void _set_tt(self, int play, int zob32, long long zob64, int etype, int value, int depth, int move) noexcept nogil:
        cdef int slot, si, ki
        cdef long long skey
        cdef int sdepth
        if (value >= 8000 and value <= 9000) or (value >= -9000 and value <= -8000):
            return
        if value > MATE_BOUND or value < -MATE_BOUND:
            return
        slot = zob32 & (self.tt_slots - 1)
        si = (play * 2 + 1) * self.tt_slots + slot
        ki = (play * 2 + 0) * self.tt_slots + slot
        skey = self.tt_key[si]
        sdepth = <int>((self.tt_data[si] >> 34) & 0xFF)
        if (skey != 0) or (self.tt_data[si] != 0):
            if (skey != 0) and sdepth > depth:
                self._write_straight(ki, zob64, etype, value, depth, move)
                return
            self.tt_data[ki] = self.tt_data[si]
            self.tt_key[ki] = self.tt_key[si]
        else:
            self._write_straight(ki, zob64, etype, value, depth, move)
        self.tt_data[si] = _pack_tt(etype, value, depth, move)
        self.tt_key[si] = zob64

    cdef inline int _piece_score(self, int piece) noexcept nogil:
        return self.st.base_score[2 + _PIECE_ROLES[piece]]

    cdef inline int _is_long_check(self, int ply) noexcept nogil:
        cdef int t
        if self.chk[ply] == 0:
            return 0
        t = ply - 1
        while t > 0:
            if self.is_null_[t] != 0:
                break
            if self.z32[t] == self.z32[ply] and self.z64[t] == self.z64[ply]:
                return 1
            if self.is_eat[t] != 0:
                return 0
            t -= 1
        return 0

    cdef inline int _is_draw(self) noexcept nogil:
        return 1 if (self.st.attack_def[1][0] == 0 and self.st.attack_def[0][0] == 0) else 0

    cdef inline int _is_danger(self, int play) noexcept nogil:
        cdef int opp = 1 - play
        cdef long long lo = 0, hi = 0
        lo |= self.st.mask_role[6 + 7 * (1 - opp)][0]
        lo |= self.st.mask_role[5 + 7 * (1 - opp)][0]
        lo |= self.st.mask_role[4 + 7 * (1 - opp)][0]
        hi |= self.st.mask_role[6 + 7 * (1 - opp)][1]
        hi |= self.st.mask_role[5 + 7 * (1 - opp)][1]
        hi |= self.st.mask_role[4 + 7 * (1 - opp)][1]
        return 1 if (_popcount64(lo & _DANGER_LO[play]) + _popcount64(hi & _DANGER_HI[play])) >= 3 else 0

    cdef inline void _store_pv(self, int ply, long long move) noexcept nogil:
        cdef int j = 0
        self.pv[ply][0] = <int>move
        while j + 1 < 68 and self.pv[ply + 1][j] != 0:
            self.pv[ply][j + 1] = self.pv[ply + 1][j]
            j += 1
        if j + 1 < 68:
            self.pv[ply][j + 1] = 0

    cdef int _gen_quiesc(self, int ply, int play, int is_checked, int* good_n, int* general_n) noexcept nogil:
        cdef int n, i, src, dest, dest_chess, src_chess, dest_score, src_score
        cdef long long m
        n = self.st._gen_moves(play, self.tmpbuf[ply], 1)
        good_n[0] = 0
        general_n[0] = 0
        for i in range(n):
            m = self.tmpbuf[ply][i]
            src = <int>(m & 127)
            dest = <int>(m >> 7)
            dest_chess = self.st.board[dest]
            dest_score = self._piece_score(dest_chess) + self.st._attach(_PIECE_ROLES[dest_chess], dest)
            src_chess = self.st.board[src]
            if dest_score >= QUIESC_GOOD:
                src_score = self._piece_score(src_chess) + self.st._attach(_PIECE_ROLES[src_chess], src)
                self.goodbuf[ply][good_n[0]] = m
                self.goodscore[ply][good_n[0]] = dest_score - src_score
                good_n[0] += 1
            else:
                self.gbuf[ply][general_n[0]] = m
                self.gscore[ply][general_n[0]] = self.history[_PIECE_KINDS[src_chess]][dest]
                general_n[0] += 1
        if is_checked:
            n = self.st._gen_moves(play, self.tmpbuf[ply], 0)
            for i in range(n):
                m = self.tmpbuf[ply][i]
                dest = <int>(m >> 7)
                if self.st.board[dest] != 0:
                    continue
                src = <int>(m & 127)
                self.gbuf[ply][general_n[0]] = m
                self.gscore[ply][general_n[0]] = self.history[_PIECE_KINDS[self.st.board[src]]][dest]
                general_n[0] += 1
        return 0

    cdef int _quiesc(self, int alpha, int beta, int ply, int play, int is_checked) noexcept nogil:
        cdef int best, is_move, i, v, good_n, general_n, dc, pl
        cdef long long m, best_move
        if self.st.all_chess[32 if play == 1 else 16] < 0:
            return -(MAX_SCORE - ply)
        self.chk[ply] = 1 if is_checked else 0
        if self._is_long_check(ply):
            return LONG_CHECK_SCORE
        if self._is_draw():
            return DRAW_SCORE
        if ply >= MAX_PLY:
            self.nodes += 1
            return self.st._evaluate(play)
        best = -MAX_SCORE - 2
        is_move = 0
        best_move = 0
        if is_checked == 0:
            is_move = 1
            self.nodes += 1
            v = self.st._evaluate(play)
            if v > best:
                if v >= beta:
                    return v
                best = v
                if v > alpha:
                    alpha = v
        self._gen_quiesc(ply, play, is_checked, &good_n, &general_n)
        i = 0
        while i < good_n:
            _select_best(self.goodbuf[ply], self.goodscore[ply], i, good_n)
            m = self.goodbuf[ply][i]
            i += 1
            self.st.make(m, &dc, &pl)
            if self.st._in_check(play):
                self.st.unmake(m, dc, pl)
                continue
            self.z32[ply + 1] = self.st.zob[0]
            self.z64[ply + 1] = self.st.zob[1]
            self.is_eat[ply + 1] = 1
            self.pv[ply + 1][0] = 0
            v = -self._quiesc(-beta, -alpha, ply + 1, 1 - play, self.st._in_check(1 - play))
            self.st.unmake(m, dc, pl)
            is_move = 1
            if v > best:
                best = v
                best_move = m
                self._store_pv(ply, best_move)
                if v > alpha:
                    alpha = v
                if v >= beta:
                    return best
        if is_checked:
            i = 0
            while i < general_n:
                _select_best(self.gbuf[ply], self.gscore[ply], i, general_n)
                m = self.gbuf[ply][i]
                i += 1
                self.st.make(m, &dc, &pl)
                if self.st._in_check(play):
                    self.st.unmake(m, dc, pl)
                    continue
                self.z32[ply + 1] = self.st.zob[0]
                self.z64[ply + 1] = self.st.zob[1]
                self.is_eat[ply + 1] = 1 if self.st.board[<int>(m >> 7)] != 0 else 0
                self.pv[ply + 1][0] = 0
                v = -self._quiesc(-beta, -alpha, ply + 1, 1 - play, self.st._in_check(1 - play))
                self.st.unmake(m, dc, pl)
                is_move = 1
                if v > best:
                    best = v
                    best_move = m
                    self._store_pv(ply, best_move)
                    if v > alpha:
                        alpha = v
                    if v >= beta:
                        return best
        if is_move:
            return best
        return -(MAX_SCORE - ply)

    cdef void _opp_attack(self, int play, long long* olo, long long* ohi) noexcept nogil:
        cdef int opp = 1 - play
        cdef int begin = 16 if opp == 0 else 32
        cdef int i, piece, src, role, br, rm, cm, key
        cdef long long lo = 0, hi = 0
        for i in range(16):
            piece = begin + i
            src = self.st.all_chess[piece]
            if src < 0:
                continue
            role = _PIECE_ROLES[piece]
            br = role % 7
            if br == 6:
                rm = self.st.bit_row[src // 9]
                cm = self.st.bit_col[src % 9]
                lo |= (_CH_ATK_R_LO[src, rm] ^ _CH_ATK_C_LO[src, cm]) | (_MV_R_LO[src, rm] ^ _MV_C_LO[src, cm])
                hi |= (_CH_ATK_R_HI[src, rm] ^ _CH_ATK_C_HI[src, cm]) | (_MV_R_HI[src, rm] ^ _MV_C_HI[src, cm])
            elif br == 4:
                rm = self.st.bit_row[src // 9]
                cm = self.st.bit_col[src % 9]
                lo |= (_GUN_ATK_R_LO[src, rm] ^ _GUN_ATK_C_LO[src, cm]) | (_GUN_FK_R_LO[src, rm] ^ _GUN_FK_C_LO[src, cm])
                hi |= (_GUN_ATK_R_HI[src, rm] ^ _GUN_ATK_C_HI[src, cm]) | (_GUN_FK_R_HI[src, rm] ^ _GUN_FK_C_HI[src, cm])
            elif br == 5:
                key = _csum_knight(_KN_LEG_LO[src] & self.st.mask_all[0], _KN_LEG_HI[src] & self.st.mask_all[1])
                lo |= _KN_ATK_LO[src, key]
                hi |= _KN_ATK_HI[src, key]
            elif br == 3:
                key = _csum_elephant(_EL_LEG_LO[src] & self.st.mask_all[0], _EL_LEG_HI[src] & self.st.mask_all[1])
                lo |= _EL_ATK_LO[src, key]
                hi |= _EL_ATK_HI[src, key]
            elif br == 0:
                lo |= _KING_LO[src]
                hi |= _KING_HI[src]
            elif br == 2:
                lo |= _GUARD_LO[src]
                hi |= _GUARD_HI[src]
            else:
                lo |= _SOL_LO[opp, src]
                hi |= _SOL_HI[opp, src]
        olo[0] = lo
        ohi[0] = hi

    cdef inline int _legal(self, int play, long long m) noexcept nogil:
        cdef int src = <int>(m & 127)
        cdef int dest = <int>(m >> 7)
        cdef int src_chess, dest_chess, role
        cdef long long lo, hi
        if src < 0 or src >= 90 or dest < 0 or dest >= 90 or src == dest:
            return 0
        src_chess = self.st.board[src]
        if src_chess == 0 or ((16 if play == 0 else 32) & src_chess) == 0:
            return 0
        dest_chess = self.st.board[dest]
        if dest_chess != 0 and ((16 if play == 0 else 32) & dest_chess) != 0:
            return 0
        role = _PIECE_ROLES[src_chess]
        self.st._target_mask(role, src, 1 if dest_chess != 0 else 0, play, &lo, &hi)
        return _has_site(lo, hi, dest)

    cdef inline void _history_bonus(self, int piece, int dest, int depth) noexcept nogil:
        self.history[_PIECE_KINDS[piece]][dest] += (2 << (depth & 31))

    cdef int _nega(self, int alpha, int beta, int depth, int ply, int play, int is_pv, int is_null) noexcept nogil:
        cdef int best_value, is_checked, entry_type, this_alpha, moves_searched, moves_count
        cdef int hit, tt_value, kd, i, j, phase, idx, n_total, m_is_eat
        cdef int eat_n, gen_n, kk, v, d_idx, k_idx
        cdef int k0, k1, head_n, is_move, opp_lo_v, opp_hi_v, skip
        cdef long long tt_move, m, best_move, head[3], opp_lo, opp_hi
        cdef int pl, dc, attack_num, null_r, src, dest, src_chess, dest_chess
        cdef int is_opp_protect, src_score, dest_score
        cdef long long val
        cdef int seen[3]
        cdef int seen_n
        play = play
        if self.st.all_chess[32 if play == 1 else 16] < 0:
            return ply - MAX_SCORE
        best_value = ply - MAX_SCORE
        if best_value > beta:
            return best_value
        if self.stop_ptr[0] != 0:
            return best_value
        if ply >= MAX_PLY:
            self.nodes += 1
            return self.st._evaluate(play)
        hit = self._get_tt(play, <int>self.st.zob[0], self.st.zob[1], depth, alpha, beta, &tt_move, &tt_value)
        if hit != FAIL_SENTINEL:
            return hit
        is_checked = self.st._in_check(play)
        self.chk[ply] = 1 if is_checked else 0
        self.is_null_[ply] = 1 if is_null != 0 else 0
        if self._is_long_check(ply):
            return LONG_CHECK_SCORE
        if is_null == 0 and self.is_eat[ply] != 0 and self._is_draw():
            return DRAW_SCORE
        if is_checked:
            depth += 1
        entry_type = HASH_ALPHA
        if depth <= 0:
            return self._quiesc(alpha, beta, ply, play, is_checked)
        if is_null == 0 and is_checked == 0 and is_pv == 0 and depth >= 2:
            null_r = _radapt(depth)
            attack_num = self.st.attack_def[play][0]
            if attack_num > 0:
                self.z32[ply + 1] = self.st.zob[0]
                self.z64[ply + 1] = self.st.zob[1]
                self.is_eat[ply + 1] = 0
                self.is_null_[ply + 1] = 1
                self.pv[ply + 1][0] = 0
                val = -self._nega(-beta, -beta + 1, depth - null_r - 1, ply + 1, 1 - play, 0, 1)
                if val >= beta:
                    if attack_num > 2 and depth < 6:
                        return <int>val
                    val = -self._nega(-beta, -beta + 1, depth - null_r + 1, ply + 1, 1 - play, 0, 1)
                    if val >= beta:
                        return <int>val
        if depth >= 6 and is_pv != 0 and tt_move == 0:
            self._nega(alpha, beta, depth - 2, ply, play, is_pv, is_null)
            if self.pv[ply][0] != 0:
                tt_move = self.pv[ply][0]
        kd = depth if depth < 64 else 63
        k0 = self.killer[kd][0]
        k1 = self.killer[kd][1]
        head_n = 0
        seen_n = 0
        if tt_move != 0 and self._legal(play, tt_move):
            head[head_n] = tt_move
            head_n += 1
            seen[seen_n] = <int>tt_move
            seen_n += 1
        if k0 != 0 and k0 != tt_move and self._legal(play, k0):
            head[head_n] = k0
            head_n += 1
            seen[seen_n] = k0
            seen_n += 1
        if k1 != 0 and k1 != tt_move and k1 != k0 and self._legal(play, k1):
            head[head_n] = k1
            head_n += 1
            seen[seen_n] = k1
            seen_n += 1
        self._opp_attack(play, &opp_lo, &opp_hi)
        n_total = self.st._gen_moves(play, self.movebuf[ply], 0)
        eat_n = 0
        gen_n = 0
        for phase in range(2):
            for idx in range(n_total):
                m = self.movebuf[ply][idx]
                dest = <int>(m >> 7)
                src = <int>(m & 127)
                src_chess = self.st.board[src]
                dest_chess = self.st.board[dest]
                m_is_eat = 1 if dest_chess != 0 else 0
                if (1 if phase == 0 else 0) != m_is_eat:
                    continue
                skip = 0
                for j in range(seen_n):
                    if seen[j] == m:
                        skip = 1
                        break
                if skip:
                    continue
                is_opp_protect = _has_site(opp_lo, opp_hi, dest)
                if m_is_eat:
                    if is_opp_protect:
                        src_score = self._piece_score(src_chess) + self.st._attach(_PIECE_ROLES[src_chess], src)
                    else:
                        src_score = -500
                    dest_score = self._piece_score(dest_chess) + self.st._attach(_PIECE_ROLES[dest_chess], dest)
                    if dest_score >= src_score:
                        self.eatbuf[ply][eat_n] = m
                        self.eatscore[ply][eat_n] = dest_score - src_score
                        eat_n += 1
                        continue
                self.genbuf[ply][gen_n] = m
                self.genscore[ply][gen_n] = self.history[_PIECE_KINDS[src_chess]][dest] + (0 if is_opp_protect else 256)
                gen_n += 1
        is_move = 0
        this_alpha = alpha
        best_move = 0
        moves_searched = 0
        moves_count = 10 if is_pv != 0 else 5
        for phase in range(3):
            if phase == 0:
                n_total = head_n
            elif phase == 1:
                n_total = eat_n
            else:
                n_total = gen_n
            j = 0
            while j < n_total:
                if phase == 0:
                    m = head[j]
                elif phase == 1:
                    _select_best(self.eatbuf[ply], self.eatscore[ply], j, eat_n)
                    m = self.eatbuf[ply][j]
                else:
                    _select_best(self.genbuf[ply], self.genscore[ply], j, gen_n)
                    m = self.genbuf[ply][j]
                j += 1
                self.st.make(m, &dc, &pl)
                if self.st._in_check(play):
                    self.st.unmake(m, dc, pl)
                    continue
                if (is_checked == 0) and is_pv == 0 and depth < 6 and (self._is_danger(play) == 0) and moves_searched >= moves_count:
                    d_idx = depth if depth < 64 else 63
                    k_idx = moves_searched if moves_searched < 64 else 63
                    if _futility(d_idx, k_idx) + (self.st.base_score[play] - self.st.base_score[1 - play]) < this_alpha:
                        self.st.unmake(m, dc, pl)
                        moves_searched += 1
                        continue
                self.z32[ply + 1] = self.st.zob[0]
                self.z64[ply + 1] = self.st.zob[1]
                self.is_eat[ply + 1] = 1 if self.st.board[<int>(m >> 7)] != 0 else 0
                self.is_null_[ply + 1] = 0
                self.pv[ply + 1][0] = 0
                if is_move:
                    kk = 2
                    if is_checked == 0 and depth >= 3 and moves_searched >= moves_count:
                        if self._is_danger(1 - play) == 0:
                            if moves_searched >= (moves_count + (5 + depth)) * 2:
                                kk = 4
                            elif moves_searched >= moves_count + 5 + depth:
                                kk = 3
                        v = -self._nega(-this_alpha - 1, -this_alpha, depth - kk, ply + 1, 1 - play, 0, 0)
                    else:
                        v = this_alpha + 1
                    if v > this_alpha:
                        if kk > 1:
                            v = -self._nega(-this_alpha - 1, -this_alpha, depth - 1, ply + 1, 1 - play, 0, 0)
                        if v > this_alpha:
                            v = -self._nega(-beta, -this_alpha, depth - 1, ply + 1, 1 - play, 1, 0)
                else:
                    v = -self._nega(-beta, -this_alpha, depth - 1, ply + 1, 1 - play, 1, 0)
                    is_move = 1
                self.st.unmake(m, dc, pl)
                moves_searched += 1
                if v > best_value:
                    best_value = v
                    best_move = m
                    self._store_pv(ply, m)
                    if v >= beta:
                        if is_null == 0 and m != k0 and m != k1:
                            self.killer[kd][1] = self.killer[kd][0]
                            self.killer[kd][0] = <int>m
                        entry_type = HASH_BETA
                        break
                    if v > this_alpha:
                        this_alpha = v
                        entry_type = HASH_PV
            if entry_type == HASH_BETA:
                break
        if is_move:
            if entry_type != HASH_ALPHA and best_move != 0:
                self._history_bonus(self.st.board[<int>(best_move & 127)], <int>(best_move >> 7), depth)
            self._set_tt(play, <int>self.st.zob[0], self.st.zob[1], entry_type, best_value, depth, <int>best_move)
            return best_value
        return best_value

    cdef int _init_root(self, int depth) noexcept nogil:
        cdef int play = self.st.side_to_move
        cdef int kd = depth if depth < 64 else 63
        cdef int count = 0, init_score = 100, i, n, h, phase, skip, is_eat, pl, dc
        cdef long long m, k0, k1, head[3]
        cdef int head_n = 0
        k0 = self.killer[kd][0]
        k1 = self.killer[kd][1]
        if k0 != 0 and self._legal(play, k0):
            head[head_n] = k0
            head_n += 1
        if k1 != 0 and k1 != k0 and self._legal(play, k1):
            head[head_n] = k1
            head_n += 1
        for h in range(head_n):
            m = head[h]
            self.st.make(m, &dc, &pl)
            if self.st._in_check(play) == 0 and count < 256:
                self.rootmoves[count] = m
                self.rootscores[count] = init_score
                count += 1
                init_score -= 1
            self.st.unmake(m, dc, pl)
        n = self.st._gen_moves(play, self.movebuf[0], 0)
        for phase in range(2):
            for i in range(n):
                m = self.movebuf[0][i]
                is_eat = 1 if self.st.board[<int>(m >> 7)] != 0 else 0
                if (1 if phase == 0 else 0) != is_eat:
                    continue
                skip = 0
                for h in range(head_n):
                    if head[h] == m:
                        skip = 1
                        break
                if skip:
                    continue
                self.st.make(m, &dc, &pl)
                if self.st._in_check(play) == 0 and count < 256:
                    self.rootmoves[count] = m
                    self.rootscores[count] = init_score
                    count += 1
                    init_score -= 1
                self.st.unmake(m, dc, pl)
        self.root_count = count
        self.root_inited = 1
        return count

    cdef int _root_nega(self, int alpha, int beta, int depth) noexcept nogil:
        cdef int play = self.st.side_to_move
        cdef int count = self.root_count
        cdef int this_alpha = alpha, best_value = -MAX_SCORE - 2, is_move = 0
        cdef int i = 0, pl, dc, v
        cdef long long m
        self.chk[0] = 1 if self.st._in_check(play) else 0
        while i < count:
            _select_best(self.rootmoves, self.rootscores, i, count)
            m = self.rootmoves[i]
            i += 1
            self.st.make(m, &dc, &pl)
            self.z32[1] = self.st.zob[0]
            self.z64[1] = self.st.zob[1]
            self.is_eat[1] = 1 if self.st.board[<int>(m >> 7)] != 0 else 0
            self.is_null_[1] = 0
            self.pv[1][0] = 0
            if is_move:
                v = -self._nega(-this_alpha - 1, -this_alpha, depth - 1, 1, 1 - play, 0, 0)
                if v > this_alpha:
                    v = -self._nega(-beta, -this_alpha, depth - 1, 1, 1 - play, 1, 0)
            else:
                v = -self._nega(-beta, -this_alpha, depth - 1, 1, 1 - play, 1, 0)
                is_move = 1
            self.st.unmake(m, dc, pl)
            self.rootscores[i - 1] = v
            if v > best_value:
                best_value = v
                if v > this_alpha:
                    this_alpha = v
                self._store_pv(0, m)
            if self.stop_ptr[0] != 0:
                break
        if is_move:
            return best_value
        return -(MAX_SCORE - 0)

    cpdef int search_depth(self, int depth):
        cdef int score
        cdef int k, j
        with nogil:
            if self.root_inited == 0:
                self._init_root(depth)
            self.pv[0][0] = 0
            score = self._root_nega(-MAX_SCORE, MAX_SCORE, depth)
            k = depth + 1
            j = 0
            while j < 68 and k >= 0 and k < 64 and self.pv[0][j] != 0:
                self.killer[k][1] = self.killer[k][0]
                self.killer[k][0] = self.pv[0][j]
                j += 1
                k -= 1
        return score

    cpdef object search_to(self, int max_depth):
        cdef int d, score = 0
        with nogil:
            self.root_inited = 0
            for d in range(4, max_depth + 1):
                if self.stop_ptr[0] != 0:
                    break
                if self.root_inited == 0:
                    self._init_root(d)
                self.pv[0][0] = 0
                score = self._root_nega(-MAX_SCORE, MAX_SCORE, d)
        return (score, self.nodes)

    cpdef int dbg(self, int stage, int d):
        cdef int r = 0
        with nogil:
            if stage == 0:
                r = self._init_root(d)
            elif stage == 1:
                r = self._root_nega(-MAX_SCORE, MAX_SCORE, d)
            elif stage == 2:
                r = self._nega(-MAX_SCORE, MAX_SCORE, d, 1, self.st.side_to_move, 1, 0)
        return r

    cpdef object search_layer(self, int depth):
        cdef int score, k, j
        cdef int mate = 0
        with nogil:
            if self.root_inited == 0:
                self._init_root(depth)
            self.pv[0][0] = 0
            score = self._root_nega(-MAX_SCORE, MAX_SCORE, depth)
            k = depth + 1
            j = 0
            while j < 68 and k >= 0 and k < 64 and self.pv[0][j] != 0:
                self.killer[k][1] = self.killer[k][0]
                self.killer[k][0] = self.pv[0][j]
                j += 1
                k -= 1
        if score > MATE_BOUND:
            mate = MAX_SCORE - score
        elif score < -MATE_BOUND:
            mate = -(MAX_SCORE + score)
        return (score, mate)

    cpdef object get_pv(self, int limit):
        cdef int i
        cdef list out = []
        for i in range(68):
            if self.pv[0][i] == 0 or len(out) >= limit:
                break
            out.append(<long long>self.pv[0][i])
        return out

    cpdef long long get_nodes(self):
        return self.nodes

    cpdef int get_side(self):
        return self.st.side_to_move

    cpdef int is_stopped(self):
        return self.stop_ptr[0]

    cpdef object get_ranked(self):
        cdef int i
        cdef list out = []
        for i in range(self.root_count):
            out.append((<long long>self.rootmoves[i], <int>self.rootscores[i]))
        return out
