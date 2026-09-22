# 对手意图推演实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 新增「对手意图推演」：给定对手刚走完一步的局面，推演底线威胁线（若不理会对手的最佳连招）与诱饵分支（若我方贪吃/随手棋，对手的惩罚连招），NDJSON 流式输出，前端在评分分析之前展示。

**Architecture:** 全部新逻辑落在 `backend/engine/intent.py`（纯 Python 编排层，不写 njit），只调用现有公开接口 `load_position/prepare/search_depth/analysis.warmup`；着法排名读 `search_depth` 后的 `ctx.root_moves/root_scores`（降序现成）；每条推演线用 `search.new_worker_context(ctx, 独立stop)` 共享置换表且 root 缓冲独立，配 `threading.Timer` 超时停旗。API 端点复用 `routes/engine.py` 既有「锁 + 队列 + ping + finally 停旗」模式并与 `/analyze` 共用 `_ANALYZE_LOCK`。前端仿照 `analyzeStream` 新增 `intentStream`，意图完成后再触发现有评分分析。

**Tech Stack:** Flask NDJSON 流式、numba/numpy 引擎（只读复用）、chess_engine 规则引擎（FEN 变换与走子）、Vue 3 组件。

**设计文档:** `docs/plans/2026-09-22-opponent-intent-design.md`（含零侵入约束与边界情形）。

**零侵入红线（每个 Task 都不得违反）:**
- 不修改 `engine/search.py`、`engine/evaluate.py`、`engine/movegen.py`、`engine/position.py`、`engine/analysis.py`、`engine/bitboard.py`、`engine/tables.py`、`engine/eval_tables.py`、`engine/zobrist.py`、`engine/constants.py`、`engine/fen.py`、`chess_engine/**` 的任何已有代码；
- `routes/engine.py` 只允许**新增**端点与辅助函数，不改已有函数；
- 每个 Task 结束跑全量后端测试确认无回归。

**引擎层关键事实（已核实，勿再重新考证）:**
- `from engine import analysis as A; A.warmup()` — 幂等预热（首测 20-35s JIT，后续零开销）；任何引擎搜索前必须已预热（或接受首测编译耗时）。
- `from engine.position import load_position; from engine.analysis import prepare` — `st = load_position(fen); prepare(st)`。
- `from engine import search as S` — `ctx = S.new_context()`（约 40MB TT）；`stack = S.new_stack()`；`stack.zob32[0] = st.zob[0]; stack.zob64[0] = st.zob[1]`；`score, mate = S.search_depth(st, ctx, stack, depth)`，`score` 为**走子方视角**，`mate>0` = 走子方 N ply 内将杀对方，`mate<0` = 被将杀；同一 `ctx/stack` 连续多轮调用（depth 递增）即迭代加深且复用排序后的根着法。
- 搜索完成后：`count=int(ctx.root_count[0])`，`ctx.root_moves[:count]`（packed int32，按分数降序）与 `ctx.root_scores[:count]`（走子方视角分）。packed 着法：`src = m & 127`、`dest = m >> 7`；site→坐标用 `engine.constants.site_to_xy(site) -> (x,y)`。
- `ctx.stop` 为 `np.int8[1]`；置位后 `search_depth` 返回的 score/mate/PV **不可信必须丢弃**（中断契约，见 search.py docstring）。
- 每分支独立 root 缓冲 + 独立 stop、共享 TT：`sub_ctx = S.new_worker_context(base_ctx, stop_arr)`（校验 `stop_arr is not base_ctx.stop` 时会抛错？不会——它只要求 stop 形状/类型，且要求 `stop is base_ctx.stop` 时**报错**……注意：源码 L259 `if stop is not ctx.stop: raise` —— **传入的 stop 必须与 ctx.stop 是同一数组**，否则 ValueError。因此共享 TT 方案不可用该函数！改为每分支**完整独立** `S.new_context()`（约 40MB × 分支数，单用户可接受；TT 不共享，浅搜索代价小）。**修正：每分支 `S.new_context()` + `S.new_stack()`，stop 用各自默认 `ctx.stop`，超时由 `threading.Timer` 置 `ctx.stop[0]=1`。**
- `stack.pv[0, j]` 为从根开始的 PV（0 结尾，最多 `analysis.PV_LIMIT` 截取逻辑参照 `analysis._copy_pv`，此处自行拷贝、上限取 6）。
- 角色常量（`engine.constants`）：`SOLDIER=1..KING=7` 基础类型；红角色 = 基础值，黑角色 = 基础值 + 7；`RED=1, BLACK=0`；`MAX_SCORE=9999`；`ROOT_START_DEPTH=4`。
- 规则引擎（`chess_engine`）：`Board().load_fen(fen)`（非法抛 `ValueError`）、`board.clone()`、`board.side_to_move`（`"red"`/`"black"`，`board.py` 顶部 `RED="red", BLACK="black"`）、`board.in_check(side)`、`board.legal_moves()`、`board.apply_move(Move(x1,y1,x2,y2))`（非法抛 `ValueError`）、`board.piece_at(x,y) -> (side,kind)|None`（kind 为 `"R,N,C,K,A,B,P"` 大写字母，红同黑小写?——**load_fen 解析用大小写分方，grid 存 `(side, kind)`，kind 恒大写**）、`board.to_fen()`。
- FEN 翻转走子方：`b = Board().load_fen(fen); c = b.clone(); c.side_to_move = "black" if b.side_to_move == "red" else "red"; c.to_fen()`（`to_fen` 输出完整 6 段，第二段 w/b）。

---

### Task 1: `engine/intent.py` 骨架与 FEN 工具

**Files:**
- Create: `backend/engine/intent.py`
- Test: `backend/tests/test_engine_intent.py`

**Step 1: 写失败测试**

```python
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
```

**Step 2: 跑测试确认失败**

