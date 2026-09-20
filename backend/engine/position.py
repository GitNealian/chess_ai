"""局面状态（State）、伪着法委托与 make/unmake 增量维护。

Java 参考：
- `Tools.parseFEN`（L59-105）：棋子索引按 FEN 字符扫描顺序分配；
- `ChessParam`：board/allChess/位图/剩余计数/攻击防御计数/三方掩码；
- `ChessMoveAbs.genEatMoveList/genNopMoveList`（L452-481）与
  `chessEatMove/chessNopMove`（L574-704）：查表生成伪着法，
  具体实现见 `movegen.py`（`pseudo_moves` 委托其 `gen_moves`）；
- `ChessMoveAbs.moveOperate/unMoveOperate`（L82-178）与
  `TranspositionTable.moveOperate/unMoveOperate`：baseScore、位图、掩码与
  Zobrist 的增量维护。

约定（与 Java 一致）：
- board 空位为 0，allChess 空位为 -1；
- 红方角色 1-7、黑方 8-14；棋子索引 16-31 黑、32-47 红；
- bit_row 的 bit(8-col)、bit_col 的 bit(9-row)；
- mask_* 一律打包成 [lo, hi] 两个 int64，site 0-63 在 lo、64-89 在 hi。
"""

import collections

import numpy as np
from numba import njit

from . import bitboard
from . import constants as C
from . import eval_tables as _eval_tables
from . import zobrist as _zobrist
from .zobrist import ZOB32, ZOB64

__all__ = [
    "State",
    "attach_score",
    "full_base_score",
    "full_zobrist",
    "load_position",
    "make_move",
    "move_is_capture",
    "pseudo_moves",
    "unmake_move",
]

State = collections.namedtuple(
    "State",
    "board all_chess bit_row bit_col remain attack_def mask_all mask_personal mask_role base_score zob side_to_move",
)

# Java Tools.parseFEN 的起始索引表：按字符扫描顺序"取当前值再自增"。
_FEN_PIECE_STARTS = {
    "k": 16,
    "r": 17,
    "n": 19,
    "b": 23,
    "a": 25,
    "c": 21,
    "p": 27,
    "K": 32,
    "R": 33,
    "N": 35,
    "B": 39,
    "A": 41,
    "C": 37,
    "P": 43,
}


def _parse_board_layout(layout):
    """按 Java Tools.parseFEN 语义把 FEN 棋盘段扫成 board[90]（site→棋子索引）。

    首行对应 site 0..8（90 坐标 row0），逐行递增；数字跳过对应格数，'/' 不占格。
    """
    board = np.zeros(90, dtype=np.int8)
    next_index = dict(_FEN_PIECE_STARTS)
    site = 0
    for ch in layout:
        if "a" <= ch <= "z" or "A" <= ch <= "Z":
            index = next_index[ch]
            next_index[ch] = index + 1
            board[site] = index
            site += 1
        elif "0" <= ch <= "9":
            site += int(ch)
    if site != 90:
        raise ValueError(f"FEN 棋盘段共占 {site} 格，应为 90")
    return board


def load_position(fen):
    """解析 FEN，构建并返回完全初始化的 State。

    base_score 初始化为与 full_base_score 一致的全量值（Java parseFEN 语义）。
    """
    parts = fen.split()
    if not parts:
        raise ValueError("FEN 不能为空")
    board = _parse_board_layout(parts[0])

    all_chess = np.full(48, C.NOTHING, dtype=np.int8)
    bit_row = np.zeros(10, dtype=np.int16)
    bit_col = np.zeros(9, dtype=np.int16)
    remain = np.zeros(15, dtype=np.int8)
    attack_def = np.zeros((2, 2), dtype=np.int8)
    mask_all = np.zeros(2, dtype=np.int64)
    mask_personal = np.zeros((2, 2), dtype=np.int64)
    mask_role = np.zeros((15, 2), dtype=np.int64)

    for site in range(90):
        piece = int(board[site])
        if piece == 0:
            continue
        role = int(C.PIECE_ROLES[piece])
        play = C.BLACK if piece < C.RED_PIECES_START else C.RED
        row, col = divmod(site, 9)
        all_chess[piece] = site
        bit_row[row] |= 1 << (8 - col)
        bit_col[col] |= 1 << (9 - row)
        remain[role] += 1
        attack_def[play][int(C.ATTACK_DEFENSE_INDEX[role])] += 1
        lo, hi = bitboard.site_mask(site)
        mask_all[0] |= lo
        mask_all[1] |= hi
        mask_personal[play, 0] |= lo
        mask_personal[play, 1] |= hi
        mask_role[role, 0] |= lo
        mask_role[role, 1] |= hi

    z32, z64 = _zobrist.full_zobrist(board)
    side_to_move = C.BLACK if len(parts) > 1 and parts[1] == "b" else C.RED
    st = State(
        board=board,
        all_chess=all_chess,
        bit_row=bit_row,
        bit_col=bit_col,
        remain=remain,
        attack_def=attack_def,
        mask_all=mask_all,
        mask_personal=mask_personal,
        mask_role=mask_role,
        base_score=np.zeros(2, dtype=np.int32),
        zob=np.array([z32, z64], dtype=np.int64),
        side_to_move=np.array([side_to_move], dtype=np.int8),
    )
    # 与 Java Tools.parseFEN 一致：baseScore 在解析时即初始化为"子力 + 位置"分。
    # 位置分来自 eval_tables 的中局表（Task 7），与 Java SearchEngine 构造
    # 函数 getChessBaseScore 的全量重算语义相同。
    st.base_score[C.RED], st.base_score[C.BLACK] = full_base_score(st)
    return st


