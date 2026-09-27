# cython: language_level=3, boundscheck=False, wraparound=False, cdivision=True, initializedcheck=False, nonecheck=False
"""Cython 核心 MVP 探针：BoardState + make/unmake。

阶段 1 验收：make+unmake <= 0.06µs（当前 numba 0.13µs，Java 0.027µs）。
表由 Python 侧经 init_tables 注入（只读 memoryview）。
"""
import numpy as np
cimport numpy as cnp
from libc.stdint cimport int64_t, int32_t, int8_t, int16_t

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


cpdef init_eval_tables(dict t):
    global _CH_ATK_R_LO, _CH_ATK_R_HI, _CH_ATK_C_LO, _CH_ATK_C_HI
    global _MV_R_LO, _MV_R_HI, _MV_C_LO, _MV_C_HI
    global _GUN_ATK_R_LO, _GUN_ATK_R_HI, _GUN_ATK_C_LO, _GUN_ATK_C_HI
    global _GUN_FK_R_LO, _GUN_FK_R_HI, _GUN_FK_C_LO, _GUN_FK_C_HI
    global _GUN_MR_R_LO, _GUN_MR_R_HI, _GUN_MR_C_LO, _GUN_MR_C_HI
    global _KN_LEG_LO, _KN_LEG_HI, _KN_ATK_LO, _KN_ATK_HI
    global _EL_LEG_LO, _EL_LEG_HI, _EL_ATK_LO, _EL_ATK_HI
    global _KING_LO, _KING_HI, _GUARD_LO, _GUARD_HI, _SOL_LO, _SOL_HI, _KCS_LO, _KCS_HI
    global _KN_TGT_LO, _KN_TGT_HI
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