Run: `cd backend && .venv/bin/python -m pytest tests/test_engine_intent.py -v`
Expected: FAIL（`ModuleNotFoundError: engine.intent` 或 ImportError）

**Step 3: 最小实现**

```python
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
    "flip_side_to_move",
    "rank_moves",
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
```

**Step 4: 跑测试确认通过**

Run: `cd backend && .venv/bin/python -m pytest tests/test_engine_intent.py -v`
Expected: PASS

**Step 5: 提交**

```bash
git add backend/engine/intent.py backend/tests/test_engine_intent.py
git commit -m "feat(intent): 意图推演编排层骨架与 FEN 翻转工具"
```

---

### Task 2: 着法排名 `rank_moves`

**Files:**
- Modify: `backend/engine/intent.py`
- Test: `backend/tests/test_engine_intent.py`

**Step 1: 写失败测试**

```python
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
```

**Step 2: 跑测试确认失败**

Run: `cd backend && .venv/bin/python -m pytest tests/test_engine_intent.py -v -k rank`
Expected: FAIL（ImportError: rank_moves）

**Step 3: 实现**

在 `intent.py` 追加（`__all__` 同步加 `"rank_moves"`）：

```python
from engine import analysis as engine_analysis
from engine import constants as EC
from engine import search as engine_search
from engine.position import load_position


def _prepare_engine(fen):
    """加载局面并做搜索前准备（动态子力/阶段/base_score）。"""
    st = load_position(fen)
    engine_analysis.prepare(st)
    return st


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


def _flag(stop):
    stop[0] = 1


def rank_moves(fen, *, depth=INTENT_RANK_DEPTH, timeout_ms=None):
    """着法排名：[(packed, score_stm)]，分数降序（走子方视角）。

    超时/中断返回 `[]`。score_stm 为该局面走子方视角引擎分。
    """
    stop = np.zeros(1, dtype=np.int8)
    result = _search_iteration(fen, max_depth=depth, stop=stop, timeout_ms=timeout_ms)
    if result is None:
        return []
    _, ctx, _, _, _ = result
    count = int(ctx.root_count[0])
    return [
        (int(ctx.root_moves[i]), int(ctx.root_scores[i])) for i in range(count)
    ]
```

**Step 4: 跑测试确认通过**

Run: `cd backend && .venv/bin/python -m pytest tests/test_engine_intent.py -v -k rank`
Expected: PASS（首个用例含 JIT，约 20-35s）

**Step 5: 提交**

```bash
git add backend/engine/intent.py backend/tests/test_engine_intent.py
git commit -m "feat(intent): 着法排名（复用根着法缓冲）"
```

---

### Task 3: 线路描述与结局判定

**Files:**
- Modify: `backend/engine/intent.py`
- Test: `backend/tests/test_engine_intent.py`

**Step 1: 写失败测试**

```python
def test_describe_line_yields_chinese_moves():
    from engine.intent import describe_line, rank_moves

    ranked = rank_moves(INITIAL, depth=4)
    board = Board().load_fen(INITIAL)
    items = describe_line([ranked[0][0]], board, limit=3)
    assert len(items) == 1
    item = items[0]
    assert set(item) == {"x1", "y1", "x2", "y2", "iccs", "chinese"}
    assert item["iccs"] != "" and item["chinese"] != ""


def test_outcome_reports_capture_loss():
    from engine.intent import _loss_for_side

    # 黑车 d6 与红车 c0 同列相望：诱饵线「红车吃黑车」后黑方丢车。
    fen = "4k4/9/9/9/3r5/9/9/9/9/2R1K4 w - - 0 1"
    board = Board().load_fen(fen)
    # 红车 c0 -> c5 吃车（packed：低位 src site、高位 dest site）
    from engine.constants import xy_to_site

    src = xy_to_site(2, 0)
    dest = xy_to_site(2, 5)
    packed = src | (dest << 7)
    outcome = _loss_for_side(packed_line=[packed], board=board, side="black")
    assert outcome == "车"
    assert _loss_for_side(packed_line=[], board=board, side="black") is None
```

（注：`_loss_for_side` 接受**从根局面开始的完整着法序列**并按指定方统计失子——本用例只验证「走线、数子、报损失」机制；mate/score_red 换算在 Task 4/5 的真实搜索线上断言。）

**Step 2: 跑测试确认失败**

Run: `cd backend && .venv/bin/python -m pytest tests/test_engine_intent.py -v -k "describe or outcome"`
Expected: FAIL（ImportError）

**Step 3: 实现**

在 `intent.py` 追加：

```python
from chess_engine.move import Move
from chess_engine.notation import move_to_chinese
from engine.constants import site_to_xy, xy_to_site

# 我方棋子价值序（loss_piece 取丢失的最大子）。
_PIECE_VALUE = {"K": 7, "R": 6, "C": 5, "N": 4, "P": 3, "A": 2, "B": 1}
_ROLE_CN_RED = {"K": "帅", "A": "仕", "B": "相", "N": "马", "R": "车", "C": "炮", "P": "兵"}
_ROLE_CN_BLACK = {"K": "将", "A": "士", "B": "象", "N": "马", "R": "车", "C": "炮", "P": "卒"}


def _packed_to_move(packed):
    x1, y1 = site_to_xy(packed & 127)
    x2, y2 = site_to_xy(packed >> 7)
    return Move(x1, y1, x2, y2)


def describe_line(packed_line, base_board, limit=LINE_PV_LIMIT):
    """packed 着法序列 → [{x1,y1,x2,y2,iccs,chinese}]（中文失败回退 ICCS）。"""
    items = []
    board = base_board.clone()
    for packed in packed_line[:limit]:
        move = _packed_to_move(int(packed))
        iccs = f"{chr(97 + move.x1)}{move.y1}{chr(97 + move.x2)}{move.y2}"
        chinese = iccs
        try:
            chinese = move_to_chinese(board, move)
        except ValueError:
            pass
        try:
            board.apply_move(move)
        except ValueError:
            board = None  # 后续着法仅出坐标，不再尝试生成中文
        items.append(
            {"x1": move.x1, "y1": move.y1, "x2": move.x2, "y2": move.y2,
             "iccs": iccs, "chinese": chinese}
        )
    return items


def _my_pieces(board, side):
    return sorted(
        (kind, x, y) for (x, y), (s, kind) in board.grid.items() if s == side
    )


def _loss_for_side(packed_line, board, side):
    """线走完后 `side` 方丢失的最大子中文名（无失子返回 None）。"""
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
    role_cn = _ROLE_CN_RED if side == "red" else _ROLE_CN_BLACK
    return role_cn[max(lost, key=lambda k: _PIECE_VALUE[k])]
```

