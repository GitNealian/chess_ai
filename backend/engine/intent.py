"""对手意图推演编排层（纯 Python，无 njit）。

设计见 docs/plans/2026-09-22-opponent-intent-design.md。零侵入约束：
只调用 engine 公开接口（load_position/prepare/search_depth/warmup）与
chess_engine 规则引擎；不修改任何搜索/评估模块。

三步推演：
1. rank：固定浅深度迭代加深后读 ctx.root_moves/root_scores（降序）；
2. threat：跳一手（翻转走子方）搜对手最佳连招；我方正被将军时降级为提示；
3. bait：诱饵着法（贪吃/随手）走完后搜对手惩罚线。

每条推演线独立 Ctx/Stack/stop（约 40MB、浅深度、独立停旗），超时用
threading.Timer 置位停旗丢弃该线；事件为 dict（由 routes 层编码 NDJSON）。
"""

from collections import Counter

import threading  # 后续任务：threading.Timer 超时停旗（Task 2）

import numpy as np  # 后续任务：stop 停旗数组 np.int8[1]（Task 2）

from chess_engine.board import BLACK, PIECE_NAMES, RED, Board
from chess_engine.move import Move
from chess_engine.notation import move_to_chinese

from engine import analysis as engine_analysis
from engine import constants as EC
from engine import search as engine_search
from engine.constants import site_to_xy, xy_to_site
from engine.position import load_position

__all__ = [
    "bait_event",
    "describe_line",
    "flip_side_to_move",
    "INTENT_LINE_DEPTH",
    "INTENT_RANK_DEPTH",
    "rank_moves",
    "select_baits",
    "threat_event",
]

# 排名与推演线的固定深度（浅层足够表达意图，单线程秒级）。
INTENT_RANK_DEPTH = 8
INTENT_LINE_DEPTH = 8

# 展示线长度上限（ply，含对手与我方交替着法）。
LINE_PV_LIMIT = 6


def flip_side_to_move(fen):
    """返回走子方翻转后的 FEN（棋盘段不变）；复用规则引擎解析/生成。

    契约：入参须为合法 FEN，否则 ValueError 冒泡；输出为规则引擎标准化的
    6 段 FEN（时钟段重写为 ``- - 0 1``，不保留原值）。
    """
    board = Board().load_fen(fen)
    board.side_to_move = BLACK if board.side_to_move == RED else RED
    return board.to_fen()


def _prepare_engine(fen):
    """加载局面并做搜索前准备（动态子力/阶段/base_score）。"""
    st = load_position(fen)
    engine_analysis.prepare(st)
    return st


def _flag(stop):
    stop[0] = 1


def _search_iteration(fen, *, max_depth, stop, timeout_ms):
    """对 fen 做 depth 4..max_depth 的迭代加深；返回 (st, ctx, stack, score, mate)。

    超时：threading.Timer 置位 stop，搜索返回后若 stop 被置位则整体丢弃
    （返回 None）——与引擎「中断层不可信」契约一致。

    契约：
    - stop 必须全零传入且一次性使用：传入已置位的数组会静默返回 None
      （引擎中断契约「一旦置位不得复位」）；
    - max_depth 必须 >= EC.ROOT_START_DEPTH（4），否则迭代循环为空、
      score 保持 None，返回时 int(None) 抛 TypeError；
    - timeout_ms <= 0 视为不限时（不启动 Timer）。
    """
    engine_analysis.warmup()  # 幂等；避免首测 JIT 阻塞在计时逻辑内
    st = _prepare_engine(fen)
    ctx = engine_search.new_context()._replace(stop=stop)
    stack = engine_search.new_stack()
    stack.zob32[0] = st.zob[0]
    stack.zob64[0] = st.zob[1]
    timer = None
    if timeout_ms is not None and timeout_ms > 0:
        timer = threading.Timer(timeout_ms / 1000.0, _flag, args=(stop,))
        timer.daemon = True
        timer.start()
    try:
        score = mate = None
        for depth in range(EC.ROOT_START_DEPTH, max_depth + 1):
            if stop[0] != 0:
                return None
            score, mate = engine_search.search_depth(st, ctx, stack, depth)
            if stop[0] != 0:
                return None
        return st, ctx, stack, int(score), int(mate)
    finally:
        if timer is not None:
            timer.cancel()


def rank_moves(fen, *, depth=INTENT_RANK_DEPTH, timeout_ms=None):
    """着法排名：[(packed, score_stm)]，分数降序（走子方视角）。

    超时/中断返回 ``[]``。score_stm 为该局面走子方视角引擎分。
    无合法着法的局面（将杀/困毙后）同样返回 ``[]``，与超时降级不可
    区分——调用方按对局中局面使用即可。

    实现注记：搜索结束后的 ctx.root_moves 次序是逐着法选择排序的
    PV-first 痕迹（fail-low 着法的 root_scores 为零窗口上界），并非按
    最终分数严格降序，故读取后按分数做一次稳定重排（同分保持引擎序）。
    """
    stop = np.zeros(1, dtype=np.int8)
    result = _search_iteration(fen, max_depth=depth, stop=stop, timeout_ms=timeout_ms)
    if result is None:
        return []
    _, ctx, _, _, _ = result
    count = int(ctx.root_count[0])
    ranked = [
        (int(ctx.root_moves[i]), int(ctx.root_scores[i])) for i in range(count)
    ]
    ranked.sort(key=lambda item: item[1], reverse=True)
    return ranked


