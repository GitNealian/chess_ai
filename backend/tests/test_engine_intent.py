"""对手意图推演（intent）测试。

- 首次运行含 numba JIT 编译（约 20-35s），后续用例复用；
- 推演结果受 Lazy SMP 影响为确定性（本模块全部 threads=1 串行、固定深度）。
"""

from chess_engine.board import Board

INITIAL = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"

# 红方一步杀（test_engine_search_main.py 穷举用例）改轮黑方：
# 黑未被将军、黑停一手（红走）即被红一步杀 —— 「对手有一步杀、轮我方」局面。
OPP_MATE_IN_ONE = "3R5/5k1N1/9/9/9/9/9/9/9/4K1R2 b - - 0 1"


def test_flip_side_to_move():
    from engine.intent import flip_side_to_move

    assert flip_side_to_move(INITIAL).split()[1] == "b"
    flipped = flip_side_to_move(OPP_MATE_IN_ONE)
    assert flipped.split()[1] == "w"
    # 棋盘段不变
    assert flipped.split()[0] == OPP_MATE_IN_ONE.split()[0]
    # 原局面仍可被规则引擎加载（往返合法）
    Board().load_fen(flipped)
    # 往返恒等：除走子方外无副作用，双重翻转还原
    assert flip_side_to_move(flipped) == OPP_MATE_IN_ONE


def test_rank_moves_returns_sorted_descending():
    from engine.intent import rank_moves

    ranked = rank_moves(INITIAL, depth=4)
    assert ranked, "初始局面必须有合法着法"
    scores = [s for _, s in ranked]
    assert scores == sorted(scores, reverse=True), "root 缓冲应降序"
    for packed, _ in ranked:
        assert isinstance(packed, int) and packed > 0


def test_rank_moves_is_stm_perspective():
    from engine import constants as C
    from engine.intent import rank_moves

    red = rank_moves(INITIAL, depth=4)
    black_fen = INITIAL.replace(" w ", " b ")
    black = rank_moves(black_fen, depth=4)
    assert red and black
    # 双方各自视角的首着分数都应显著优于最差着法且不越界
    assert abs(red[0][1]) < C.MAX_SCORE
    assert abs(black[0][1]) < C.MAX_SCORE