`from collections import Counter` 放模块顶部；`__all__` 增加 `"describe_line"`（`_loss_for_side` 为私有辅助，不进 `__all__`）。

**Step 4: 跑测试确认通过**

Run: `cd backend && .venv/bin/python -m pytest tests/test_engine_intent.py -v -k "describe or outcome"`
Expected: PASS

**Step 5: 提交**

```bash
git add backend/engine/intent.py backend/tests/test_engine_intent.py
git commit -m "feat(intent): 线路中文描述与失子结局判定"
```

---

### Task 4: 底线威胁线 `threat_event`

**Files:**
- Modify: `backend/engine/intent.py`
- Test: `backend/tests/test_engine_intent.py`

**Step 1: 写失败测试**

```python
def test_threat_reports_mate_when_ignoring():
    from engine.intent import threat_event

    # OPP_MATE_IN_ONE：轮黑、黑未被将军、黑停一手红一步杀。
    event = threat_event(OPP_MATE_IN_ONE, depth=6, timeout_ms=30000)
    assert event["type"] == "threat"
    assert event["hint"] is None
    assert event["outcome"]["mate"] == 1  # 我方（黑）1 ply 内被绝杀
    assert event["line"], "应产出对手杀线"
    assert event["outcome"]["score_red"] > 9000 // 2  # 红方视角大优（将杀分换算后）


def test_threat_downgrades_when_in_check():
    from engine.intent import threat_event

    # 黑车已将军红王且轮红（黑上一手将军）——我方被将军 → 降级提示。
    fen = "4k4/9/9/9/9/9/9/9/9/3r1K3 b - - 0 1"
    board = Board().load_fen(fen)
    assert board.in_check(board.side_to_move)
    event = threat_event(fen, depth=6, timeout_ms=30000)
    assert event["line"] == []
    assert event["outcome"] is None
    assert event["hint"] == "你正被将军，必须应将"


def test_threat_timeout_returns_degraded():
    from engine.intent import threat_event

    event = threat_event(INITIAL, depth=8, timeout_ms=1)
    assert event["type"] == "threat"
    assert event["line"] == []
    assert event["hint"] is None  # 超时静默：无限期挂起也无事件字段异常
```

**Step 2: 跑测试确认失败**

Run: `cd backend && .venv/bin/python -m pytest tests/test_engine_intent.py -v -k threat`
Expected: FAIL（ImportError: threat_event）

**Step 3: 实现**

在 `intent.py` 追加（`__all__` 加 `"threat_event"`）：

```python
_THREAT_HINT = "你正被将军，必须应将"


def _pv_of(stack, limit=LINE_PV_LIMIT):
    """stack.pv[0] 头段独立拷贝（0 结尾）。"""
    pv = []
    row = stack.pv[0]
    for i in range(row.shape[0]):
        m = int(row[i])
        if m == 0 or len(pv) >= limit:
            break
        pv.append(m)
    return pv


def threat_event(fen, *, depth=INTENT_LINE_DEPTH, timeout_ms=2000):
    """底线威胁线：我方停一手后对手的最佳连招。

    - 我方正被将军：无法合法停一手，降级为提示（line 空、outcome None）；
    - 超时/中断：line 空、hint None、outcome None（静默降级）；
    - score_red 换算：搜索在翻转局面进行、走子方=对手；mate>0 表示对手
      N ply 杀我方。
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
    st, ctx, stack, score, mate = result
    pv = _pv_of(stack)
    # 翻转局面走子方 = 对手；score 为对手视角 → 红方视角换算
    opponent_is_red = board.side_to_move != "red"  # 我方非红 → 对手红
    my_mated = mate > 0  # 对手视角 mate>0 = 对手将杀我方
    # threat 线只报 mate 与 score_red：loss_piece 恒 None（对手连招的
    # 威胁以分数表达；且翻转局面的「我方」语义与原局面相反，不在此统计）
    outcome = {"mate": int(mate) if my_mated else None,
               "loss_piece": None,
               "score_red": int(score if opponent_is_red else -score)}
    line = describe_line(pv, Board().load_fen(flipped), limit=LINE_PV_LIMIT)
    return {"type": "threat", "line": line, "outcome": outcome, "hint": None}
```

**Step 4: 跑测试确认通过**

Run: `cd backend && .venv/bin/python -m pytest tests/test_engine_intent.py -v -k threat`
Expected: PASS（若 `test_threat_reports_mate_when_ignoring` 的 score_red 断言过严，放宽为 `> 0` 并保留 mate==1 断言）

**Step 5: 提交**

```bash
git add backend/engine/intent.py backend/tests/test_engine_intent.py
git commit -m "feat(intent): 底线威胁线（停一手推演 + 被将军降级）"
```

---

### Task 5: 诱饵筛选 `select_baits` 与诱饵线 `bait_event`

**Files:**
- Modify: `backend/engine/intent.py`
- Test: `backend/tests/test_engine_intent.py`

**Step 1: 写失败测试**

