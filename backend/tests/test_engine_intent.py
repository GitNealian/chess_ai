"""对手意图推演（intent）测试。

- 首次运行含 numba JIT 编译（约 20-35s），后续用例复用；
- 推演结果受 Lazy SMP 影响为确定性（本模块全部 threads=1 串行、固定深度）。
"""

from chess_engine.board import Board

INITIAL = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"

# 轮黑方的对称局面（禁止字符串 replace 变换，直接写全量 FEN）。
INITIAL_BLACK = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR b - - 0 1"

# 红方一步杀（test_engine_search_main.py 穷举用例）改轮黑方：
# 黑未被将军但无合法着法（将 f9 仅 e9/f8 可去，分别被红车/红马控制）——
# 困毙局面，rank_moves 对其返回 []（见 test_rank_moves_is_stm_perspective 注）。
OPP_MATE_IN_ONE = "3R5/5k1N1/9/9/9/9/9/9/9/4K1R2 b - - 0 1"

# 轮黑方被杀局面（test_engine_search_main.py MATE_CHAIN_CASES 3-ply 杀局面
# 改轮黑）：黑有 2 个合法着法、非困毙，但任意应对 4 ply 内被红强制将杀，
# 走子方视角最优分为结构性被杀分 -(MAX_SCORE-ply)。
STM_MATED_IN_FOUR = "3pk4/1R7/2N4N1/4N4/9/9/9/9/9/3K5 b - - 0 1"


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

    # 被杀方（黑）视角：最优着法分数必为结构性被杀分（负的大额 mate 分），
    # 跨机器稳定、锁死「走子方视角」符号语义
    ranked = rank_moves(STM_MATED_IN_FOUR, depth=4)
    assert ranked
    assert ranked[0][1] <= -(C.MAX_SCORE - 100)  # 走子方被将杀：-(MAX_SCORE-ply) 量级


def test_describe_line_yields_chinese_moves():
    from engine.intent import describe_line, rank_moves

    ranked = rank_moves(INITIAL, depth=4)
    board = Board().load_fen(INITIAL)
    items = describe_line([ranked[0][0]], board, limit=3)
    assert len(items) == 1
    item = items[0]
    assert set(item) == {"x1", "y1", "x2", "y2", "iccs", "chinese"}
    assert item["iccs"] != "" and item["chinese"] != ""


def test_loss_for_side_reports_capture_loss():
    from engine.constants import xy_to_site
    from engine.intent import _loss_for_side

    # 黑车 c6 与红车 c0 同列相望（c1..c5 空）：红车 c0→c6 吃车后黑方丢车。
    fen = "4k4/9/9/2r6/9/9/9/9/9/2R1K4 w - - 0 1"
    board = Board().load_fen(fen)
    src = xy_to_site(2, 0)  # 红车 c0
    dest = xy_to_site(2, 6)  # 黑车 c6
    packed = src | (dest << 7)
    assert _loss_for_side(packed_line=[packed], board=board, side="black") == "车"
    # 空线无失子
    assert _loss_for_side(packed_line=[], board=board, side="black") is None
