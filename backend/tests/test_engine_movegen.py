"""Task 6：着法生成、将军检测与合法性校验测试。

覆盖：
- 两阶段着法顺序（先全部吃子、再全部非吃子；棋子顺序将最后）；
- 初始局面伪着法数量；
- 车/炮/马/兵将军与飞将；
- 蹩腿/塞眼；
- legal_move 快速校验；
- opp_attack_site 攻击位语义；
- gen_legal_moves 与手工过滤自将一致。
"""

import numpy as np

from chess_engine.board import INITIAL_FEN
from engine import bitboard as B
from engine import constants as C
from engine import movegen as MG
from engine import position as P


def _moves(st, play, captures_only=False):
    if captures_only:
        buf, n = MG.gen_captures(st, play)
    else:
        buf, n = MG.gen_moves(st, play)
    return [int(m) for m in buf[:n]]


def _legal(st, play):
    return [int(m) for m in MG.gen_legal_moves(st, play)]


def _site(col, row):
    """(列, 行) → site；row 与 site 定义一致（0 = 黑方底线，9 = 红方底线）。"""
    return row * 9 + col


def _move(src, dest):
    return int(C.pack_move(_site(*src), _site(*dest)))


def _random_state(rng, plies):
    st = P.load_position(INITIAL_FEN)
    kings = (C.BLACK_PIECES_START, C.RED_PIECES_START)
    for _ in range(plies):
        side = int(st.side_to_move[0])
        buf, n = MG.gen_moves(st, side)
        moves = [int(m) for m in buf[:n] if int(st.board[C.move_dest(m)]) not in kings]
        if not moves:
            break
        P.make_move(st, moves[int(rng.integers(len(moves)))])
    return st


def _targets_of(st, play, src_site):
    return {C.move_dest(m) for m in _moves(st, play) if C.move_src(m) == src_site}


def test_initial_pseudo_moves_both_sides():
    st = P.load_position(INITIAL_FEN)
    assert len(_moves(st, C.RED)) == 44
    assert len(_moves(st, C.BLACK)) == 44
    assert len(_legal(st, C.RED)) == 44
    assert len(_legal(st, C.BLACK)) == 44


def test_gen_moves_two_phase_order():
    # 红车 (4,5) 可横向吃到黑卒 (3,5)，同时大量非吃子着法。
    st = P.load_position("4k4/9/9/9/9/3pR4/9/9/9/3K5 w - - 0 1")
    moves = _moves(st, C.RED)
    capture_flags = [int(st.board[C.move_dest(m)]) != 0 for m in moves]
    assert any(capture_flags)
    assert capture_flags == sorted(capture_flags, reverse=True)
    assert _move((4, 5), (3, 5)) in moves


def test_gen_moves_piece_order_king_last():
    # 每个阶段内棋子顺序 = PIECE_STARTS[play]+1 .. +15，最后为将（着法 src 是 site）。
    st = P.load_position(INITIAL_FEN)
    for play in (C.RED, C.BLACK):
        start = C.PIECE_STARTS[play]
        expected = [
            int(st.all_chess[p]) for p in list(range(start + 1, start + 16)) + [start]
        ]
        captures = _moves(st, play, captures_only=True)
        full = _moves(st, play)
        quiets = [m for m in full if int(st.board[C.move_dest(m)]) == 0]
        assert full == captures + quiets  # 两阶段不交错
        for stage in (captures, quiets):
            srcs = []
            for m in stage:
                s = C.move_src(m)
                if s not in srcs:
                    srcs.append(s)
            assert srcs == [s for s in expected if s in srcs]
            if expected[-1] in srcs:
                assert srcs[-1] == expected[-1]  # 将/帅最后


def test_gen_moves_black_target_scan_order():
    # 黑车 (3,9) → 红帅 (4,9) 为阶段 A；阶段 B 的目标按 Java
    # MSB(BLACKPLAYSIGN) 分四段：81..89、54..80、27..53、0..26。
    st = P.load_position("4k4/9/9/9/9/9/9/9/9/3rK4 w - - 0 1")
    car = [m for m in _moves(st, C.BLACK) if C.move_src(m) == _site(3, 9)]
    captures = [m for m in car if int(st.board[C.move_dest(m)]) != 0]
    quiets = [m for m in car if int(st.board[C.move_dest(m)]) == 0]
    assert captures == [_move((3, 9), (4, 9))]
    assert quiets == [
        int(C.pack_move(_site(3, 9), d))
        for d in (81, 82, 83, 57, 66, 75, 30, 39, 48, 3, 12, 21)
    ]