```python
def test_select_baits_prefers_captures():
    from engine.intent import rank_moves, select_baits

    # 红车 c0 与黑车 c5 同列：红有「车吃车」着法 → 应被选为「贪吃」诱饵。
    fen = "4k4/9/9/9/3r5/9/9/9/9/2R1K4 w - - 0 1"
    ranked = rank_moves(fen, depth=4)
    baits = select_baits(fen, ranked, max_baits=2)
    assert baits, "存在吃子着法时必须产出诱饵"
    assert any(b["reason"] == "贪吃" for b in baits)
    for b in baits:
        assert b["reason"] in ("贪吃", "随手")
        assert set(b) >= {"packed", "reason"}


def test_bait_event_reports_punishment_structure():
    from engine.intent import bait_event, rank_moves, select_baits

    fen = "4k4/9/9/9/3r5/9/9/9/9/2R1K4 w - - 0 1"
    baits = select_baits(fen, rank_moves(fen, depth=4), max_baits=1)
    event = bait_event(fen, baits[0], depth=6, timeout_ms=30000)
    assert event["type"] == "bait"
    assert event["bait"]["reason"] in ("贪吃", "随手")
    assert isinstance(event["line"], list)
    assert set(event["outcome"]) == {"mate", "loss_piece", "score_red"}
```

**Step 2: 跑测试确认失败**

Run: `cd backend && .venv/bin/python -m pytest tests/test_engine_intent.py -v -k "select_baits or bait"`
Expected: FAIL（ImportError）

**Step 3: 实现**

在 `intent.py` 追加（`__all__` 加 `"select_baits", "bait_event"`）：

```python
_BAIT_LABEL = {"贪吃", "随手"}


def _board_capture_targets(fen, ranked):
    """在根局面判定哪些候选着法是吃子（用规则引擎逐个试）。"""
    board = Board().load_fen(fen)
    out = {}
    for packed, _ in ranked:
        move = _packed_to_move(packed)
        out[packed] = board.piece_at(move.x2, move.y2) is not None
    return out


def select_baits(fen, ranked, *, max_baits=2, capture_window=8):
    """从排名挑诱饵：吃子优先（贪吃），再补排名靠前的非吃子（随手）。

    - `ranked`：`rank_moves` 输出（降序），首名为正着不入选；
    - 只在排名前 `capture_window` 内找吃子着法（排名太靠后的吃子无诱骗性）；
    - 不足 `max_baits` 时按实际数量产出。
    """
    if len(ranked) < 2:
        return []
    is_capture = _board_capture_targets(fen, ranked[:capture_window])
    baits = []
    for packed, _ in ranked[1:capture_window]:
        if is_capture.get(packed):
            baits.append({"packed": packed, "reason": "贪吃"})
            if len(baits) >= max_baits:
                return baits
    for packed, _ in ranked[1:]:
        if all(b["packed"] != packed for b in baits):
            baits.append({"packed": packed, "reason": "随手"})
            if len(baits) >= max_baits:
                return baits
    return baits


def bait_event(fen, bait, *, depth=INTENT_LINE_DEPTH, timeout_ms=2000):
    """诱饵线：我方走诱饵后对手的最佳惩罚连招。

    - 搜索局面 = 我方走诱饵后（轮对手），PV 首着即对手惩罚着手；
    - mate>0 = 对手 N ply 内杀我方；score_red 为红方视角；
    - loss_piece：对比走线前后**我方**子力（诱饵局面走子方是对手，
      我方 = 原局面走子方），丢的最大子中文名。
    """
    root = Board().load_fen(fen)
    my_side = root.side_to_move
    move = _packed_to_move(bait["packed"])
    probe = root.clone()
    probe.apply_move(move)  # 诱饵着法来自合法排名，不捕获 ValueError 以尽早暴露
    bait_fen = probe.to_fen()

    stop = np.zeros(1, dtype=np.int8)
    result = _search_iteration(
        bait_fen, max_depth=depth, stop=stop, timeout_ms=timeout_ms
    )
    payload = {
        "type": "bait",
        "bait": {
            "x1": move.x1, "y1": move.y1, "x2": move.x2, "y2": move.y2,
            "iccs": f"{chr(97 + move.x1)}{move.y1}{chr(97 + move.x2)}{move.y2}",
            "reason": bait["reason"],
        },
        "line": [],
        "outcome": {"mate": None, "loss_piece": None, "score_red": None},
    }
    if result is None:
        return payload
    st, ctx, stack, score, mate = result
    pv = _pv_of(stack)
    # score 为对手（bait_fen 走子方）视角 → 红方视角换算
    opponent_is_red = my_side != "red"
    payload["outcome"]["score_red"] = int(score if opponent_is_red else -score)
    if mate > 0:
        payload["outcome"]["mate"] = int(mate)
    # 我方失子：线从 bait_fen 出发，我方 = 原局面走子方
    line_board = Board().load_fen(bait_fen)
    payload["outcome"]["loss_piece"] = _loss_for_side(
        packed_line=pv, board=line_board, side=my_side
    )
    payload["line"] = describe_line(pv, line_board, limit=LINE_PV_LIMIT)
    return payload
```

Task 3 已提供 `_loss_for_side`，此处直接使用；`Counter` 已在模块顶部导入。

**Step 4: 跑测试确认通过**

Run: `cd backend && .venv/bin/python -m pytest tests/test_engine_intent.py -v`
Expected: PASS

**Step 5: 提交**

```bash
git add backend/engine/intent.py backend/tests/test_engine_intent.py
git commit -m "feat(intent): 诱饵筛选与惩罚线推演"
```

---

### Task 6: 总编排 `intent_events`

**Files:**
- Modify: `backend/engine/intent.py`
- Test: `backend/tests/test_engine_intent.py`

**Step 1: 写失败测试**

