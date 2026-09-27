"""搜索后端抽象层：统一 numba（njit）与 Cython（AOT）两套引擎。

设计（见 docs/plans/cython-45-api 计划）：
- 后端选择：`ENGINE_BACKEND=cython|numba`；缺省优先 cython（扩展可用时）。
- 会话接口：`create(fen, ...) -> Session`；`Session.search_layer(depth)` 逐层
  搜索并返回 `(score, mate)`；Lazy SMP 由 `Session.spawn_worker` 派生共享
  TT/停旗的 worker。
- Cython 后端的只读表首次使用时经 `_ensure_cython_tables` 注入（幂等、加锁）。
- 停旗：`Session.request_stop()` 置位；多线程共享由 worker 的 `attach_stop`
  保证（Cython）/共享数组保证（numba）。
"""

import logging
import math
import os
import threading

from . import constants as C
from .position import load_position

_log = logging.getLogger(__name__)

__all__ = ["create", "resolve_backend"]

_CYTHON_READY = False
_CYTHON_LOCK = threading.Lock()
_CYTHON_AVAILABLE = None


def _cython_available():
    global _CYTHON_AVAILABLE
    if _CYTHON_AVAILABLE is None:
        try:
            from . import _cycore  # noqa: F401

            _CYTHON_AVAILABLE = True
        except Exception:  # noqa: BLE001 - 扩展缺失时回退 numba
            _CYTHON_AVAILABLE = False
    return _CYTHON_AVAILABLE


