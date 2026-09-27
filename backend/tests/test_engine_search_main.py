"""Task 11：主搜索（根 PVS + negaScout + 迭代加深）的测试。

覆盖：
- `Stack` 的 `is_null` 字段与 `Ctx` 的根着法缓冲（`root_moves/root_scores/
  root_count/root_inited`）；
- `is_long_check` 遇空着节点终止回溯；
- 辅助：`RAdapt`、`FUTILITY_SCORE`、`is_danger`；
- `init_root`：根着法枚举（killer 优先、自将过滤、初始分递减）；
- `search_depth`：一轮根搜索 + 结果写回 root_scores + PV 写入 `stack.pv[0]`；
- 一步杀 / 两步杀 / 无杀局面 / 迭代加深 / stop 中断 / TT 生效 / 将死分数。

Java 参考：`PrincipalVariation.java`（searchMove L40-94、rootNegaScout
L95-148、negaScout L154-337）、`SearchEngine.java`（isDanger L274-286、
RAdapt L102-113、FutilityScore L19-30）、`MoveNodesSort.java`（next L81-150）、
`ChessMovePlay.java`（savePlayChess L44-83）。

与 Java 的有意差异（详见 `engine/search.py`）：
- `nega_scout` 入口检查 `ctx.stop`（Java 仅在根循环检查），支持快速中断；
- `FUTILITY_SCORE`/killer 索引在越界极端情形下钳位而非崩溃。
"""

import threading
import time

import numpy as np

from engine import analysis as A
from engine import constants as C
from engine import movegen as MG
from engine import position as P
from engine import search as S

SMALL = 1 << 10

OPENING_FEN = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"
# 黑将被红车 e1 将死（逃路 d0/f0 被 a0 车控制、e1 被红帅 e2 飞将）
MATE_FEN = "R3k4/4R4/4K4/9/9/9/9/9/9/9 b - - 0 1"
# 红方一步杀（车 b1-f1 困毙：d0 黑卒被 a0 车钉住、f0/e1 被 f1 车控）
MATE_IN_ONE_FEN = "R2pk4/1R7/9/3N5/5R3/9/9/9/9/3K5 w - - 0 1"
# 红方两步杀：车 b1-e1 逼将 e0-f0，红方第二步杀（马 e3-g2 或马 c2xd0 困毙）
MATE_IN_TWO_FEN = "3pk4/1R7/2N4N1/4N4/9/9/9/9/9/3K5 w - - 0 1"


def root(fen, prepare=True):
    st = P.load_position(fen)
    if prepare:
        A.prepare(st)
    return st


def new_search(fen, hash_size=SMALL):
    st = root(fen)
    ctx = S.new_context(hash_size=hash_size)
    stack = S.new_stack()
    stack.zob32[0] = st.zob[0]
    stack.zob64[0] = st.zob[1]
    return st, ctx, stack


def pv_moves(stack):
    """提取 `stack.pv[0]` 中的连续非零着法。"""
    out = []
    for m in stack.pv[0]:
        if m == 0:
            break
        out.append(int(m))
    return out


# --------------------------------------------------------------------------
# 结构扩展
# --------------------------------------------------------------------------


def test_new_stack_layout_includes_is_null():
    stack = S.new_stack()
    assert S.Stack._fields == ("zob32", "zob64", "is_eat", "chk", "is_null", "pv")
    assert stack.is_null.shape == (S.STACK_SIZE,) and stack.is_null.dtype == np.int8
    assert not stack.is_null.any()


def test_new_context_has_root_fields():
    ctx = S.new_context(hash_size=SMALL)
    assert ctx.root_moves.shape == (128,) and ctx.root_moves.dtype == np.int32
    assert ctx.root_scores.shape == (128,) and ctx.root_scores.dtype == np.int32
    assert ctx.root_count.shape == (1,) and ctx.root_count.dtype == np.int32
    assert ctx.root_inited.shape == (1,) and ctx.root_inited.dtype == np.int8
    assert ctx.root_count[0] == 0 and ctx.root_inited[0] == 0
    assert not ctx.root_moves.any() and not ctx.root_scores.any()