```python
def test_intent_events_sequence():
    from engine.intent import intent_events

    events = list(
        intent_events(OPP_MATE_IN_ONE, max_baits=1, per_line_timeout_ms=30000)
    )
    kinds = [e["type"] for e in events]
    assert kinds[0] == "rank"
    assert "threat" in kinds
    assert kinds[-1] == "bait" or kinds[-1] == "threat"
    rank = events[0]
    assert rank["best"] and rank["list"]
    assert all(set(m) >= {"x1", "y1", "x2", "y2", "iccs", "chinese", "score_stm"} for m in rank["list"])
    # threat 在 rank 之后、bait 之前
    assert kinds.index("threat") < len(kinds) - 1 or kinds[-1] == "threat"


def test_intent_events_rank_scores_are_stm():
    from engine.intent import intent_events

    events = list(intent_events(INITIAL, max_baits=1, per_line_timeout_ms=30000))
    rank = events[0]
    assert rank["list"][0]["score_stm"] >= rank["list"][-1]["score_stm"]
```

**Step 2: 跑测试确认失败**

Run: `cd backend && .venv/bin/python -m pytest tests/test_engine_intent.py -v -k intent_events`
Expected: FAIL（ImportError）

**Step 3: 实现**

在 `intent.py` 追加（`__all__` 加 `"intent_events"`）：

```python
_RANK_LIST_LIMIT = 5


def _move_payload(packed, board):
    """单着法 → 坐标 + ICCS + 中文（不走子，仅描述起点局面下的该着）。"""
    move = _packed_to_move(int(packed))
    iccs = f"{chr(97 + move.x1)}{move.y1}{chr(97 + move.x2)}{move.y2}"
    try:
        chinese = move_to_chinese(board, move)
    except ValueError:
        chinese = iccs
    return {"x1": move.x1, "y1": move.y1, "x2": move.x2, "y2": move.y2,
            "iccs": iccs, "chinese": chinese}


def intent_events(fen, *, max_baits=2, rank_depth=INTENT_RANK_DEPTH,
                  line_depth=INTENT_LINE_DEPTH, per_line_timeout_ms=2000,
                  stop=None):
    """意图推演总编排：依次产出 rank → threat → bait* 事件 dict。

    - `stop`：可选 np.int8[1]，置位后当前线完成即不再开始后续线（已产出
      事件保留）；各线内部独立 stop（超时 Timer），二者取或；
    - 任何单线失败不中断整流：rank 失败直接结束（后续线依赖排名），
      threat/bait 失败跳过并继续。
    """
    board = Board().load_fen(fen)
    external_stop = stop if stop is not None else np.zeros(1, dtype=np.int8)

    ranked = rank_moves(fen, depth=rank_depth, timeout_ms=per_line_timeout_ms)
    if not ranked or external_stop[0] != 0:
        return
    best_packed, best_score = ranked[0]
    my_is_red = board.side_to_move == "red"
    to_red = (lambda s: s) if my_is_red else (lambda s: -s)
    rank_items = []
    for packed, s in ranked[:_RANK_LIST_LIMIT]:
        item = _move_payload(packed, board)
        item["score_stm"] = int(s)
        item["score_red"] = int(to_red(s))
        rank_items.append(item)
    yield {"type": "rank", "best": rank_items[0], "list": rank_items}
    if external_stop[0] != 0:
        return

    threat = threat_event(fen, depth=line_depth, timeout_ms=per_line_timeout_ms)
    yield threat
    if external_stop[0] != 0:
        return

    for bait in select_baits(fen, ranked, max_baits=max_baits):
        if external_stop[0] != 0:
            return
        yield bait_event(fen, bait, depth=line_depth,
                         timeout_ms=per_line_timeout_ms)
```

**Step 4: 跑测试确认通过**

Run: `cd backend && .venv/bin/python -m pytest tests/test_engine_intent.py -v`
Expected: PASS

**Step 5: 提交**

```bash
git add backend/engine/intent.py backend/tests/test_engine_intent.py
git commit -m "feat(intent): 意图推演总编排（rank→threat→baits）"
```

> **Task 6 执行前必读（性能预算实测备注）**：threat 线 depth=8 在初始局面完整搜索约 2.6s，超出默认 timeout_ms=2000，开局/复杂局面 threat 线会静默降级（line 空）；threat 2s + bait×2 各 2s = 6s 已超「先意图后评分 2-5s」总承诺，且 rank_moves 默认不限时。Task 6 编排时需统筹：各线默认 timeout 建议降为 1500ms 并接受部分线降级，或调低 line_depth；不得为保证全产出而放宽超时（违反「意图先出」承诺）。

---

### Task 7: API 端点 `POST /api/engine/intent`

**Files:**
- Modify: `backend/routes/engine.py`（只新增，不改已有函数）
- Test: `backend/tests/test_engine_intent_api.py`

**Step 1: 写失败测试**

参考 `tests/test_engine_api.py` / `test_engine_analysis_api.py` 的 client fixture 风格（conftest 已提供 app/client fixture，先读该文件确认名称）。核心用例：

```python
"""POST /api/engine/intent 端点测试（NDJSON 流式）。"""

import json

INITIAL = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"

OPP_MATE_IN_ONE = "3R5/5k1N1/9/9/9/9/9/9/9/4K1R2 b - - 0 1"


def _post_intent(client, payload):
    resp = client.post("/api/engine/intent", json=payload)
    assert resp.status_code == 200
    assert resp.mimetype == "application/x-ndjson"
    return [json.loads(line) for line in resp.get_data(as_text=True).splitlines() if line.strip()]


def test_intent_stream_event_sequence(client):
    events = _post_intent(client, {"fen": OPP_MATE_IN_ONE, "max_baits": 1,
                                   "time_limit_ms": 30000})
    kinds = [e["type"] for e in events]
    assert kinds[0] == "rank"
    assert "threat" in kinds
    assert kinds[-1] in ("bait", "threat", "done")
    assert kinds.count("ping") >= 0  # ping 可选存在，不得导致解析失败
    assert not any(e["type"] == "error" for e in events)


def test_intent_invalid_fen_yields_error_event(client):
    events = _post_intent(client, {"fen": "not-a-fen"})
    assert any(e["type"] == "error" for e in events)


def test_intent_requires_json_object(client):
    resp = client.post("/api/engine/intent")
    assert resp.status_code == 400


def test_intent_param_clamping(client):
    events = _post_intent(client, {"fen": INITIAL, "max_baits": 99,
                                   "time_limit_ms": 1})
    baits = [e for e in events if e["type"] == "bait"]
    assert len(baits) <= 3  # 夹逼到 1..3
```