def _ensure_cython_tables():
    """把 Python 构建的只读表注入 Cython 模块（幂等）。"""
    global _CYTHON_READY
    if _CYTHON_READY:
        return
    with _CYTHON_LOCK:
        if _CYTHON_READY:
            return
        import numpy as _np

        from . import _cycore, eval_tables as ET, tables, zobrist

        def ac(a):
            return _np.ascontiguousarray(a)

        _cycore.init_tables(
            ac(zobrist.ZOB64),
            ac(zobrist.ZOB32),
            ac(ET.MIDDLE_RED),
            ac(ET.MIDDLE_BLACK),
            ac(ET.END_RED),
            ac(ET.END_BLACK),
            ac(C.PIECE_ROLES),
            ac(C.ATTACK_DEFENSE_INDEX),
            ac(tables.MASK_SITE_LO),
            ac(tables.MASK_SITE_HI),
        )
        _cycore.init_eval_tables(
            {
                "CHARIOT_ATTACK_ROW_LO": ac(tables.CHARIOT_ATTACK_ROW_LO),
                "CHARIOT_ATTACK_ROW_HI": ac(tables.CHARIOT_ATTACK_ROW_HI),
                "CHARIOT_ATTACK_COL_LO": ac(tables.CHARIOT_ATTACK_COL_LO),
                "CHARIOT_ATTACK_COL_HI": ac(tables.CHARIOT_ATTACK_COL_HI),
                "MOVE_CHARIOT_GUN_ROW_LO": ac(tables.MOVE_CHARIOT_GUN_ROW_LO),
                "MOVE_CHARIOT_GUN_ROW_HI": ac(tables.MOVE_CHARIOT_GUN_ROW_HI),
                "MOVE_CHARIOT_GUN_COL_LO": ac(tables.MOVE_CHARIOT_GUN_COL_LO),
                "MOVE_CHARIOT_GUN_COL_HI": ac(tables.MOVE_CHARIOT_GUN_COL_HI),
                "GUN_ATTACK_ROW_LO": ac(tables.GUN_ATTACK_ROW_LO),
                "GUN_ATTACK_ROW_HI": ac(tables.GUN_ATTACK_ROW_HI),
                "GUN_ATTACK_COL_LO": ac(tables.GUN_ATTACK_COL_LO),
                "GUN_ATTACK_COL_HI": ac(tables.GUN_ATTACK_COL_HI),
                "GUN_FAKE_ATTACK_ROW_LO": ac(tables.GUN_FAKE_ATTACK_ROW_LO),
                "GUN_FAKE_ATTACK_ROW_HI": ac(tables.GUN_FAKE_ATTACK_ROW_HI),
                "GUN_FAKE_ATTACK_COL_LO": ac(tables.GUN_FAKE_ATTACK_COL_LO),
                "GUN_FAKE_ATTACK_COL_HI": ac(tables.GUN_FAKE_ATTACK_COL_HI),
                "GUN_MORE_REST_ATTACK_ROW_LO": ac(tables.GUN_MORE_REST_ATTACK_ROW_LO),
                "GUN_MORE_REST_ATTACK_ROW_HI": ac(tables.GUN_MORE_REST_ATTACK_ROW_HI),
                "GUN_MORE_REST_ATTACK_COL_LO": ac(tables.GUN_MORE_REST_ATTACK_COL_LO),
                "GUN_MORE_REST_ATTACK_COL_HI": ac(tables.GUN_MORE_REST_ATTACK_COL_HI),
                "KNIGHT_LEG_LO": ac(tables.KNIGHT_LEG_LO),
                "KNIGHT_LEG_HI": ac(tables.KNIGHT_LEG_HI),
                "KNIGHT_ATTACK_LIMIT_LO": ac(tables.KNIGHT_ATTACK_LIMIT_LO),
                "KNIGHT_ATTACK_LIMIT_HI": ac(tables.KNIGHT_ATTACK_LIMIT_HI),
                "ELEPHANT_LEG_LO": ac(tables.ELEPHANT_LEG_LO),
                "ELEPHANT_LEG_HI": ac(tables.ELEPHANT_LEG_HI),
                "ELEPHANT_ATTACK_LIMIT_LO": ac(tables.ELEPHANT_ATTACK_LIMIT_LO),
                "ELEPHANT_ATTACK_LIMIT_HI": ac(tables.ELEPHANT_ATTACK_LIMIT_HI),
                "KING_TARGET_LO": ac(tables.KING_TARGET_LO),
                "KING_TARGET_HI": ac(tables.KING_TARGET_HI),
                "GUARD_TARGET_LO": ac(tables.GUARD_TARGET_LO),
                "GUARD_TARGET_HI": ac(tables.GUARD_TARGET_HI),
                "SOLDIER_TARGET_LO": ac(tables.SOLDIER_TARGET_LO),
                "SOLDIER_TARGET_HI": ac(tables.SOLDIER_TARGET_HI),
                "KING_CHECKED_SOLDIER_LO": ac(tables.KING_CHECKED_SOLDIER_LO),
                "KING_CHECKED_SOLDIER_HI": ac(tables.KING_CHECKED_SOLDIER_HI),
                "KNIGHT_TARGET_LO": ac(tables.KNIGHT_TARGET_LO),
                "KNIGHT_TARGET_HI": ac(tables.KNIGHT_TARGET_HI),
                "CHARIOT_GUN_MOBILITY_ROW": ac(tables.CHARIOT_GUN_MOBILITY_ROW),
                "CHARIOT_GUN_MOBILITY_COL": ac(tables.CHARIOT_GUN_MOBILITY_COL),
                "ATTACK_PARTITION_SCORE": ac(ET.ATTACK_PARTITION_SCORE),
                "DEFENSE_PARTITION_SCORE": ac(ET.DEFENSE_PARTITION_SCORE),
                "MIN_MOBILITY": ac(ET.MIN_MOBILITY),
                "MOBILITY_REWARDS": ac(ET.MOBILITY_REWARDS),
                "GUARD_ELEPHANT_NUM_SCORE": ac(ET.GUARD_ELEPHANT_NUM_SCORE),
                "GUN_NUM_SCORE_DEPEND_GUARD": ac(ET.GUN_NUM_SCORE_DEPEND_GUARD),
                "KNIGHT_NUM_SCORE_DEPEND_GUARD": ac(ET.KNIGHT_NUM_SCORE_DEPEND_GUARD),
                "ROLE_PARTITION_SITE": ac(ET.ROLE_PARTITION_SITE),
                "SOLDIERS_PROTECTED": ac(ET.SOLDIERS_PROTECTED),
                "GUN_OPPT_NOT_GUARD": ac(ET.GUN_OPPT_NOT_GUARD),
                "KNIGHT_OPPT_NOT_GUARD": ac(ET.KNIGHT_OPPT_NOT_GUARD),
                "PIECE_KINDS": ac(C.PIECE_KINDS),
                "DANGER_MARGIN_LO": ac(tables.DANGER_MARGIN_LO),
                "DANGER_MARGIN_HI": ac(tables.DANGER_MARGIN_HI),
            }
        )
        _CYTHON_READY = True


def resolve_backend():
    name = os.environ.get("ENGINE_BACKEND", "").strip().lower()
    if name == "numba":
        return "numba"
    if name == "cython":
        return "cython"
    return "cython" if _cython_available() else "numba"