def test_is_long_check_stops_at_null_move():
    stack = S.new_stack()
    z32, z64 = 0x1234, 0x123456789ABCDEF
    stack.zob32[1] = z32
    stack.zob64[1] = z64
    stack.zob32[2] = z32
    stack.zob64[2] = z64
    stack.chk[2] = 1
    assert S.is_long_check(stack, 2)
    # 第 1 层是空着节点（Java nullNode 的 moveNode==null）→ 回溯立即终止
    stack.is_null[1] = 1
    assert not S.is_long_check(stack, 2)
    # 空着层本身不参与 zobrist 比较（即使哈希相同）
    assert not S.is_long_check(stack, 1)


# --------------------------------------------------------------------------
# 辅助函数
# --------------------------------------------------------------------------


def test_r_adapt_values():
    assert S.RAdapt(1) == 2
    assert S.RAdapt(6) == 2
    assert S.RAdapt(7) == 3
    assert S.RAdapt(8) == 3
    assert S.RAdapt(9) == 4
    assert S.RAdapt(20) == 4


def test_futility_score_table():
    assert S.FUTILITY_SCORE.shape == (64, 64)
    assert S.FUTILITY_SCORE.dtype == np.int32
    assert not S.FUTILITY_SCORE[0].any()
    for d in (1, 2, 5, 10, 63):
        for k in (0, 1, 5, 63):
            expected = int(d * 1.29 * 155) - k * d * 10
            assert int(S.FUTILITY_SCORE[d, k]) == expected


def test_is_danger_counts_opponent_chariot_knight_gun_in_margin():
    # 黑方危险区（row0-2 + row3 中路）内两枚红车 → 不危险
    st = root("4k4/9/RR7/9/9/9/9/9/9/3K5 w - - 0 1")
    assert not S.is_danger(st, C.BLACK)
    # 加上红马 c2 → 三枚 → 危险（play 视角）
    st = root("4k4/9/RRN6/9/9/9/9/9/9/3K5 w - - 0 1")
    assert S.is_danger(st, C.BLACK)
    # 红方半场对称：黑车 a7/b7 + 黑马 c7 → 红方危险
    st = root("3K5/9/9/9/9/9/9/rrn6/9/4k4 b - - 0 1")
    assert S.is_danger(st, C.RED)
    st = root("3K5/9/9/9/9/9/9/rr7/9/4k4 b - - 0 1")
    assert not S.is_danger(st, C.RED)
    # 初始局面双方都不危险（危险区内的车马炮不足 3）
    st = root(OPENING_FEN)
    assert not S.is_danger(st, C.RED)
    assert not S.is_danger(st, C.BLACK)


# --------------------------------------------------------------------------
# 根枚举
# --------------------------------------------------------------------------


def test_init_root_enumerates_all_legal_moves_with_descending_scores():
    st, ctx, stack = new_search(OPENING_FEN)
    S.init_root(st, ctx, stack)
    assert ctx.root_inited[0] == 1
    count = int(ctx.root_count[0])
    legal = MG.gen_legal_moves(st, C.RED)
    assert count == len(legal)
    moves = {int(ctx.root_moves[i]) for i in range(count)}
    assert moves == {int(m) for m in legal}
    scores = [int(ctx.root_scores[i]) for i in range(count)]
    assert scores == list(range(100, 100 - count, -1))


