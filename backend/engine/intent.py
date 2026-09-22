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

from __future__ import annotations

import threading

import numpy as np

from chess_engine.board import Board

__all__ = [
    "flip_side_to_move",
    "INTENT_LINE_DEPTH",
    "INTENT_RANK_DEPTH",
]

# 排名与推演线的固定深度（浅层足够表达意图，单线程秒级）。
INTENT_RANK_DEPTH = 8
INTENT_LINE_DEPTH = 8

# 展示线长度上限（ply，含对手与我方交替着法）。
LINE_PV_LIMIT = 6


def flip_side_to_move(fen):
    """返回走子方翻转后的 FEN（棋盘段不变）；复用规则引擎解析/生成。"""
    board = Board().load_fen(fen)
    clone = board.clone()
    clone.side_to_move = "black" if board.side_to_move == "red" else "red"
    return clone.to_fen()