# 我方棋子价值序（loss_piece 取丢失的最大子）；相对序对齐
# engine.constants.PIECE_SCORES（兵 < 士＝象 < 马 < 炮 < 车 < 将）；
# 不入引擎常量以保持编排层纯 Python。
_PIECE_VALUE = {"K": 7, "R": 6, "C": 5, "N": 4, "A": 3, "B": 3, "P": 2}


def _packed_to_move(packed):
    """packed 着法 → Move（低 7 位起点 site、高位终点 site）。"""
    x1, y1 = site_to_xy(packed & 127)
    x2, y2 = site_to_xy(packed >> 7)
    return Move(x1, y1, x2, y2)


def _move_chinese(board, move):
    """中文记谱；非法着法/异常局面（ValueError）回退 ICCS。"""
    iccs = f"{chr(97 + move.x1)}{move.y1}{chr(97 + move.x2)}{move.y2}"
    try:
        return move_to_chinese(board, move)
    except ValueError:
        return iccs


def describe_line(packed_line, base_board, limit=LINE_PV_LIMIT):
    """packed 着法序列 → [{x1,y1,x2,y2,iccs,chinese}]（中文失败回退 ICCS）。

    逐着在副本局面推进以生成上下文相关的中文记谱；任一着 apply 失败
    （非法/异常局面）后不再尝试后续中文，仅出坐标。

    降级语义与 routes._pv_payload 对齐（评分 PV 展示在 routes 层、
    意图连招展示在此处，有意分离）。
    """
    items = []
    board = base_board.clone()
    for packed in packed_line[:limit]:
        move = _packed_to_move(int(packed))
        iccs = f"{chr(97 + move.x1)}{move.y1}{chr(97 + move.x2)}{move.y2}"
        chinese = iccs if board is None else _move_chinese(board, move)
        if board is not None:
            try:
                board.apply_move(move)
            except ValueError:
                board = None
        items.append(
            {"x1": move.x1, "y1": move.y1, "x2": move.x2, "y2": move.y2,
             "iccs": iccs, "chinese": chinese}
        )
    return items


def _my_pieces(board, side):
    # sorted 固定顺序，使 _loss_for_side 同分取最大时结果确定。
    return sorted(
        (kind, x, y) for (x, y), (s, kind) in board.grid.items() if s == side
    )


def _loss_for_side(packed_line, board, side):
    """线走完后 `side` 方丢失的最大子中文名（无失子返回 None）。

    走线前后的 `side` 方子力按数量差统计（同种多子无法区分个体）；
    起点无子等 apply 拒绝时返回 None（apply_move 不校验着法形状，
    输入须来自引擎合法着法）。

    side 取值 "red"/"black"，其余值静默按黑方处理——调用方须传小写。
    """
    before = Counter(kind for kind, _, _ in _my_pieces(board, side))
    probe = board.clone()
    for packed in packed_line:
        try:
            probe.apply_move(_packed_to_move(int(packed)))
        except ValueError:
            return None
    after = Counter(kind for kind, _, _ in _my_pieces(probe, side))
    lost = list((before - after).elements())
    if not lost:
        return None
    return PIECE_NAMES[(side, max(lost, key=lambda k: _PIECE_VALUE[k]))]


_THREAT_HINT = "你正被将军，必须应将"


def _pv_of(stack, limit=LINE_PV_LIMIT):
    """stack.pv[0] 头段独立拷贝（0 结尾，上限 limit）。"""
    pv = []
    row = stack.pv[0]
    for i in range(row.shape[0]):
        m = int(row[i])
        if m == 0 or len(pv) >= limit:
            break
        pv.append(m)
    return pv