def test_init_root_prefers_killers_and_filters_self_check():
    st, ctx, stack = new_search(OPENING_FEN)
    # 初始局面无马/炮被钉住，killer 参与时排在最前
    killer = C.pack_move(54, 45)
    ctx.killer[6, 0] = killer
    S.init_root(st, ctx, stack, killer_depth=6)
    assert int(ctx.root_moves[0]) == killer
    # 非法 killer（源格为空）被跳过
    st2, ctx2, stack2 = new_search(OPENING_FEN)
    ctx2.killer[6, 0] = C.pack_move(0, 1)
    S.init_root(st2, ctx2, stack2, killer_depth=6)
    assert int(ctx2.root_moves[0]) != C.pack_move(0, 1)

    # 自将着法必须被过滤：黑车 a9 照面红帅 d9，帅只能下 d8（e9 仍在车口）
    st3, ctx3, stack3 = new_search("4k4/9/9/9/9/9/9/9/9/r2K5 w - - 0 1")
    S.init_root(st3, ctx3, stack3)
    moves = [int(ctx3.root_moves[i]) for i in range(int(ctx3.root_count[0]))]
    assert C.pack_move(84, 75) in moves
    assert C.pack_move(84, 85) not in moves
    for m in moves:
        undo = P.make_move(st3, m)
        assert not MG.in_check(st3, C.RED)
        P.unmake_move(st3, m, undo)


def test_init_root_respects_root_buffer_capacity():
    st, ctx, stack = new_search(OPENING_FEN)
    S.init_root(st, ctx, stack)
    assert 0 < int(ctx.root_count[0]) <= 128


# --------------------------------------------------------------------------
# search_depth：一步杀 / 两步杀 / 无杀局面
# --------------------------------------------------------------------------


def test_search_depth_finds_mate_in_one():
    st, ctx, stack = new_search(MATE_IN_ONE_FEN)
    S.init_root(st, ctx, stack)
    score, mate = S.search_depth(st, ctx, stack, 2)
    assert score >= C.MAX_SCORE - 10
    assert mate == 1
    moves = pv_moves(stack)
    assert moves
    # PV 首着走完后黑方无合法着法（将杀或困毙）
    undo = P.make_move(st, moves[0])
    assert MG.gen_legal_moves(st, C.BLACK).size == 0
    P.unmake_move(st, moves[0], undo)


def test_search_depth_finds_mate_in_two():
    st, ctx, stack = new_search(MATE_IN_TWO_FEN)
    S.init_root(st, ctx, stack)
    # depth=2 的主搜索深度不足以覆盖 3-ply 杀，但 quiesc（动态子力）会继续
    # 搜索吃子序列并发现该杀（Java chessBaseScore 语义下同样会报 mate=3）
    _, mate2 = S.search_depth(st, ctx, stack, 2)
    assert mate2 == 3
    # depth=4 找到：红 1、黑 1、红 2 三步后黑方无着法
    score4, mate4 = S.search_depth(st, ctx, stack, 4)
    assert score4 >= C.MAX_SCORE - 10
    assert mate4 == 3
    moves = pv_moves(stack)
    assert len(moves) >= 3
    play = C.RED
    undos = []
    for m in moves[:3]:
        assert MG.legal_move(st, play, m)
        undos.append((m, P.make_move(st, m)))
        assert not MG.in_check(st, play)
        play = 1 - play
    assert MG.gen_legal_moves(st, play).size == 0
    for m, undo in reversed(undos):
        P.unmake_move(st, m, undo)


def test_search_depth_opening_position_score_bounded_and_pv_legal():
    st, ctx, stack = new_search(OPENING_FEN)
    S.init_root(st, ctx, stack)
    score, mate = S.search_depth(st, ctx, stack, 4)
    assert -300 <= score <= 300
    assert mate == 0
    moves = pv_moves(stack)
    assert moves
    play = C.RED
    for m in moves:
        assert MG.legal_move(st, play, m)
        undo = P.make_move(st, m)
        assert not MG.in_check(st, play)
        play = 1 - play
        P.unmake_move(st, m, undo)


# --------------------------------------------------------------------------
# 迭代加深 / stop / TT
# --------------------------------------------------------------------------


