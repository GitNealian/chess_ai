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

# 我方正被将军的局面：黑车 f0 将军红王 d0、轮红（红应将中）。
MY_IN_CHECK = "4k4/9/9/9/9/9/9/9/9/3K1r3 w - - 0 1"


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
    assert item["chinese"] != item["iccs"], "中文记谱应真正生成而非回退 ICCS"


def test_describe_line_limit_truncates():
    from engine.constants import xy_to_site
    from engine.intent import describe_line

    # 手工构造初始局面两个合法 packed（src | dest << 7）：
    # 红炮 (7,2)→(4,2) 炮二平五、黑炮 (7,7)→(4,7) 炮8平5。
    red_cannon = xy_to_site(7, 2) | (xy_to_site(4, 2) << 7)
    black_cannon = xy_to_site(7, 7) | (xy_to_site(4, 7) << 7)
    board = Board().load_fen(INITIAL)
    full = describe_line([red_cannon, black_cannon], board)
    assert len(full) == 2
    assert full[0]["chinese"] == "炮二平五"
    assert full[1]["chinese"] != full[1]["iccs"]
    assert len(describe_line([red_cannon, black_cannon], board, limit=1)) == 1


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


def test_loss_for_side_picks_most_valuable_among_multiple():
    from engine.constants import xy_to_site
    from engine.intent import _loss_for_side

    # 最小局面：红车 a0 连走两着先吃黑士 a2 再吃黑兵 a9——
    # 黑同丢[士,兵]，价值序对齐 PIECE_SCORES 后应报更贵的「士」。
    fen = "p3k4/9/9/9/9/9/9/a8/9/R3K4 w - - 0 1"
    board = Board().load_fen(fen)
    take_advisor = xy_to_site(0, 0) | (xy_to_site(0, 2) << 7)
    take_pawn = xy_to_site(0, 2) | (xy_to_site(0, 9) << 7)
    assert _loss_for_side(
        packed_line=[take_advisor, take_pawn], board=board, side="black"
    ) == "士"


def test_loss_for_side_returns_none_on_empty_source():
    from engine.constants import xy_to_site
    from engine.intent import _loss_for_side

    board = Board().load_fen(INITIAL)
    # 起点取初始局面中路空点 (4,5)：apply_move 抛 ValueError → 返回 None。
    packed = xy_to_site(4, 5) | (xy_to_site(4, 8) << 7)
    assert _loss_for_side(packed_line=[packed], board=board, side="black") is None


def test_threat_reports_mate_when_ignoring():
    from engine.intent import threat_event

    # 我方（黑）停一手 → 红连招杀黑（spike 实测 mate=3）。
    event = threat_event(STM_MATED_IN_FOUR, depth=6, timeout_ms=30000)
    assert event["type"] == "threat"
    assert event["hint"] is None
    assert event["outcome"]["mate"] == 3  # 原局面黑 4-ply 被杀；停一手后红先走，3-ply 即杀（spike 实测）
    assert event["line"], "应产出对手杀线"
    assert event["outcome"]["score_red"] > 9000  # 红方视角将杀分（实测 9996）


def test_threat_downgrades_when_in_check():
    from engine.intent import threat_event

    event = threat_event(MY_IN_CHECK, depth=6, timeout_ms=30000)
    assert event["line"] == []
    assert event["outcome"] is None
    assert event["hint"] == "你正被将军，必须应将"


def test_threat_timeout_returns_degraded():
    from engine.intent import threat_event

    event = threat_event(INITIAL, depth=8, timeout_ms=1)
    assert event["type"] == "threat"
    assert event["line"] == []
    assert event["outcome"] is None
    assert event["hint"] is None  # 超时静默降级


def test_threat_without_mate_reports_scored_line():
    from engine.intent import threat_event

    event = threat_event(INITIAL, depth=6, timeout_ms=30000)
    assert event["type"] == "threat"
    assert event["hint"] is None
    assert event["outcome"] is not None
    assert event["outcome"]["mate"] is None  # 初始局面无杀
    assert abs(event["outcome"]["score_red"]) < 9000
    assert event["line"]  # 有威胁线


