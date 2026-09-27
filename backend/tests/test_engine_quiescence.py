"""Task 10：静态搜索（`engine/search.py`）的测试。

覆盖：
- `Stack` 搜索栈布局（68 层三角 PV）与 `new_stack`；
- `fine_evaluate` / `rough_evaluate`；
- `is_long_check` 长将检测（回溯范围、吃子截断、比较顺序、根节点不参与）；
- `is_draw` 双方无攻击子判和；
- `gen_quiesc_moves` 好/坏吃子分类（`savePlayChess` 语义：目标价值+位置分
  >= 150 进 good，否则进 general；被将时 general 追加全部非吃子）；
- 选择排序 `_select_best` 的原地交换语义（`getSortAfterBestMove`）；
- `quiesc_search` 主流程：王被吃、长将 8888、和棋 0、ply 保险丝、
  stand-pat、吃子递归、被将枚举全部着法、无着法将死分。

Java 参考：`SearchEngine.java` L163-273（quiesc/isLongChk/isDraw/
fineEvaluate/roughEvaluate）、`ChessQuiescMove.java` L44-64、
`MoveNodesSort.java` L44-80/L215-228。
"""

import numpy as np
from engine import analysis as A
from engine import constants as C
from engine import evaluate as E
from engine import movegen as MG
from engine import position as P
from engine import search as S

SMALL = 1 << 10

# 标准开局（中局阶段）与常用测试盘面
OPENING_FEN = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"
# 中局阶段且不对称（少一黑车）：中局/残局评估值不同，可验证阶段分派
MIDDLE_ASYMMETRIC_FEN = (
    "rnbakabn1/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"
)
# 红车 a9、红帅 d9、黑马 a4、黑将 e0：红车可白吃无保护黑马
HANGING_KNIGHT_FEN = "4k4/9/9/9/n8/9/9/9/9/R2K5 w - - 0 1"
# 同上，但黑车 a0 保护 a 列：红车吃马后被吃回
PROTECTED_KNIGHT_FEN = "r3k4/9/9/9/n8/9/9/9/9/R2K5 w - - 0 1"
# 红车 c5、红帅 e9、黑车 e5、黑卒 c0、黑将 e0
# 动态子力（Java chessBaseScore）：残局黑卒 = 100+(11-1)*8 = 180，
# 吃 e5 黑车与吃 c0 黑卒（180+0）都 >= 150 → 均进 good
CLASSIFY_FEN = "2p1k4/9/9/9/9/2R1r4/9/9/9/4K4 w - - 0 1"
# 近满员中局：红车 e5 白吃黑卒 e6（黑攻击子 10 → 卒动态 108，108+10=118 < 150）
GENERAL_FEN = "rnbakabnr/9/1c5c1/11p1p1p1p/9/4R4/P1P1P1P1P/1C5C1/9/RNBAKABN1 w - - 0 1"
# 黑将被红车 e1 将死（逃路 d0/f0 被 a0 车控制、e1 被红帅 e2 飞将）
MATE_FEN = "R3k4/4R4/4K4/9/9/9/9/9/9/9 b - - 0 1"
# 黑将被将但有唯一逃路（吃 e1 车）
CHECK_ESCAPE_FEN = "R3k4/4R4/9/9/9/9/9/9/9/3K5 b - - 0 1"


def root(fen, prepare=True):
    st = P.load_position(fen)
    if prepare:
        A.prepare(st)
    return st


def run_quiesc(
    st,
    play=None,
    is_checked=False,
    ply=0,
    alpha=-C.MAX_SCORE - 2,
    beta=C.MAX_SCORE + 2,
    ctx=None,
    stack=None,
):
    """测试入口：根节点哈希写入栈后调用 `quiesc_search`。"""
    if ctx is None:
        ctx = S.new_context(hash_size=SMALL)
    if stack is None:
        stack = S.new_stack()
    if play is None:
        play = C.RED if st.side_to_move[0] == C.RED else C.BLACK
    stack.zob32[ply] = st.zob[0]
    stack.zob64[ply] = st.zob[1]
    return S.quiesc_search(st, ctx, stack, alpha, beta, ply, play, is_checked)


def new_bufs():
    return (
        np.empty(MG.MAX_MOVES, dtype=np.int32),
        np.empty(MG.MAX_MOVES, dtype=np.int32),
        np.empty(MG.MAX_MOVES, dtype=np.int32),
        np.empty(MG.MAX_MOVES, dtype=np.int32),
    )


# --------------------------------------------------------------------------
# Stack 布局
# --------------------------------------------------------------------------