def test_iterative_deepening_node_growth_and_same_depth_stability():
    st, ctx, stack = new_search(OPENING_FEN)
    S.init_root(st, ctx, stack)
    deltas = []
    for depth in (4, 5, 6, 7, 8):
        before = int(ctx.nodes[0])
        _, mate = S.search_depth(st, ctx, stack, depth)
        deltas.append(int(ctx.nodes[0]) - before)
        assert mate == 0
    assert all(d > 0 for d in deltas)
    assert deltas[-1] > deltas[0]

    # 同层重复搜索：分数一致，TT 命中后评估节点数大幅下降（通常为 0）
    first_six = deltas[2]
    before = int(ctx.nodes[0])
    score_a, _ = S.search_depth(st, ctx, stack, 6)
    nodes_a = int(ctx.nodes[0]) - before
    before = int(ctx.nodes[0])
    score_b, _ = S.search_depth(st, ctx, stack, 6)
    nodes_b = int(ctx.nodes[0]) - before
    assert score_a == score_b
    assert nodes_b <= nodes_a
    assert nodes_a < first_six


def test_tt_makes_second_search_cheaper():
    st, ctx, stack = new_search(OPENING_FEN)
    S.init_root(st, ctx, stack)
    S.search_depth(st, ctx, stack, 4)
    first = int(ctx.nodes[0])
    S.search_depth(st, ctx, stack, 4)
    second = int(ctx.nodes[0]) - first
    assert 0 < second < first


def test_search_depth_stop_flag_interrupts_before_descent():
    st, ctx, stack = new_search(OPENING_FEN)
    S.init_root(st, ctx, stack)
    ctx.stop[0] = 1
    S.search_depth(st, ctx, stack, 6)
    # 根首着的子节点入口即被停旗中断，从未进入静态评估
    assert int(ctx.nodes[0]) == 0


def test_null_move_path_runs_without_error():
    # 初始局面 depth=6 的非 PV 分支（depth>=2、有攻击子）会走空着裁剪路径
    st, ctx, stack = new_search(OPENING_FEN)
    S.init_root(st, ctx, stack)
    score, _ = S.search_depth(st, ctx, stack, 6)
    assert -500 < score < 500
    assert int(ctx.nodes[0]) > 0


# --------------------------------------------------------------------------
# 将死分数
# --------------------------------------------------------------------------


def test_search_depth_mated_position_returns_negative_max_score():
    st, ctx, stack = new_search(MATE_FEN)
    S.init_root(st, ctx, stack)
    assert int(ctx.root_count[0]) == 0
    score, _ = S.search_depth(st, ctx, stack, 4)
    assert score == -(C.MAX_SCORE - 0)


def test_nega_scout_mate_score_uses_ply():
    st, ctx, stack = new_search(MATE_FEN)
    stack.zob32[3] = st.zob[0]
    stack.zob64[3] = st.zob[1]
    score = S.nega_scout(st, ctx, stack, -C.MAX_SCORE, C.MAX_SCORE, 4, 3, C.BLACK, 1, 0)
    assert score == -(C.MAX_SCORE - 3)


def test_search_depth_writes_back_root_scores():
    st, ctx, stack = new_search(OPENING_FEN)
    S.init_root(st, ctx, stack)
    count = int(ctx.root_count[0])
    before = [int(ctx.root_scores[i]) for i in range(count)]
    assert before == list(range(100, 100 - count, -1))
    S.search_depth(st, ctx, stack, 4)
    after = [int(ctx.root_scores[i]) for i in range(count)]
    # 结果写回 root_scores（供下一轮 getSortAfterBestMove 动态选择）
    assert after != before
    assert all(-C.MAX_SCORE <= s <= C.MAX_SCORE for s in after)


# --------------------------------------------------------------------------
# mate 分数不入 TT（修正 Java 继承缺陷）：同一 ctx 迭代加深不再漂移
# --------------------------------------------------------------------------