def threat_event(fen, *, depth=INTENT_LINE_DEPTH, timeout_ms=2000):
    """底线威胁线：我方停一手（完全不理会）后对手的最佳连招。

    - 我方正被将军：无法合法停一手，降级为提示（line 空、outcome None）；
    - 超时/中断：line 空、hint None、outcome None（静默降级）；
    - 搜索在翻转局面（走子方 = 对手）进行：mate>0 = 对手 N ply 杀我方；
    - score_red 为红方视角（对手为红取原值、对手为黑取反）；
    - loss_piece 恒 None：对手连招的威胁以 mate/score 表达，且翻转局面
      的「我方」语义与原局面相反，不在此统计失子；
    - 入参 fen 须为合法 FEN（非法时 ValueError 冒泡，由 routes 层转
      error 事件）；
    - depth 须 ≥ 4（与 _search_iteration 契约一致）。
    """
    board = Board().load_fen(fen)
    if board.in_check(board.side_to_move):
        return {"type": "threat", "line": [], "outcome": None, "hint": _THREAT_HINT}

    flipped = flip_side_to_move(fen)
    stop = np.zeros(1, dtype=np.int8)
    result = _search_iteration(
        flipped, max_depth=depth, stop=stop, timeout_ms=timeout_ms
    )
    if result is None:
        return {"type": "threat", "line": [], "outcome": None, "hint": None}
    _, _, stack, score, mate = result
    pv = _pv_of(stack)
    opponent_is_red = board.side_to_move != RED  # 我方非红 → 对手红
    my_mated = mate > 0
    outcome = {
        "mate": int(mate) if my_mated else None,
        "loss_piece": None,
        "score_red": int(score if opponent_is_red else -score),
    }
    line = describe_line(pv, Board().load_fen(flipped), limit=LINE_PV_LIMIT)
    return {"type": "threat", "line": line, "outcome": outcome, "hint": None}


# 只在排名前 N 内找诱饵（排名太靠后的着法无诱骗性）。
_BAIT_WINDOW = 8


def _board_capture_flags(fen, packed_list):
    """在根局面判定各着法是否吃子（规则引擎 piece_at，结构信号）。"""
    board = Board().load_fen(fen)
    flags = {}
    for packed in packed_list:
        move = _packed_to_move(packed)
        flags[packed] = board.piece_at(move.x2, move.y2) is not None
    return flags


def select_baits(fen, ranked, *, max_baits=2):
    """从排名挑诱饵着法：吃子优先（贪吃），再补靠前的非吃子（随手）。

    - `ranked`：`rank_moves` 输出（降序），首名视为正着不入选；
    - 不比较分数差：root_scores 对 fail-low 着法是零窗口上界，分差不可靠
      （Task 2 实测），「诱人程度」以吃子结构信号表达；
    - 只看排名前 `_BAIT_WINDOW`；候选不足按实际数量产出。
    """
    if len(ranked) < 2:
        return []
    window = ranked[1:_BAIT_WINDOW + 1]
    is_capture = _board_capture_flags(fen, [packed for packed, _ in window])
    baits = []
    for packed, _ in window:
        if is_capture[packed]:
            baits.append({"packed": packed, "reason": "贪吃"})
            if len(baits) >= max_baits:
                return baits
    for packed, _ in window:
        if all(b["packed"] != packed for b in baits):
            baits.append({"packed": packed, "reason": "随手"})
            if len(baits) >= max_baits:
                return baits
    return baits


def bait_event(fen, bait, *, depth=INTENT_LINE_DEPTH, timeout_ms=2000):
    """诱饵线：我方走诱饵着法后对手的最佳惩罚连招。

    - 搜索局面 = 我方走诱饵后（走子方 = 对手），PV 首着即对手惩罚着手；
    - mate>0 = 对手 N ply 内杀我方；score_red 统一红方视角；
    - loss_piece：对比走线前后**我方**（原局面走子方）子力；
    - 超时/中断：line 空、outcome 全 None（静默降级）；
    - `bait` 来自 `select_baits`（含 packed/reason）。
    """
    root = Board().load_fen(fen)
    my_side = root.side_to_move
    move = _packed_to_move(int(bait["packed"]))
    probe = root.clone()
    probe.apply_move(move)  # 诱饵来自合法排名着法；apply 失败应尽早暴露
    bait_fen = probe.to_fen()

    iccs = f"{chr(97 + move.x1)}{move.y1}{chr(97 + move.x2)}{move.y2}"
    payload = {
        "type": "bait",
        "bait": {
            "x1": move.x1, "y1": move.y1, "x2": move.x2, "y2": move.y2,
            "iccs": iccs,
            "chinese": _move_chinese(root, move),
            "reason": bait["reason"],
        },
        "line": [],
        "outcome": {"mate": None, "loss_piece": None, "score_red": None},
    }
    stop = np.zeros(1, dtype=np.int8)
    result = _search_iteration(
        bait_fen, max_depth=depth, stop=stop, timeout_ms=timeout_ms
    )
    if result is None:
        return payload
    _, _, stack, score, mate = result
    pv = _pv_of(stack)
    opponent_is_red = my_side != RED
    payload["outcome"]["score_red"] = int(score if opponent_is_red else -score)
    if mate > 0:
        payload["outcome"]["mate"] = int(mate)
    line_board = Board().load_fen(bait_fen)
    payload["outcome"]["loss_piece"] = _loss_for_side(pv, line_board, my_side)
    payload["line"] = describe_line(pv, line_board, limit=LINE_PV_LIMIT)
    return payload