def test_new_stack_layout():
    stack = S.new_stack()
    assert S.Stack._fields == ("zob32", "zob64", "is_eat", "chk", "is_null", "pv")
    assert stack.zob32.shape == (68,) and stack.zob32.dtype == np.int64
    assert stack.zob64.shape == (68,) and stack.zob64.dtype == np.int64
    assert stack.is_eat.shape == (68,) and stack.is_eat.dtype == np.int8
    assert stack.chk.shape == (68,) and stack.chk.dtype == np.int8
    assert stack.is_null.shape == (68,) and stack.is_null.dtype == np.int8
    assert stack.pv.shape == (68, 68) and stack.pv.dtype == np.int32
    for arr in (stack.zob32, stack.zob64, stack.is_eat, stack.chk, stack.is_null, stack.pv):
        assert not arr.any()


# --------------------------------------------------------------------------
# 评估辅助
# --------------------------------------------------------------------------


def test_fine_evaluate_counts_nodes_and_dispatches():
    ctx = S.new_context(hash_size=SMALL)
    st = root(HANGING_KNIGHT_FEN)  # 残局阶段
    v = S.fine_evaluate(st, C.RED, ctx)
    assert ctx.nodes[0] == 1
    assert v == E.evaluate(st, C.RED)
    assert v == E.evaluate_endgame(st, C.RED)

    st2 = root(MIDDLE_ASYMMETRIC_FEN)  # 中局阶段（中局/残局评估值不同）
    assert A.phase_of(st2) == A.MIDDLE_GAME
    v2 = S.fine_evaluate(st2, C.RED, ctx)
    assert ctx.nodes[0] == 2
    assert v2 == E.evaluate(st2, C.RED)
    assert v2 == E.evaluate(st2, C.RED, endgame=False)
    assert v2 != E.evaluate_endgame(st2, C.RED)


def test_rough_evaluate_is_base_score_diff():
    st = root(OPENING_FEN)
    assert S.rough_evaluate(st, C.RED) == int(st.base_score[C.RED]) - int(
        st.base_score[C.BLACK]
    )
    assert S.rough_evaluate(st, C.BLACK) == -S.rough_evaluate(st, C.RED)
    assert S.rough_evaluate(st, C.RED) == E.rough_evaluate(st, C.RED)


# --------------------------------------------------------------------------
# 长将检测
# --------------------------------------------------------------------------


def test_is_long_check_matches_same_position_without_capture_between():
    stack = S.new_stack()
    z32, z64 = 0x1234, 0x123456789ABCDEF
    stack.zob32[1] = z32
    stack.zob64[1] = z64
    stack.zob32[2] = z32
    stack.zob64[2] = z64
    stack.is_eat[1] = 0
    stack.chk[2] = 1
    assert S.is_long_check(stack, 2)


def test_is_long_check_stops_at_capture():
    stack = S.new_stack()
    z32, z64 = 0x1234, 0x123456789ABCDEF
    stack.zob32[1] = z32
    stack.zob64[1] = z64
    stack.zob32[2] = z32
    stack.zob64[2] = z64
    stack.chk[2] = 1
    # t=1 是吃子层：先比较（相等）→ True，与吃子无关
    stack.is_eat[1] = 1
    assert S.is_long_check(stack, 2)

    # t=2 哈希不同但 t=2 是吃子 → 截断返回 False
    stack2 = S.new_stack()
    stack2.zob32[1] = z32
    stack2.zob64[1] = z64
    stack2.zob32[3] = z32
    stack2.zob64[3] = z64
    stack2.is_eat[2] = 1
    stack2.chk[3] = 1
    assert not S.is_long_check(stack2, 3)


def test_is_long_check_requires_checked_flag_and_skips_root():
    stack = S.new_stack()
    stack.zob32[1] = stack.zob32[2] = 7
    stack.zob64[1] = stack.zob64[2] = 8
    # chk[2] == 0 → 不检测
    assert not S.is_long_check(stack, 2)
    # ply=1 只能看到根（ply 0），根无着法信息 → False
    stack.chk[1] = 1
    stack.zob32[0] = stack.zob32[1] = 7
    stack.zob64[0] = stack.zob64[1] = 8
    assert not S.is_long_check(stack, 1)


# --------------------------------------------------------------------------
# 和棋
# --------------------------------------------------------------------------


def test_is_draw_only_when_both_sides_lack_attackers():
    stack = S.new_stack()
    # 双方只有将（无车马炮）→ 和棋（Java 只看攻击子数，不看是否吃子）
    st = root("4k4/9/9/9/9/9/9/9/9/3K5 w - - 0 1")
    assert S.is_draw(st, stack, 0)
    # 黑方有车 → 非和棋
    st2 = root("r3k4/9/9/9/9/9/9/9/9/3K5 w - - 0 1")
    assert not S.is_draw(st2, stack, 0)