**Step 2: 跑测试确认失败**

Run: `cd backend && .venv/bin/python -m pytest tests/test_engine_intent_api.py -v`
Expected: FAIL（404 Not Found）

**Step 3: 实现**

在 `routes/engine.py` 末尾**追加**（复用既有 `_ANALYZE_LOCK` / `_resolve_fen` / `PING_INTERVAL_S` / `_encode` / `_clamp_int`）：

```python
# ---- 对手意图推演（零侵入：新端点，复用锁与流式骨架） -----------------

MIN_INTENT_TIMEOUT_MS = 500
MAX_INTENT_TIMEOUT_MS = 5000
MIN_INTENT_BAITS = 1
MAX_INTENT_BAITS = 3


def _line_payload(pv, base_board, limit):
    """PV/packed 线 → 坐标 + ICCS + 中文（limit 参数化版 _pv_payload）。"""
    from engine.intent import _packed_to_move  # 新增辅助，见 intent 模块

    items = []
    board = base_board.clone()
    for packed in pv[:limit]:
        move = _packed_to_move(packed)
        iccs = f"{chr(97 + move.x1)}{move.y1}{chr(97 + move.x2)}{move.y2}"
        chinese = iccs
        if board is not None:
            try:
                chinese = move_to_chinese(board, move)
            except ValueError:
                chinese = iccs
            try:
                board.apply_move(move)
            except ValueError:
                board = None
        items.append({"x1": move.x1, "y1": move.y1, "x2": move.x2, "y2": move.y2,
                      "iccs": iccs, "chinese": chinese})
    return items


@engine_bp.post("/intent")
def intent_position():
    """对手意图推演：NDJSON 流式（rank → threat → bait* → done）。"""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "请求体必须是 JSON 对象"}), 400

    def generate():
        try:
            fen = _resolve_fen(data)
            timeout_ms = _clamp_int(
                data.get("time_limit_ms"), 2000,
                MIN_INTENT_TIMEOUT_MS, MAX_INTENT_TIMEOUT_MS,
            )
            max_baits = _clamp_int(
                data.get("max_baits"), 2, MIN_INTENT_BAITS, MAX_INTENT_BAITS,
            )
        except Exception as exc:  # noqa: BLE001 - 兜底转流内 error 行
            yield _encode({"type": "error", "message": str(exc)})
            return

        stop = np.zeros(1, dtype=np.int8)
        events = queue.Queue()

        def worker():
            try:
                from engine.intent import intent_events

                for event in intent_events(
                    fen, max_baits=max_baits,
                    per_line_timeout_ms=timeout_ms, stop=stop,
                ):
                    events.put(("event", event))
                events.put(("done", None))
            except Exception as exc:  # noqa: BLE001 - 转流内 error 行
                events.put(("error", exc))

        with _ANALYZE_LOCK:
            t0 = time.perf_counter()
            threading.Thread(
                target=worker, name="engine-intent", daemon=True
            ).start()
            try:
                while True:
                    try:
                        kind, payload = events.get(timeout=PING_INTERVAL_S)
                    except queue.Empty:
                        yield _encode(
                            {
                                "type": "ping",
                                "elapsed_ms": int(
                                    (time.perf_counter() - t0) * 1000
                                ),
                            }
                        )
                        continue
                    if kind == "event":
                        yield _encode(payload)
                    elif kind == "done":
                        yield _encode(
                            {
                                "type": "done",
                                "time_ms": int(
                                    (time.perf_counter() - t0) * 1000
                                ),
                            }
                        )
                        break
                    else:
                        yield _encode({"type": "error", "message": str(payload)})
                        break
            finally:
                stop[0] = 1

    return Response(stream_with_context(generate()), mimetype="application/x-ndjson")
```

**注意：**
- `_line_payload` 最终**不需要**——意图线在 `intent_events` 内已完成中文描述；实现时若确认无需则不添加该函数（DRY）。测试与实现以「事件里 line 已含 chinese」为准。
- `intent_events` 首次调用含 JIT 预热（`warmup()` 幂等），测试整体耗时与 analyze 端点测试同量级。

**Step 4: 跑测试确认通过**

Run: `cd backend && .venv/bin/python -m pytest tests/test_engine_intent_api.py -v`
Expected: PASS

**Step 5: 全量回归（零侵入验收）**

Run: `cd backend && .venv/bin/python -m pytest`
Expected: 与改动前相同的通过数（当前 428 项：427 通过 + 1 跳过），无新增失败。**如有失败：修复实现，绝不改既有测试预期。**

**Step 6: 提交**

```bash
git add backend/routes/engine.py backend/tests/test_engine_intent_api.py
git commit -m "feat(api): 对手意图推演 NDJSON 流式端点 /api/engine/intent"
```

---

### Task 8: 前端 — `intentStream` API 与意图卡片组件

**Files:**
- Modify: `frontend/src/api/index.js`
- Create: `frontend/src/components/IntentPanel.vue`
- Test: `frontend/src/api/__tests__/`（仿现有 analyzeStream 测试文件命名与结构，先读该目录确认模式）