def _hash_pow(hash_size):
    if hash_size is None:
        return 19
    return int(round(math.log2(hash_size)))


def create(fen, *, stop=None, hash_size=None):
    """创建主搜索会话（后端按 resolve_backend）。"""
    from . import analysis as _analysis

    if hash_size is not None and (hash_size <= 0 or hash_size & (hash_size - 1)):
        raise ValueError("hash_size 必须是 2 的幂")
    st = load_position(fen)
    _analysis.prepare(st)
    backend = resolve_backend()
    if backend == "cython":
        _ensure_cython_tables()
        return _CythonSession(st, hash_size, fen)
    return _NumbaSession(st, stop, hash_size, fen)


class _NumbaSession:
    def __init__(self, st, stop, hash_size, fen):
        import numpy as np

        from . import search as _search

        self._search = _search
        self.st = st
        self.fen = fen
        self.stop = stop if stop is not None else np.zeros(1, dtype=np.int8)
        self.ctx = (
            _search.new_context()
            if hash_size is None
            else _search.new_context(hash_size=hash_size)
        )
        self.ctx = self.ctx._replace(stop=self.stop)
        self.stack = _search.new_stack()
        self.stack.zob32[0] = st.zob[0]
        self.stack.zob64[0] = st.zob[1]

    def search_layer(self, depth):
        score, mate = self._search.search_depth(
            self.st, self.ctx, self.stack, depth
        )
        return int(score), int(mate)

    def pv(self, limit):
        from .analysis import _copy_pv

        return _copy_pv(self.stack)

    def nodes(self):
        return int(self.ctx.nodes[0])

    def ranked(self):
        count = int(self.ctx.root_count[0])
        return [
            (int(self.ctx.root_moves[i]), int(self.ctx.root_scores[i]))
            for i in range(count)
        ]

    def side(self):
        return int(self.st.side_to_move[0])

    def is_stopped(self):
        return int(self.stop[0])

    def request_stop(self):
        self.stop[0] = 1

    def spawn_worker(self, first_depth):
        return _NumbaWorker(self.fen, self.ctx, self.stop, first_depth)

    def close(self):
        del self.ctx, self.stack


class _NumbaWorker:
    def __init__(self, fen, shared_ctx, stop, first_depth):
        from . import search as _search

        self._search = _search
        self.first_depth = first_depth
        self.fen = fen
        self.ctx = _search.new_worker_context(shared_ctx, stop)
        self.stack = _search.new_stack()
        self.st = None

    def _load(self):
        from . import analysis as _analysis

        self.st = load_position(self.fen)
        _analysis.prepare(self.st)
        self.stack.zob32[0] = self.st.zob[0]
        self.stack.zob64[0] = self.st.zob[1]

    def run(self, max_depth):
        self._load()
        depth = self.first_depth
        while depth <= max_depth:
            self._search.search_depth(self.st, self.ctx, self.stack, depth)
            depth += 1

    def close(self):
        del self.ctx, self.stack


class _CythonSession:
    def __init__(self, st, hash_size, fen):
        from . import _cycore

        self._cycore = _cycore
        self.fen = fen
        self.s = _cycore.Searcher(_hash_pow(hash_size))
        self.s.load(st)

    def search_layer(self, depth):
        score, mate = self.s.search_layer(depth)
        return int(score), int(mate)

    def pv(self, limit):
        return self.s.get_pv(limit)

    def nodes(self):
        return int(self.s.get_nodes())

    def ranked(self):
        return self.s.get_ranked()

    def side(self):
        return int(self.s.get_side())

    def is_stopped(self):
        return int(self.s.is_stopped())

    def request_stop(self):
        self.s.request_stop()

    def spawn_worker(self, first_depth):
        return _CythonWorker(self.s, self.fen, first_depth)

    def close(self):
        del self.s


class _CythonWorker:
    def __init__(self, main_s, fen, first_depth):
        self.main = main_s
        self.fen = fen
        self.first_depth = first_depth
        self.s = None

    def run(self, max_depth):
        from . import _cycore, analysis as _analysis

        st = load_position(self.fen)
        _analysis.prepare(st)
        self.s = _cycore.Searcher(1)
        self.s.load(st)
        self.s.attach_tt(self.main)
        self.s.attach_stop(self.main)
        depth = self.first_depth
        while depth <= max_depth:
            self.s.search_layer(depth)
            depth += 1

    def close(self):
        del self.s