# --------------------------------------------------------------------------
# 好/坏吃子分类
# --------------------------------------------------------------------------


def test_gen_quiesc_moves_classifies_captures():
    st = root(CLASSIFY_FEN)
    ctx = S.new_context(hash_size=SMALL)
    good_buf, good_score, general_buf, general_score = new_bufs()
    good_n, general_n = S.gen_quiesc_moves(
        st, ctx, C.RED, False, good_buf, good_score, general_buf, general_score
    )
    # 吃 e5 黑车与吃 c0 黑卒（动态值 180）都进 good，顺序按生成序（site 升序）
    assert good_n == 2
    assert good_buf[0] == C.pack_move(47, 2)
    assert good_buf[1] == C.pack_move(47, 49)
    assert good_score[1] > 0
    assert general_n == 0


def test_gen_quiesc_moves_general_holds_history_score():
    st = root(GENERAL_FEN)
    ctx = S.new_context(hash_size=SMALL)
    ctx.history[C.PIECE_KINDS[st.board[49]], 31] = 77
    good_buf, good_score, general_buf, general_score = new_bufs()
    good_n, general_n = S.gen_quiesc_moves(
        st, ctx, C.RED, False, good_buf, good_score, general_buf, general_score
    )
    # 红车 e5 吃 e6 卒（118 < 150）进 general，排序分取历史分
    assert (good_n, general_n) == (2, 1)
    assert general_buf[0] == C.pack_move(49, 31)
    assert general_score[0] == 77


def test_gen_quiesc_moves_checked_appends_all_quiet_moves():
    st = root(CHECK_ESCAPE_FEN)
    assert MG.in_check(st, C.BLACK)
    play = C.BLACK
    ctx = S.new_context(hash_size=SMALL)
    good_buf, good_score, general_buf, general_score = new_bufs()
    good_n, general_n = S.gen_quiesc_moves(
        st, ctx, play, True, good_buf, good_score, general_buf, general_score
    )
    # 黑将被将：good = 吃 e1 车；general = d0、f0 两个非吃子逃路
    assert good_n == 1
    assert good_buf[0] == C.pack_move(4, 13)
    assert general_n == 2
    quiet = {int(general_buf[i]) for i in range(general_n)}
    assert quiet == {C.pack_move(4, 3), C.pack_move(4, 5)}
    # 未被将时不生成非吃子
    good_buf2, good_score2, general_buf2, general_score2 = new_bufs()
    n2 = S.gen_quiesc_moves(
        st, ctx, C.RED, False, good_buf2, good_score2, general_buf2, general_score2
    )
    assert n2[1] == 0


# --------------------------------------------------------------------------
# 选择排序
# --------------------------------------------------------------------------


def test_select_best_is_inplace_selection_sort():
    buf = np.array([10, 20, 30, 40], dtype=np.int32)
    score = np.array([9, 9, 5, 7], dtype=np.int32)
    S._select_best(buf, score, 0, 4)
    # 等分保留靠前者（严格大于才替换）→ 不交换
    assert list(buf) == [10, 20, 30, 40]
    S._select_best(buf, score, 1, 4)
    # 从 index=1 起最大是 30/score=5？不是：score[1]=9 最大 → 不换
    assert list(buf) == [10, 20, 30, 40]
    buf2 = np.array([10, 20, 30, 40], dtype=np.int32)
    score2 = np.array([1, 9, 8, 7], dtype=np.int32)
    S._select_best(buf2, score2, 0, 4)
    assert list(buf2) == [20, 10, 30, 40]
    assert list(score2) == [9, 1, 8, 7]
    S._select_best(buf2, score2, 1, 4)
    assert list(buf2) == [20, 30, 10, 40]


# --------------------------------------------------------------------------
# quiesc_search 主流程
# --------------------------------------------------------------------------


def test_quiesc_wang_captured_returns_mate_score():
    st = root(OPENING_FEN, prepare=False)
    st.all_chess[C.BLACK_PIECES_START] = C.NOTHING
    ctx = S.new_context(hash_size=SMALL)
    assert run_quiesc(st, play=C.BLACK, ctx=ctx) == -(C.MAX_SCORE - 0)


def test_quiesc_long_check_returns_8888():
    st = root(OPENING_FEN)
    stack = S.new_stack()
    stack.zob32[1] = stack.zob32[2] = int(st.zob[0])
    stack.zob64[1] = stack.zob64[2] = int(st.zob[1])
    stack.chk[2] = 1
    ctx = S.new_context(hash_size=SMALL)
    v = run_quiesc(st, play=C.RED, is_checked=True, ply=2, ctx=ctx, stack=stack)
    assert v == C.LONG_CHECK_SCORE == 8888


