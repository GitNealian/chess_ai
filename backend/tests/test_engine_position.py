"""Task 5：Zobrist、局面状态与 make/unmake 的测试。"""

import numpy as np

from chess_engine.board import INITIAL_FEN
from engine import bitboard as B
from engine import constants as C
from engine import position as P
from engine import zobrist as Z


def test_load_initial_position_layout():
    st = P.load_position(INITIAL_FEN)
    assert st.board[C.xy_to_site(0, 0)] == 33      # 红方左车
    assert st.board[C.xy_to_site(8, 0)] == 34
    assert st.board[C.xy_to_site(4, 9)] == 16      # 黑将
    assert st.board[C.xy_to_site(4, 0)] == 32      # 红帅
    assert st.board[C.xy_to_site(0, 6)] == 27      # 黑方左卒
    assert st.board[C.xy_to_site(0, 3)] == 43      # 红方左兵
    assert int(st.side_to_move[0]) == C.RED
    assert int(st.remain[C.RED_CHARIOT]) == 2
    assert int(st.remain[C.BLACK_SOLDIER]) == 5
    assert int(st.attack_def[C.RED][0]) == 11      # 红: 车2+马2+炮2+兵5
    assert int(st.attack_def[C.RED][1]) == 5       # 红: 仕2+相2+帅1
    # 掩码与 board 的非空格完全一致
    occupied = (int(st.mask_all[0]) & B.LO_MASK) | (
        (int(st.mask_all[1]) & B.LO_MASK) << 64
    )
    expected = 0
    for site in range(90):
        if st.board[site] != 0:
            expected |= 1 << site
    assert occupied == expected
    assert B.count(int(st.mask_all[0]), int(st.mask_all[1])) == 32


def test_load_position_all_chess_reverse_index():
    st = P.load_position(INITIAL_FEN)
    for piece in range(16, 48):
        site = int(st.all_chess[piece])
        assert site >= 0
        assert int(st.board[site]) == piece
    alive = sum(1 for piece in range(16, 48) if st.all_chess[piece] >= 0)
    assert alive == 32


def test_bit_planes_match_board():
    st = P.load_position(INITIAL_FEN)
    for row in range(10):
        expected = 0
        for col in range(9):
            if st.board[row * 9 + col] != 0:
                expected |= 1 << (8 - col)
        assert int(st.bit_row[row]) == expected
    for col in range(9):
        expected = 0
        for row in range(10):
            if st.board[row * 9 + col] != 0:
                expected |= 1 << (9 - row)
        assert int(st.bit_col[col]) == expected


def test_piece_index_assignment_is_scan_order():
    # 非标准布局：扫描顺序按 FEN 字符先后分配索引，而不是按站点几何
    st = P.load_position("9/9/9/9/9/9/9/p8/9/1r7 b - - 0 1")
    assert st.board[C.xy_to_site(0, 2)] == 27    # 先扫到的 'p' (row7,col0) 取 27
    assert st.board[C.xy_to_site(1, 0)] == 17    # 后扫到的 'r' (row9,col1) 取 17
    assert int(st.side_to_move[0]) == C.BLACK


def test_side_to_move_defaults_to_red():
    st = P.load_position("4k4/9/9/9/9/9/9/9/9/4K4")
    assert int(st.side_to_move[0]) == C.RED


def test_load_position_masks_and_roles():
    st = P.load_position(INITIAL_FEN)
    assert int(st.mask_all[0]) & B.LO_MASK
    for play in (C.RED, C.BLACK):
        lo, hi = int(st.mask_personal[play, 0]), int(st.mask_personal[play, 1])
        assert B.count(lo, hi) == 16
    for role in range(1, 15):
        lo, hi = int(st.mask_role[role, 0]), int(st.mask_role[role, 1])
        assert B.count(lo, hi) == int(st.remain[role])
    red_score, black_score = P.full_base_score(st)
    assert int(st.base_score[C.RED]) == red_score
    assert int(st.base_score[C.BLACK]) == black_score