def test_select_baits_prefers_captures():
    from engine.constants import xy_to_site
    from engine.intent import select_baits

    # 黑王 d9、黑车 c6、红车 c0、红王 e0（无照面）；红吃车着法不在排名首位
    fen = "3k5/9/9/2r6/9/9/9/9/9/2R1K4 w - - 0 1"
    best = xy_to_site(4, 0) | (xy_to_site(4, 1) << 7)    # 王 e0→e1（假想最佳）
    capture = xy_to_site(2, 0) | (xy_to_site(2, 6) << 7)  # 车 c0→c6 吃车
    quiet = xy_to_site(2, 0) | (xy_to_site(2, 3) << 7)    # 车 c0→c3 空移
    ranked = [(best, 30), (capture, -80), (quiet, -120)]
    baits = select_baits(fen, ranked, max_baits=2)
    assert baits[0] == {"packed": capture, "reason": "贪吃"}
    assert baits[1] == {"packed": quiet, "reason": "随手"}
    assert all(b["packed"] != best for b in baits)  # 正着不入选


def test_select_baits_window_includes_rank_eighth():
    from engine.constants import xy_to_site
    from engine.intent import select_baits

    # 黑王 d9、黑车 c6、红车 c0、红王 e0（无照面）。红方合法非吃子着法
    # 有车 c0→c1..c5、车 c0→a0/b0/d0、王 e0→e1/f0/f1（d0/d1 与黑王照面
    # 非法、c0→c6 是吃子），从中取 9 项构造排名：best + 8 个 fillers。
    # ranked[8]（排名第 8 的非最佳着法）修复前（窗口 7 候选）不入窗，
    # 修复后（8 候选）应作为「随手」入选。
    fen = "3k5/9/9/2r6/9/9/9/9/9/2R1K4 w - - 0 1"
    best = xy_to_site(2, 0) | (xy_to_site(2, 1) << 7)              # 车 c0→c1
    fillers = [
        xy_to_site(2, 0) | (xy_to_site(2, y) << 7) for y in (2, 3, 4, 5)
    ] + [
        xy_to_site(2, 0) | (xy_to_site(x, 0) << 7) for x in (0, 1, 3)
    ] + [
        xy_to_site(4, 0) | (xy_to_site(4, 1) << 7),  # 王 e0→e1
    ]
    assert len(fillers) == 8
    ranked = [(best, 30)] + [(m, -10 - i) for i, m in enumerate(fillers)]
    baits = select_baits(fen, ranked, max_baits=8)
    assert {"packed": fillers[-1], "reason": "随手"} in baits


def test_select_baits_skips_when_too_few_moves():
    from engine.intent import select_baits

    # 排名不足 2 个 → 无诱饵
    assert select_baits("4k4/9/9/9/9/9/9/9/9/4K4 w - - 0 1", [(123, 0)], max_baits=2) == []


def test_bait_event_reports_punishment_structure():
    from engine.intent import bait_event, rank_moves, select_baits

    # 初始局面无吃子着法 → 诱饵为「随手」（ranked[1]）
    ranked = rank_moves(INITIAL, depth=4, timeout_ms=30000)
    baits = select_baits(INITIAL, ranked, max_baits=1)
    assert len(baits) == 1 and baits[0]["reason"] == "随手"
    event = bait_event(INITIAL, baits[0], depth=4, timeout_ms=30000)
    assert event["type"] == "bait"
    assert event["bait"]["reason"] == "随手"
    assert event["bait"]["chinese"] != ""
    assert isinstance(event["line"], list)
    assert set(event["outcome"]) == {"mate", "loss_piece", "score_red"}


def test_bait_event_timeout_degrades():
    from engine.intent import bait_event, rank_moves, select_baits

    ranked = rank_moves(INITIAL, depth=4, timeout_ms=30000)
    bait = {"packed": ranked[1][0], "reason": "随手"}
    event = bait_event(INITIAL, bait, depth=6, timeout_ms=1)
    assert event["line"] == []
    assert event["outcome"] == {"mate": None, "loss_piece": None, "score_red": None}