def test_quiesc_ply_fuse_returns_fine_evaluate():
    st = root(OPENING_FEN)
    ctx = S.new_context(hash_size=SMALL)
    v = run_quiesc(st, play=C.RED, ply=64, ctx=ctx)
    assert v == E.evaluate(st, C.RED)
    assert ctx.nodes[0] == 1


def test_quiesc_draw_precedes_ply_fuse():
    # 双方只有将：和棋判断在深度保险丝之前（Java L178-184），不调用评估
    st = root("4k4/9/9/9/9/9/9/9/9/3K5 w - - 0 1")
    ctx = S.new_context(hash_size=SMALL)
    v = run_quiesc(st, play=C.RED, ply=64, ctx=ctx)
    assert v == C.DRAW_SCORE == 0
    assert ctx.nodes[0] == 0


def test_quiesc_long_check_precedes_draw_and_fuse():
    # 长将判断先于和棋与保险丝（Java L174-184）
    st = root("4k4/9/9/9/9/9/9/9/9/3K5 w - - 0 1")
    stack = S.new_stack()
    stack.zob32[63] = stack.zob32[64] = int(st.zob[0])
    stack.zob64[63] = stack.zob64[64] = int(st.zob[1])
    stack.is_eat[63] = 0
    ctx = S.new_context(hash_size=SMALL)
    v = run_quiesc(st, play=C.RED, is_checked=True, ply=64, ctx=ctx, stack=stack)
    assert v == C.LONG_CHECK_SCORE
    assert ctx.nodes[0] == 0


def test_quiesc_mate_returns_negative_max_score():
    st = root(MATE_FEN)
    assert MG.in_check(st, C.BLACK)
    assert len(MG.gen_legal_moves(st, C.BLACK)) == 0
    ctx = S.new_context(hash_size=SMALL)
    v = run_quiesc(st, play=C.BLACK, is_checked=True, ctx=ctx)
    assert v == -(C.MAX_SCORE - 0)


def test_quiesc_checked_searches_all_evasions():
    st = root(CHECK_ESCAPE_FEN)
    assert MG.in_check(st, C.BLACK)
    ctx = S.new_context(hash_size=SMALL)
    v = run_quiesc(st, play=C.BLACK, is_checked=True, ctx=ctx)
    # 唯一逃路是吃 e1 车 → 不是将死分，且应低于不吃（红方仍有一车）
    assert -(C.MAX_SCORE) < v < 0
    assert ctx.nodes[0] > 0


def test_quiesc_free_capture_beats_stand_pat():
    st = root(HANGING_KNIGHT_FEN)
    ctx = S.new_context(hash_size=SMALL)
    stand_pat = E.evaluate(st, C.RED)
    v = run_quiesc(st, play=C.RED, ctx=ctx)
    # 白吃马（490+）应显著高于不吃
    assert v > stand_pat + 200
    assert ctx.nodes[0] > 0


def test_quiesc_does_not_overvalue_protected_capture():
    st = root(PROTECTED_KNIGHT_FEN)
    ctx = S.new_context(hash_size=SMALL)
    stand_pat = E.evaluate(st, C.RED)
    v = run_quiesc(st, play=C.RED, ctx=ctx)
    # 吃马后被黑车吃回：静态搜索应保持 stand-pat，不高估
    assert v == stand_pat


def test_quiesc_opening_position_reasonable():
    st = root(OPENING_FEN)
    ctx = S.new_context(hash_size=SMALL)
    v = run_quiesc(st, play=C.RED, ctx=ctx)
    assert -500 < v < 500
    assert ctx.nodes[0] >= 1


def test_quiesc_stand_pat_beta_cutoff():
    st = root(HANGING_KNIGHT_FEN)
    ctx = S.new_context(hash_size=SMALL)
    stand_pat = E.evaluate(st, C.RED)
    # beta <= stand-pat → 直接返回 stand-pat
    v = run_quiesc(st, play=C.RED, alpha=stand_pat - 100, beta=stand_pat, ctx=ctx)
    assert v == stand_pat


def test_stack_handles_deep_recursion_without_overflow():
    # 深度 63 调用：内部递归最多写 stack[64]，不会越界（栈长 68）
    st = root(HANGING_KNIGHT_FEN)
    ctx = S.new_context(hash_size=SMALL)
    v = run_quiesc(st, play=C.RED, ply=63, ctx=ctx)
    assert isinstance(v, (int, np.integer))
    stack = S.new_stack()
    assert stack.zob32.shape[0] == 68