@njit(cache=True)
def attach_score(role, site):
    """棋子位置价值分（中局位置表，Task 7）。

    对应 Java `EvaluateComputeMiddleGame.chessAttachScore`；role 1-7 红方、
    8-14 黑方，红表 = 黑表行镜像。搜索阶段的残局切换由 Task 8 处理。
    """
    if role <= 7:
        return _eval_tables.MIDDLE_RED[role - 1, site]
    return _eval_tables.MIDDLE_BLACK[role - 8, site]


def full_base_score(st):
    """按当前棋盘重算双方 base_score（子力分 + attach_score），返回 (red, black)。"""
    red = 0
    black = 0
    for site in range(90):
        piece = int(st.board[site])
        if piece == 0:
            continue
        role = int(C.PIECE_ROLES[piece])
        value = int(C.PIECE_SCORES[role]) + int(attach_score(role, site))
        if piece < C.RED_PIECES_START:
            black += value
        else:
            red += value
    return red, black


def full_zobrist(st):
    """State 版全量 Zobrist 重算，返回 (zob32, zob64)。"""
    return _zobrist.full_zobrist(st.board)


def pseudo_moves(st, play):
    """生成 play 方全部伪合法着法（查预生成表；不排序、不过滤自将）。

    委托给 `movegen.gen_moves`（两阶段顺序与 Java 一致）；返回 Python list
    以保持既有调用方的向后兼容。
    """
    from . import movegen

    buf, count = movegen.gen_moves(st, play)
    return [int(m) for m in buf[:count]]


@njit(cache=True)
def move_is_capture(st, m):
    """目标格有棋子即为吃子（与 Java destChess != NOTHING 等价）。"""
    return st.board[C.move_dest(m)] != 0


@njit(cache=True)
def make_move(st, m):
    """走子并增量维护全部派生状态，返回 undo 元组 (被吃子索引, 走子方)。

    增量顺序与 Java ChessMoveAbs.moveOperate / TranspositionTable.moveOperate
    一致；调用方保证 m 的源格有棋子（伪合法着法即可）。
    """
    src = C.move_src(m)
    dest = C.move_dest(m)
    board = st.board
    chess = board[src]
    role = C.PIECE_ROLES[chess]
    play = C.BLACK if chess < C.RED_PIECES_START else C.RED
    dest_chess = board[dest]
    dest_role = np.int8(0)
    if dest_chess != 0:
        dest_role = C.PIECE_ROLES[dest_chess]

    lo_src, hi_src = bitboard.site_mask(src)
    lo_dest, hi_dest = bitboard.site_mask(dest)

    # 分数增量（Java L86-98）
    st.base_score[play] -= attach_score(role, src)
    st.base_score[play] += attach_score(role, dest)
    if dest_chess != 0:
        dest_play = 1 - play
        st.base_score[dest_play] -= C.PIECE_SCORES[dest_role]
        st.base_score[dest_play] -= attach_score(dest_role, dest)

    # 掩码（Java L87-98）
    st.mask_all[0] ^= lo_src
    st.mask_all[1] ^= hi_src
    st.mask_all[0] |= lo_dest
    st.mask_all[1] |= hi_dest
    st.mask_personal[play, 0] ^= lo_src
    st.mask_personal[play, 1] ^= hi_src
    st.mask_personal[play, 0] ^= lo_dest
    st.mask_personal[play, 1] ^= hi_dest
    st.mask_role[role, 0] ^= lo_src
    st.mask_role[role, 1] ^= hi_src
    st.mask_role[role, 0] ^= lo_dest
    st.mask_role[role, 1] ^= hi_dest
    if dest_chess != 0:
        st.mask_personal[1 - play, 0] ^= lo_dest
        st.mask_personal[1 - play, 1] ^= hi_dest
        st.mask_role[dest_role, 0] ^= lo_dest
        st.mask_role[dest_role, 1] ^= hi_dest
        st.remain[dest_role] -= 1
        st.attack_def[1 - play, C.ATTACK_DEFENSE_INDEX[dest_role]] -= 1
        st.all_chess[dest_chess] = C.NOTHING

    board[src] = 0
    board[dest] = chess
    st.all_chess[chess] = dest

    # 行列位图（Java L122-133）
    src_row = src // 9
    src_col = src % 9
    dest_row = dest // 9
    dest_col = dest % 9
    st.bit_row[dest_row] |= np.int16(1 << (8 - dest_col))
    st.bit_col[dest_col] |= np.int16(1 << (9 - dest_row))
    st.bit_row[src_row] ^= np.int16(1 << (8 - src_col))
    st.bit_col[src_col] ^= np.int16(1 << (9 - src_row))

    # Zobrist 增量（Java TranspositionTable L135-151）
    st.zob[0] ^= ZOB32[src, role]
    st.zob[0] ^= ZOB32[dest, role]
    st.zob[1] ^= ZOB64[src, role]
    st.zob[1] ^= ZOB64[dest, role]
    if dest_chess != 0:
        st.zob[0] ^= ZOB32[dest, dest_role]
        st.zob[1] ^= ZOB64[dest, dest_role]

    st.side_to_move[0] = np.int8(1 - st.side_to_move[0])
    return np.int8(dest_chess), np.int8(play)