# 5 个杀棋局面（1/1/3/3/5 ply），期望值由独立穷举验证
MATE_CHAIN_CASES = (
    ("3R5/5k1N1/9/9/9/9/9/9/9/4K1R2 w - - 0 1", 1),
    ("5k3/8R/9/9/9/9/9/9/9/3K3P1 w - - 0 1", 1),
    ("3pk4/1R7/2N4N1/4N4/9/9/9/9/9/3K5 w - - 0 1", 3),
    ("3pk4/1R7/2N6/4N4/9/9/9/9/9/3K5 w - - 0 1", 3),
    ("2C6/4k4/1C7/9/9/9/9/9/9/3K5 w - - 0 1", 5),
)


def _force_mate(st, play, plies):
    """play 方在 plies 内强制将死/困毙对方（只用 movegen/position 的穷举）。"""
    moves = MG.gen_legal_moves(st, play)
    if moves.size == 0:
        return False
    opp = 1 - play
    for i in range(moves.size):
        m = int(moves[i])
        undo = P.make_move(st, m)
        if MG.gen_legal_moves(st, opp).size == 0:
            P.unmake_move(st, m, undo)
            return True
        if plies >= 3:
            all_ok = True
            replies = MG.gen_legal_moves(st, opp)
            for j in range(replies.size):
                reply = int(replies[j])
                undo2 = P.make_move(st, reply)
                ok = _force_mate(st, play, plies - 2)
                P.unmake_move(st, reply, undo2)
                if not ok:
                    all_ok = False
                    break
            if all_ok:
                P.unmake_move(st, m, undo)
                return True
        P.unmake_move(st, m, undo)
    return False


def min_mate_ply(fen, max_ply=7):
    """独立穷举最小杀步（ply），无杀返回 0。"""
    st = root(fen)
    play = int(st.side_to_move[0])
    for plies in range(1, max_ply + 1, 2):
        if _force_mate(st, play, plies):
            return plies
    return 0


def test_exhaustive_min_mate_matches_expected_cases():
    for fen, expect in MATE_CHAIN_CASES:
        assert min_mate_ply(fen) == expect


def test_iterative_deepening_mate_reports_do_not_drift():
    # mate 分数不入 TT：同一 ctx 迭代加深时每层报出的 mate 要么是 0（深度
    # 还不够），要么等于穷举最小杀步；深度足够后必须报出正确值且保持稳定
    for fen, expect in MATE_CHAIN_CASES:
        st, ctx, stack = new_search(fen)
        reported = []
        for depth in (4, 5, 6, 7, 8):
            score, mate = S.search_depth(st, ctx, stack, depth)
            mate = int(mate)
            reported.append(mate)
            assert mate in (0, expect), (fen, depth, mate)
            if mate != 0:
                assert int(score) == C.MAX_SCORE - expect
        assert expect in reported
        # 足够深的后续两轮仍报相同值（TT 复用下不再漂移）
        for _ in range(2):
            score, mate = S.search_depth(st, ctx, stack, 8)
            assert int(mate) == expect
            assert int(score) == C.MAX_SCORE - expect


# --------------------------------------------------------------------------
# nogil 中断响应
# --------------------------------------------------------------------------


def test_stop_from_other_thread_interrupts_nogil_search():
    st, ctx, stack = new_search(OPENING_FEN)
    S.init_root(st, ctx, stack)
    S.search_depth(st, ctx, stack, 4)  # 预热 JIT

    st2, ctx2, stack2 = new_search(OPENING_FEN)
    S.init_root(st2, ctx2, stack2)

    def setter():
        time.sleep(0.15)
        ctx2.stop[0] = 1

    thread = threading.Thread(target=setter)
    thread.start()
    start = time.perf_counter()
    S.search_depth(st2, ctx2, stack2, 8)
    elapsed = time.perf_counter() - start
    thread.join()
    assert int(ctx2.stop[0]) == 1
    # nogil 生效：其他线程可置停旗，depth8 搜索应在亚秒级返回
    # （不释放 GIL 时该搜索会跑满数秒）
    assert elapsed < 2.0