**Step 1: 写失败测试**

仿照 `frontend/src/api/__tests__/` 中现有流式测试（fetch mock 模式）：

```javascript
import { describe, expect, it, vi } from "vitest";
import { intentStream } from "../index";

function mockFetch(lines) {
  const encoder = new TextEncoder();
  let sent = false;
  return vi.fn().mockResolvedValue({
    ok: true,
    body: {
      getReader: () => ({
        read: async () => {
          if (sent) return { done: true, value: undefined };
          sent = true;
          return { done: false, value: encoder.encode(lines.join("\n") + "\n") };
        },
      }),
    },
  });
}

describe("intentStream", () => {
  it("按事件类型分发 rank/threat/bait/done", async () => {
    const onRank = vi.fn();
    const onThreat = vi.fn();
    const onBait = vi.fn();
    const onDone = vi.fn();
    global.fetch = mockFetch([
      JSON.stringify({ type: "rank", best: {}, list: [] }),
      JSON.stringify({ type: "threat", line: [], outcome: null, hint: null }),
      JSON.stringify({ type: "bait", bait: {}, line: [], outcome: {} }),
      JSON.stringify({ type: "done", time_ms: 1 }),
    ]);
    await intentStream({}, { onRank, onThreat, onBait, onDone });
    expect(onRank).toHaveBeenCalledTimes(1);
    expect(onThreat).toHaveBeenCalledTimes(1);
    expect(onBait).toHaveBeenCalledTimes(1);
    expect(onDone).toHaveBeenCalledTimes(1);
  });

  it("abort 后静默返回", async () => {
    const controller = new AbortController();
    global.fetch = vi.fn().mockRejectedValue(
      Object.assign(new Error("aborted"), { name: "AbortError" })
    );
    const onError = vi.fn();
    await intentStream({}, { signal: controller.signal, onError });
    expect(onError).not.toHaveBeenCalled();
  });
});
```

**Step 2: 跑测试确认失败**

Run: `cd frontend && npx vitest run src/api/__tests__ --reporter=verbose`
Expected: FAIL（intentStream 未导出）

**Step 3: 实现 `intentStream`**

在 `frontend/src/api/index.js` 追加（结构与 `analyzeStream` 平行）：

```javascript
export async function intentStream(payload, { signal, onRank, onThreat, onBait, onDone, onError } = {}) {
  try {
    const response = await fetch("/api/engine/intent", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal,
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.detail || data.error || `意图推演请求失败（${response.status}）`);
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    const handleLine = (line) => {
      const text = line.trim();
      if (!text) return;
      let msg;
      try {
        msg = JSON.parse(text);
      } catch {
        return;
      }
      if (msg.type === "rank") onRank?.(msg);
      else if (msg.type === "threat") onThreat?.(msg);
      else if (msg.type === "bait") onBait?.(msg);
      else if (msg.type === "done") onDone?.(msg);
      else if (msg.type === "error") onError?.(new Error(msg.message || "意图推演失败"));
    };
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop();
      lines.forEach(handleLine);
    }
    buffer += decoder.decode();
    handleLine(buffer);
  } catch (err) {
    if (err?.name === "AbortError") return;
    onError?.(err);
  }
}
```

**Step 4: 实现 `IntentPanel.vue`**

展示组件（纯 props 渲染，无请求逻辑；样式对齐现有分析面板的卡片风格——实现前先读 `PlayView.vue` 模板中分析区的类名与结构，复用同一套样式类）：

```vue
<script setup>
defineProps({
  intent: { type: Object, required: true },
});

function lineText(line) {
  return (line || []).map((m) => m.chinese || m.iccs).join(" → ");
}

function outcomeText(outcome) {
  if (!outcome) return "";
  if (outcome.mate) return `绝杀（${outcome.mate} 步内）`;
  if (outcome.loss_piece) return `白丢${outcome.loss_piece}`;
  if (outcome.score_red === null || outcome.score_red === undefined) return "";
  const v = outcome.score_red;
  if (Math.abs(v) < 1) return "均势";
  return v > 0 ? `红优 +${v}` : `黑优 ${v}`;
}
</script>

<template>
  <section class="intent-panel">
    <h3>对手意图推演</h3>
    <p v-if="intent.status === 'running'">推演中…</p>
    <template v-if="intent.status === 'done'">
      <p v-if="intent.threat?.hint" class="intent-hint">{{ intent.threat.hint }}</p>
      <p v-else-if="intent.threat?.line?.length">
        若不理会：{{ lineText(intent.threat.line) }}
        <strong v-if="intent.threat.outcome">{{ outcomeText(intent.threat.outcome) }}</strong>
      </p>
      <ul v-if="intent.baits.length">
        <li v-for="(b, i) in intent.baits" :key="i">
          若你走 {{ b.bait.chinese }}（{{ b.bait.reason }}）：
          {{ lineText(b.line) }}
          <strong v-if="outcomeText(b.outcome)">{{ outcomeText(b.outcome) }}</strong>
        </li>
      </ul>
      <p v-if="intent.rank?.best" class="intent-best">
        正着参考：{{ intent.rank.best.chinese }}
      </p>
    </template>
  </section>
</template>
```

**Step 5: 跑测试确认通过**

Run: `cd frontend && npx vitest run src/api/__tests__ --reporter=verbose`
Expected: PASS

**Step 6: 提交**

```bash
git add frontend/src/api/index.js frontend/src/api/__tests__/ frontend/src/components/IntentPanel.vue
git commit -m "feat(frontend): intentStream API 与对手意图卡片组件"
```

---

### Task 9: 前端 — 触发顺序改造（先意图后评分）

**Files:**
- Modify: `frontend/src/views/PlayView.vue`
- Modify: `frontend/src/views/PracticeView.vue`
- Test: `frontend/src/views/__tests__/`（如无视图测试目录则仅手动验证，见 Step 5）