def test_zobrist_tables_properties():
    assert Z.ZOB32.shape == (90, 15)
    assert Z.ZOB64.shape == (90, 15)
    assert bool((Z.ZOB32 >= 0).all()) and bool((Z.ZOB32 < (1 << 31)).all())
    assert bool((Z.ZOB64 >= 0).all()) and bool((Z.ZOB64 < (1 << 63)).all())
    assert bool((Z.ZOB32[:, 0] == 0).all())
    assert bool((Z.ZOB64[:, 0] == 0).all())
    assert not Z.ZOB32.flags.writeable
    assert not Z.ZOB64.flags.writeable
    # 固定种子：重建结果逐值一致
    rng = np.random.default_rng(Z.SEED)
    expect32 = rng.integers(0, 1 << 31, size=(90, 15), dtype=np.int64)
    expect64 = rng.integers(0, 1 << 63, size=(90, 15), dtype=np.int64)
    expect32[:, 0] = 0
    expect64[:, 0] = 0
    assert np.array_equal(Z.ZOB32, expect32)
    assert np.array_equal(Z.ZOB64, expect64)


def test_zobrist_matches_full_recompute():
    st = P.load_position(INITIAL_FEN)
    z32, z64 = P.full_zobrist(st)
    assert z32 == int(st.zob[0]) and z64 == int(st.zob[1])


def test_zobrist_after_capture_matches_full_recompute():
    st = P.load_position("4k4/9/9/p8/9/9/9/9/9/R3K4 w - - 0 1")
    m = C.pack_move(C.xy_to_site(0, 0), C.xy_to_site(0, 6))
    undo = P.make_move(st, m)
    assert P.full_zobrist(st) == (int(st.zob[0]), int(st.zob[1]))
    P.unmake_move(st, m, undo)
    assert P.full_zobrist(st) == (int(st.zob[0]), int(st.zob[1]))


def test_make_unmake_restores_everything():
    st = P.load_position(INITIAL_FEN)
    snapshot = {f: getattr(st, f).copy() for f in st._fields}
    moves = P.pseudo_moves(st, C.RED)
    assert len(moves) == 44
    for m in moves:
        undo = P.make_move(st, m)
        # 增量 == 全量
        assert P.full_zobrist(st) == (int(st.zob[0]), int(st.zob[1]))
        assert P.full_base_score(st) == (int(st.base_score[C.RED]), int(st.base_score[C.BLACK]))
        P.unmake_move(st, m, undo)
        for f in st._fields:
            assert np.array_equal(getattr(st, f), snapshot[f]), (f, m)


def test_side_to_move_toggles_on_make_and_unmake():
    st = P.load_position(INITIAL_FEN)
    m = int(P.pseudo_moves(st, C.RED)[0])
    undo = P.make_move(st, m)
    assert int(st.side_to_move[0]) == C.BLACK
    P.unmake_move(st, m, undo)
    assert int(st.side_to_move[0]) == C.RED


def test_capture_updates_remain_and_masks():
    st = P.load_position("4k4/9/9/p8/9/9/9/9/9/R3K4 w - - 0 1")
    src, dest = C.xy_to_site(0, 0), C.xy_to_site(0, 6)
    m = C.pack_move(src, dest)
    assert P.move_is_capture(st, m)
    before = int(st.remain[C.BLACK_SOLDIER])
    undo = P.make_move(st, m)
    assert int(st.remain[C.BLACK_SOLDIER]) == before - 1
    assert int(st.all_chess[27]) == -1
    assert int(st.board[dest]) == 33
    P.unmake_move(st, m, undo)
    assert int(st.remain[C.BLACK_SOLDIER]) == before
    assert int(st.all_chess[27]) == dest


def test_move_is_capture():
    st = P.load_position("4k4/9/9/p8/9/9/9/9/9/R3K4 w - - 0 1")
    capture = C.pack_move(C.xy_to_site(0, 0), C.xy_to_site(0, 6))
    quiet = C.pack_move(C.xy_to_site(0, 0), C.xy_to_site(0, 1))
    assert P.move_is_capture(st, capture)
    assert not P.move_is_capture(st, quiet)