def test_gen_into_buffers_api():
    st = P.load_position(INITIAL_FEN)
    buf = np.zeros(MG.MAX_MOVES, dtype=np.int32)
    n = MG.gen_moves_into(st, C.RED, buf, False)
    assert n == 44
    assert [int(m) for m in buf[:n]] == _legal(st, C.RED)
    # 初始局面红方有两个吃子：两门炮各自隔黑炮吃黑马。
    cap_buf = np.zeros(MG.MAX_MOVES, dtype=np.int32)
    n_cap = MG.gen_captures_into(st, C.RED, cap_buf)
    assert n_cap == 2
    assert all(int(st.board[C.move_dest(m)]) < C.RED_PIECES_START for m in cap_buf[:n_cap])
    legal_buf = np.zeros(MG.MAX_MOVES, dtype=np.int32)
    n2 = MG.gen_legal_moves_into(st, C.RED, legal_buf)
    assert n2 == 44
    assert [int(m) for m in legal_buf[:n2]] == _legal(st, C.RED)


def test_gen_captures_only_captures():
    st = P.load_position("4k4/9/9/9/9/3pR4/9/9/9/3K5 w - - 0 1")
    caps = _moves(st, C.RED, captures_only=True)
    assert caps
    for m in caps:
        assert int(st.board[C.move_dest(m)]) != 0
        assert int(st.board[C.move_dest(m)]) < C.RED_PIECES_START


def test_chariot_check():
    st = P.load_position("4k4/9/9/9/9/4R4/9/9/9/3K5 w - - 0 1")
    assert MG.in_check(st, C.BLACK)
    assert not MG.in_check(st, C.RED)
    legal = _legal(st, C.BLACK)
    assert _move((4, 0), (5, 0)) in legal
    assert _move((4, 0), (3, 0)) not in legal  # 仍与红帅同列（飞将）


def test_gun_check_needs_screen():
    with_screen = P.load_position("4k4/9/9/4P4/9/4C4/9/9/9/3K5 w - - 0 1")
    assert MG.in_check(with_screen, C.BLACK)
    no_screen = P.load_position("4k4/9/9/9/9/4C4/9/9/9/3K5 w - - 0 1")
    assert not MG.in_check(no_screen, C.BLACK)


def test_knight_check_and_blocked_leg():
    check = P.load_position("4k4/9/3N5/9/9/9/9/9/9/3K5 w - - 0 1")
    assert MG.in_check(check, C.BLACK)
    assert _move((3, 2), (4, 0)) in _moves(check, C.RED)

    blocked = P.load_position("4k4/3P5/3N5/9/9/9/9/9/9/3K5 w - - 0 1")
    assert not MG.in_check(blocked, C.BLACK)
    assert _move((3, 2), (4, 0)) not in _moves(blocked, C.RED)


def test_soldier_check_crossed_river_sideways():
    st = P.load_position("9/3Pk4/9/9/9/9/9/9/9/3K5 w - - 0 1")
    assert MG.in_check(st, C.BLACK)
    assert _move((3, 1), (4, 1)) in _moves(st, C.RED)


def test_soldier_check_forward():
    st = P.load_position("4k4/4P4/9/9/9/9/9/9/9/3K5 w - - 0 1")
    assert MG.in_check(st, C.BLACK)
    assert _move((4, 1), (4, 0)) in _legal(st, C.RED)


def test_soldier_quiet_moves_before_after_river():
    # 红兵 (4,6) 未过河：只能直进；红兵 (4,4) 已过河：可直进 + 左右横走。
    before = P.load_position("4k4/9/9/9/9/9/4P4/9/9/3K5 w - - 0 1")
    assert _targets_of(before, C.RED, _site(4, 6)) == {_site(4, 5)}
    after = P.load_position("4k4/9/9/9/4P4/9/9/9/9/3K5 w - - 0 1")
    assert _targets_of(after, C.RED, _site(4, 4)) == {_site(4, 3), _site(3, 4), _site(5, 4)}