**Step 1: 阅读 PlayView/PracticeView 模板中分析面板区域**

确认意图卡片插入位置（分析面板旁），以及 `onCellClick`/`undo`/悔棋等所有调用 `startAnalysis()` 的触发点（PlayView.vue:212-220 附近；PracticeView.vue 相应处）。

**Step 2: 写失败测试（如视图有测试）**

若 `frontend/src/views/__tests__/` 不存在，跳过自动化、以 Step 5 手动验证为准（视图无既有测试基建时不新增基建——YAGNI）。

**Step 3: 实现 PlayView 改造**

在 `<script setup>` 中（与 `analysis` 状态平行）新增：

```javascript
import IntentPanel from "../components/IntentPanel.vue";
import { analyzeStream, intentStream, api } from "../api";

function emptyIntent() {
  return { status: "idle", rank: null, threat: null, baits: [], error: "" };
}

const intent = ref(emptyIntent());
let intentController = null;

function stopIntent() {
  if (intentController) {
    intentController.abort();
    intentController = null;
  }
}

function startIntent() {
  stopIntent();
  intent.value = emptyIntent("running");
  intentController = new AbortController();
  intentStream(
    {
      initial_fen: session.state.initialFen,
      moves: session.state.moves.map(({ chinese, check, gameOver, ...rest }) => rest),
    },
    {
      signal: intentController.signal,
      onRank: (r) => { intent.value.rank = r; },
      onThreat: (r) => { intent.value.threat = r; },
      onBait: (r) => { intent.value.baits.push(r); },
      onDone: () => {
        intent.value.status = "done";
        startAnalysis(); // 意图完成后再启动评分分析（串行，零干扰）
      },
      onError: () => {
        intent.value.status = "error"; // 静默降级：意图失败不影响评分
        startAnalysis();
      },
    }
  );
}
```

- `onCellClick`/`undo` 等触发点改为调用 `startIntent()`（原 `startAnalysis()` 调用点全部替换为 `startIntent()`）；
- `stopAnalysis()` 保持不变（startIntent 内 onDone/onError 链式调用 startAnalysis，评分的 abort/token 机制原样工作）；
- 模板中分析面板附近插入 `<IntentPanel :intent="intent" />`；
- 组件销毁时清理：现有 `onUnmounted`（如有）追加 `stopIntent()`。

PracticeView 同样改造（`initial_fen/moves/ply` 用其现有 payload 形状：`{ initial_fen: game.value.initial_fen, moves: game.value.moves, ply: ply.value }`）。

**Step 4: 跑前端全量测试**

Run: `cd frontend && npx vitest run`
Expected: 全部通过（149 项 + 新增 api 测试）

**Step 5: 手动验证（启动后端与前端开发服务器）**

```bash
cd backend && .venv/bin/python app.py   # 终端 1
cd frontend && npm run dev              # 终端 2
```

- 打谱页打开任一棋谱：选中一步后先出现「对手意图推演」卡片（rank/threat/bait 渐次填充），卡片完成后评分条开始逐层更新；
- 对弈页走一步：对手走完后意图卡片先出、评分后出；快速连走时旧请求取消、无报错堆叠；
- 被将军局面：意图卡片显示「你正被将军，必须应将」。

**Step 6: 提交**

```bash
git add frontend/src/views/PlayView.vue frontend/src/views/PracticeView.vue
git commit -m "feat(frontend): 先意图后评分的串行触发与意图卡片接入"
```

---

### Task 10: 文档更新与最终验收

**Files:**
- Modify: `README.md`
- Modify: `docs/plans/2026-09-22-opponent-intent-design.md`（修订一处：删除「局面必须轮到我方，否则 400」——推演对任意局面均有定义，我方 = 走子方）

**Step 1: 修订设计文档**

删除设计文档「后端接口设计」一节中的句子：`局面必须「轮到我方」（即对手刚走完），否则 400。`，替换为：`推演对任意合法局面均有定义：「我方」即走子方；前端仅在对弈/打谱流程中自然传入「对手刚走完」的局面。`

**Step 2: 更新 README**

- 「功能特性」追加一条：`- **对手意图推演**：走子后先推演对手连招——底线威胁（若不理会）与圈套分支（若贪吃/随手棋中计），再进行 AI 评分分析。`
- 「API 一览」表追加：`| POST | /api/engine/intent | 对手意图推演（NDJSON 流式：rank/threat/bait 事件） |`
- API 文档段落（`validate-move` 段之后）新增 `/api/engine/intent` 的请求/事件说明（照设计文档「后端接口设计」一节精简）；
- 「已知限制」追加：`- 意图推演基于浅层搜索（固定深度 8、每线限时 ≤5s），线路精度有限；诱饵筛选为启发式；「跳一手」威胁线结论仅在「我方完全不作为」前提下成立。`

**Step 3: 最终全量验收**

```bash
cd backend && .venv/bin/python -m pytest      # 全部通过，无新增失败
cd frontend && npx vitest run                 # 全部通过
```

**Step 4: 提交**

```bash
git add README.md docs/plans/2026-09-22-opponent-intent-design.md
git commit -m "docs: 对手意图推演接入 README 与设计文档修订"
```

---

## 验收清单（对照设计文档）

- [ ] rank → threat → bait* → done 事件序列，全部含中文记谱；
- [ ] 被将军时 threat 降级为提示；超时分支静默跳过；
- [ ] `/api/engine/analyze` 与所有搜索/评估模块零改动（`git diff --stat` 验证：只新增 intent.py/test 两个新文件 + routes/engine.py 纯追加 + 前端文件）；
- [ ] 后端全量测试通过（数量不少于改动前），前端全量测试通过；
- [ ] 前端触发顺序：意图 done 之后才开始评分分析；意图失败静默、评分照常。