def test_capture_updates_bit_planes_and_mask_roles():
    st = P.load_position("4k4/9/9/p8/9/9/9/9/9/R3K4 w - - 0 1")
    src, dest = C.xy_to_site(0, 0), C.xy_to_site(0, 6)
    m = C.pack_move(src, dest)
    src_piece, victim = int(st.board[src]), int(st.board[dest])
    src_role = int(C.PIECE_ROLES[src_piece])
    victim_role = int(C.PIECE_ROLES[victim])
    src_row, src_col = divmod(src, 9)
    dest_row, dest_col = divmod(dest, 9)
    before_all = B.count(int(st.mask_all[0]), int(st.mask_all[1]))
    undo = P.make_move(st, m)
    # 走子方掩码与角色掩码迁往目标格
    assert B.has_site(int(st.mask_role[src_role, 0]), int(st.mask_role[src_role, 1]), dest)
    assert not B.has_site(int(st.mask_personal[C.RED, 0]), int(st.mask_personal[C.RED, 1]), src)
    # 被吃方掩码清除
    assert not B.has_site(int(st.mask_role[victim_role, 0]), int(st.mask_role[victim_role, 1]), dest)
    assert not B.has_site(int(st.mask_personal[C.BLACK, 0]), int(st.mask_personal[C.BLACK, 1]), dest)
    # 行列位图跟随
    assert int(st.bit_row[src_row]) & (1 << (8 - src_col)) == 0
    assert int(st.bit_row[dest_row]) & (1 << (8 - dest_col)) != 0
    assert int(st.bit_col[src_col]) & (1 << (9 - src_row)) == 0
    assert int(st.bit_col[dest_col]) & (1 << (9 - dest_row)) != 0
    # 全部棋子掩码数量随吃子减一，撤销后恢复
    assert B.count(int(st.mask_all[0]), int(st.mask_all[1])) == before_all - 1
    P.unmake_move(st, m, undo)
    assert B.count(int(st.mask_all[0]), int(st.mask_all[1])) == before_all
    assert B.has_site(int(st.mask_personal[C.BLACK, 0]), int(st.mask_personal[C.BLACK, 1]), dest)


def test_pseudo_moves_counts_by_piece_type():
    st = P.load_position(INITIAL_FEN)
    moves = P.pseudo_moves(st, C.RED)
    assert len(moves) == 44          # 初始局面红方伪合法（无自将）
    # 至少验证：车/马/炮/兵都有着法
    srcs = {C.move_src(m) for m in moves}
    assert C.xy_to_site(0, 0) in srcs and C.xy_to_site(1, 0) in srcs


def test_pseudo_moves_black_initial_count():
    st = P.load_position(INITIAL_FEN)
    moves = P.pseudo_moves(st, C.BLACK)
    assert len(moves) == 44


def test_pseudo_moves_source_target_validity():
    st = P.load_position(INITIAL_FEN)
    for play in (C.RED, C.BLACK):
        for m in P.pseudo_moves(st, play):
            src, dest = C.move_src(m), C.move_dest(m)
            piece = int(st.board[src])
            assert piece != 0
            assert C.play_of_piece(piece) == play
            target = int(st.board[dest])
            assert target == 0 or C.play_of_piece(target) != play


def test_pseudo_moves_captures_only_opponent():
    st = P.load_position("4k4/9/9/p8/9/9/9/9/9/R3K4 w - - 0 1")
    moves = P.pseudo_moves(st, C.RED)
    assert C.pack_move(C.xy_to_site(0, 0), C.xy_to_site(0, 6)) in moves
    # 红车 81 不可能吃到己方 85 的帅
    assert C.pack_move(C.xy_to_site(0, 0), C.xy_to_site(4, 0)) not in moves


def test_pseudo_moves_respect_knight_leg():
    # 马在 (4,5)=site40，四个正交邻格全被占据 → 八个方向全部蹩腿
    st = P.load_position("9/9/9/4p4/3pNp3/4p4/9/9/9/9 w - - 0 1")
    moves = P.pseudo_moves(st, C.RED)
    srcs = {C.move_src(m) for m in moves}
    assert C.xy_to_site(4, 5) not in srcs


def _random_state(rng, plies):
    st = P.load_position(INITIAL_FEN)
    kings = (16, 32)
    for _ in range(plies):
        side = int(st.side_to_move[0])
        moves = [
            m for m in P.pseudo_moves(st, side)
            if int(st.board[C.move_dest(m)]) not in kings
        ]
        if not moves:
            break
        m = int(moves[int(rng.integers(len(moves)))])
        P.make_move(st, m)
    return st


def test_make_unmake_random_positions_roundtrip():
    rng = np.random.default_rng(20260921)
    states = [_random_state(rng, 5) for _ in range(20)]
    assert len({(int(s.zob[0]), int(s.zob[1])) for s in states}) > 1
    for st in states:
        snapshot = {f: getattr(st, f).copy() for f in st._fields}
        side = int(st.side_to_move[0])
        moves = P.pseudo_moves(st, side)
        assert moves
        for m in moves:
            undo = P.make_move(st, m)
            assert P.full_zobrist(st) == (int(st.zob[0]), int(st.zob[1])), m
            assert P.full_base_score(st) == (
                int(st.base_score[C.RED]),
                int(st.base_score[C.BLACK]),
            ), m
            P.unmake_move(st, m, undo)
            for f in st._fields:
                assert np.array_equal(getattr(st, f), snapshot[f]), (f, m)