def test_kings_facing_and_in_check():
    st = P.load_position("4k4/9/9/9/9/9/9/9/9/4K4 w - - 0 1")
    assert MG.kings_facing(st)
    assert MG.in_check(st, C.BLACK)
    assert MG.in_check(st, C.RED)
    legal = _legal(st, C.BLACK)
    assert _move((4, 0), (3, 0)) in legal
    assert _move((4, 0), (5, 0)) in legal
    assert _move((4, 0), (4, 1)) not in legal

    blocked = P.load_position("4k4/9/9/9/4P4/9/9/9/9/4K4 w - - 0 1")
    assert not MG.kings_facing(blocked)
    assert not MG.in_check(blocked, C.BLACK)
    assert not MG.in_check(blocked, C.RED)


def test_knight_leg_blocks_direction():
    # 红马 (4,5)，腿位 (4,4) 被红兵占据 → (3,3)/(5,3) 不可走，其余方向仍可走。
    st = P.load_position("4k4/9/9/9/4P4/4N4/9/9/9/3K5 w - - 0 1")
    targets = _targets_of(st, C.RED, _site(4, 5))
    assert _site(3, 3) not in targets and _site(5, 3) not in targets
    assert _site(2, 4) in targets and _site(6, 4) in targets
    assert _site(3, 7) in targets and _site(5, 7) in targets


def test_elephant_eye_blocks_direction():
    # 红象 (4,6)，眼位 (3,7) 被红兵占据 → 不可走 (2,8)，仍可走 (6,8)。
    st = P.load_position("4k4/9/9/9/9/9/4B4/3P5/9/3K5 w - - 0 1")
    targets = _targets_of(st, C.RED, _site(4, 6))
    assert _site(2, 8) not in targets
    assert _site(6, 8) in targets


def test_legal_move_accepts_and_rejects():
    st = P.load_position(INITIAL_FEN)
    assert MG.legal_move(st, C.RED, _move((0, 9), (0, 8)))
    assert MG.legal_move(st, C.RED, _move((1, 9), (0, 7)))
    # 目标为己方兵（车沿列被己方兵挡住 → 非法）
    assert not MG.legal_move(st, C.RED, _move((0, 9), (0, 6)))
    # 斜走非法
    assert not MG.legal_move(st, C.RED, _move((0, 9), (1, 8)))
    # 源子不属于走子方
    assert not MG.legal_move(st, C.RED, _move((0, 0), (0, 1)))


def test_opp_attack_site_semantics():
    st = P.load_position("3rk4/9/9/9/9/4R4/9/9/9/3K5 w - - 0 1")
    red_attack = MG.opp_attack_site(st, C.BLACK)   # 红方攻击位
    black_attack = MG.opp_attack_site(st, C.RED)   # 黑方攻击位
    assert B.has_site(red_attack[0], red_attack[1], _site(4, 0))   # 红车吃到黑将
    assert B.has_site(black_attack[0], black_attack[1], _site(3, 9))  # 黑车吃到红帅
    assert not B.has_site(black_attack[0], black_attack[1], _site(4, 5))
    assert B.count(black_attack[0], black_attack[1]) > 0


def test_opp_attack_site_smoke_initial():
    st = P.load_position(INITIAL_FEN)
    for play in (C.RED, C.BLACK):
        lo, hi = MG.opp_attack_site(st, play)
        n = B.count(lo, hi)
        assert 15 <= n <= 80


def test_gen_legal_moves_matches_manual_self_check_filter():
    rng = np.random.default_rng(20260921)
    states = [_random_state(rng, 6) for _ in range(5)]
    for st in states:
        play = int(st.side_to_move[0])
        expected = []
        for m in _moves(st, play):
            undo = P.make_move(st, m)
            ok = not MG.in_check(st, play)
            P.unmake_move(st, m, undo)
            if ok:
                expected.append(m)
        assert _legal(st, play) == expected
