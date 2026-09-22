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

import threading  # 后续任务：threading.Timer 超时停旗（Task 2）

import numpy as np  # 后续任务：stop 停旗数组 np.int8[1]（Task 2）

from chess_engine.board import BLACK, RED, Board

from engine import analysis as engine_analysis
from engine import constants as EC
from engine import search as engine_search
from engine.position import load_position

__all__ = [
    "flip_side_to_move",
    "INTENT_LINE_DEPTH",
    "INTENT_RANK_DEPTH",
    "rank_moves",
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
    """
    engine_analysis.warmup()  # 幂等；避免首测 JIT 阻塞在计时逻辑内
    st = _prepare_engine(fen)
    ctx = engine_search.new_context()
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