@njit(cache=True)
def unmake_move(st, m, undo):
    """撤销 make_move：按 undo 恢复被吃子，其余全部为增量逆操作。"""
    dest_chess = undo[0]
    play = undo[1]
    src = C.move_src(m)
    dest = C.move_dest(m)
    board = st.board
    chess = board[dest]
    role = C.PIECE_ROLES[chess]
    dest_role = np.int8(0)
    if dest_chess != 0:
        dest_role = C.PIECE_ROLES[dest_chess]

    lo_src, hi_src = bitboard.site_mask(src)
    lo_dest, hi_dest = bitboard.site_mask(dest)

    # 分数还原
    st.base_score[play] -= attach_score(role, dest)
    st.base_score[play] += attach_score(role, src)
    if dest_chess != 0:
        st.base_score[1 - play] += C.PIECE_SCORES[dest_role]
        st.base_score[1 - play] += attach_score(dest_role, dest)

    # 掩码还原：走子方由目标格迁回源格
    st.mask_personal[play, 0] ^= lo_dest
    st.mask_personal[play, 1] ^= hi_dest
    st.mask_personal[play, 0] ^= lo_src
    st.mask_personal[play, 1] ^= hi_src
    st.mask_role[role, 0] ^= lo_dest
    st.mask_role[role, 1] ^= hi_dest
    st.mask_role[role, 0] ^= lo_src
    st.mask_role[role, 1] ^= hi_src
    st.mask_all[0] ^= lo_src
    st.mask_all[1] ^= hi_src
    if dest_chess == 0:
        st.mask_all[0] ^= lo_dest
        st.mask_all[1] ^= hi_dest
    else:
        st.mask_personal[1 - play, 0] ^= lo_dest
        st.mask_personal[1 - play, 1] ^= hi_dest
        st.mask_role[dest_role, 0] ^= lo_dest
        st.mask_role[dest_role, 1] ^= hi_dest
        st.remain[dest_role] += 1
        st.attack_def[1 - play, C.ATTACK_DEFENSE_INDEX[dest_role]] += 1
        st.all_chess[dest_chess] = dest

    board[dest] = dest_chess
    board[src] = chess
    st.all_chess[chess] = src

    src_row = src // 9
    src_col = src % 9
    dest_row = dest // 9
    dest_col = dest % 9
    # Java unMoveOperate：源格无条件 |（棋子回位）；目标格在无吃子时 ^= 清除，
    # 有吃子时保持置位（被吃子已归还）。
    st.bit_row[src_row] |= np.int16(1 << (8 - src_col))
    st.bit_col[src_col] |= np.int16(1 << (9 - src_row))
    if dest_chess == 0:
        st.bit_row[dest_row] ^= np.int16(1 << (8 - dest_col))
        st.bit_col[dest_col] ^= np.int16(1 << (9 - dest_row))

    st.zob[0] ^= ZOB32[src, role]
    st.zob[0] ^= ZOB32[dest, role]
    st.zob[1] ^= ZOB64[src, role]
    st.zob[1] ^= ZOB64[dest, role]
    if dest_chess != 0:
        st.zob[0] ^= ZOB32[dest, dest_role]
        st.zob[1] ^= ZOB64[dest, dest_role]

    st.side_to_move[0] = np.int8(1 - st.side_to_move[0])
