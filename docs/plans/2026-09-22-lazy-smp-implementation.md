# 引擎 Lazy SMP 并行搜索实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为 `engine.analysis.analyze` 增加 Lazy SMP 并行搜索：主线程产出结果、辅助线程共享置换表互补填表，单次分析吃满多核。

**Architecture:** 主线程保持现有迭代加深与流式产出；T-1 个辅助线程各自独立 `State`/`Stack`/轻量 `Ctx`（仅共享 TT 与停旗），深度相位错开（第 i 个从 `ROOT_START_DEPTH + i` 起）。TT 采用无锁写序保护（写侧 key 最后写、读侧复核 key）。外部 stop 经 10ms 轮询转发到内部总停旗；`threads == 1` 走现有代码路径，行为零变化。

**Tech Stack:** Python 3.12、numba 0.67（`@njit(nogil=True)` 为真并行前提）、numpy、pytest。

**设计文档:** `docs/plans/2026-09-22-lazy-smp-design.md`（先读它）。

**执行约定:**
- 所有命令默认在 `/home/nealian/chess/backend` 下执行，Python 用 `.venv/bin/python`。
- 测试文件里的引擎用例不创建 Flask app；`tests/conftest.py` 会设 `ENGINE_THREADS=1` 保证既有测试确定性。
- 提交信息风格沿用仓库现状：`feat(engine): ...` / `fix(engine): ...` / `test(engine): ...` / `docs: ...`。

---

### Task 0: 提交设计文档

**Files:**
- Add: `docs/plans/2026-09-22-lazy-smp-design.md`（已写好）

**Step 1: 确认文件存在并提交**

```bash
cd /home/nealian/chess
git add docs/plans/2026-09-22-lazy-smp-design.md
git commit -m "docs: 引擎 Lazy SMP 并行搜索设计"
```

---

### Task 1: 线程数解析 + 测试确定性兜底

**Files:**
- Modify: `backend/engine/analysis.py`（顶部 imports、`__all__`、`_resolve_threads`）
- Modify: `backend/tests/conftest.py`（autouse fixture）
- Create: `backend/tests/test_engine_parallel.py`

**Step 1: 先写 conftest 兜底 fixture（不改行为，只隔离环境变量）**

`backend/tests/conftest.py` 末尾追加：

```python
import pytest


@pytest.fixture(autouse=True)
def engine_threads_single(monkeypatch):
    """测试默认单线程：并行专项用例显式传 threads 覆盖。"""
    monkeypatch.setenv("ENGINE_THREADS", "1")
```

（把 `import pytest` 合并到文件顶部已有 import 区，避免重复导入。）

**Step 2: 写失败测试（新建 `backend/tests/test_engine_parallel.py`）**

```python
"""Lazy SMP 并行搜索测试（设计见 docs/plans/2026-09-22-lazy-smp-design.md）。

覆盖：线程数解析、辅助线程上下文隔离、共享 TT 并发读写、并行分析
结果口径、stop 中断与线程清理。
"""

import os
import threading

import numpy as np

from engine import analyze
from engine import analysis as A
from engine import constants as C
from engine import search as S

INITIAL = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"
MATE_IN_ONE = "3R5/5k1N1/9/9/9/9/9/9/9/4K1R2 w - - 0 1"


def _auto_threads():
    cpus = os.cpu_count() or 1
    return max(1, min(cpus - 1, 8))


def test_resolve_threads_explicit_wins(monkeypatch):
    monkeypatch.setenv("ENGINE_THREADS", "3")
    assert A._resolve_threads(2) == 2


def test_resolve_threads_env(monkeypatch):
    monkeypatch.setenv("ENGINE_THREADS", "3")
    assert A._resolve_threads(None) == 3


def test_resolve_threads_auto(monkeypatch):
    monkeypatch.delenv("ENGINE_THREADS", raising=False)
    assert A._resolve_threads(None) == _auto_threads()


def test_resolve_threads_clamped():
    assert A._resolve_threads(0) == 1
    assert A._resolve_threads(999) == A.MAX_THREADS


def test_resolve_threads_bad_value_falls_back(monkeypatch):
    monkeypatch.setenv("ENGINE_THREADS", "abc")
    assert A._resolve_threads(None) == _auto_threads()
    assert A._resolve_threads("xyz") == _auto_threads()
```

**Step 3: 运行测试确认失败**

```bash
.venv/bin/python -m pytest tests/test_engine_parallel.py -v
```

Expected: FAIL（`AttributeError: module 'engine.analysis' has no attribute '_resolve_threads'` / `MAX_THREADS`）。

**Step 4: 实现 `_resolve_threads`**

`backend/engine/analysis.py`：

- imports 区加 `import os`、`import threading`：
```python
import dataclasses
import logging
import os
import threading
import time
```
- `__all__` 追加 `"MAX_THREADS"`、`"_resolve_threads"`（保持字母序）。
- 常量区（`_log = logging.getLogger(__name__)` 之后）加：

```python
# 并行搜索线程数上限（含主线程）。
MAX_THREADS = 16

# 自动线程数：核数 - 1（给 UI/系统留余量），最多 8。
_AUTO_THREADS_MAX = 8


def _resolve_threads(threads):
    """解析并行线程数：显式参数 > 环境变量 `ENGINE_THREADS` > 自动。

    自动值 = `max(1, min(cpu_count - 1, 8))`；显式值夹逼到 `[1, MAX_THREADS]`；
    非法（非整数）值一律回退自动。
    """
    if threads is None:
        raw = os.environ.get("ENGINE_THREADS")
        if raw is not None:
            try:
                threads = int(raw)
            except ValueError:
                threads = None
    if threads is None:
        return max(1, min((os.cpu_count() or 1) - 1, _AUTO_THREADS_MAX))
    try:
        threads = int(threads)
    except (TypeError, ValueError):
        return max(1, min((os.cpu_count() or 1) - 1, _AUTO_THREADS_MAX))
    return max(1, min(threads, MAX_THREADS))
```

**Step 5: 运行测试确认通过**

```bash
.venv/bin/python -m pytest tests/test_engine_parallel.py -v
```

Expected: PASS（5 项）。

**Step 6: 回归既有分析测试（确认 conftest 隔离生效）**

```bash
.venv/bin/python -m pytest tests/test_engine_analysis_api.py -q
```

Expected: 全部 PASS。

**Step 7: Commit**

```bash
git add backend/engine/analysis.py backend/tests/conftest.py backend/tests/test_engine_parallel.py
git commit -m "feat(engine): 并行线程数解析与测试单线程兜底"
```

---

### Task 2: 辅助线程轻量上下文 `new_worker_context`

**Files:**
- Modify: `backend/engine/search.py`（`new_context` 之后）
- Test: `backend/tests/test_engine_parallel.py`

**Step 1: 写失败测试（追加到 `test_engine_parallel.py`）**

```python
def test_worker_context_shares_tt_isolates_rest():
    base = S.new_context(hash_size=1 << 10)
    shared_stop = np.zeros(1, dtype=np.int8)
    worker = S.new_worker_context(base, shared_stop)

    for field in ("tt_key", "tt_type", "tt_value", "tt_depth", "tt_move", "tt_exists"):
        assert getattr(worker, field) is getattr(base, field)
    for field in (
        "killer",
        "history",
        "nodes",
        "root_moves",
        "root_scores",
        "root_count",
        "root_inited",
    ):
        assert getattr(worker, field) is not getattr(base, field)

    assert worker.stop is shared_stop
    assert worker.nodes[0] == 0
    worker.history[0, 0] = 7
    assert base.history[0, 0] == 0
```

**Step 2: 运行确认失败**

```bash
.venv/bin/python -m pytest tests/test_engine_parallel.py::test_worker_context_shares_tt_isolates_rest -v
```

Expected: FAIL（`AttributeError: ... has no attribute 'new_worker_context'`）。

**Step 3: 实现（search.py 的 `new_context` 函数之后）**

```python
def new_worker_context(ctx, stop):
    """派生 Lazy SMP 工作线程上下文：TT 数组引用共享，其余字段独立。

    共享：`tt_*` 六数组（线程间互补填表）与 `stop`（总停旗）；
    独立：killer/history/nodes 与根着法缓冲（避免线程间互相干扰排序状态）。
    """
    return ctx._replace(
        killer=np.zeros((64, 2), dtype=np.int32),
        history=np.zeros((8, 256), dtype=np.int32),
        stop=stop,
        nodes=np.zeros(1, dtype=np.int64),
        root_moves=np.zeros(128, dtype=np.int32),
        root_scores=np.zeros(128, dtype=np.int32),
        root_count=np.zeros(1, dtype=np.int32),
        root_inited=np.zeros(1, dtype=np.int8),
    )
```

同时把 `"new_worker_context"` 加入 search.py 的 `__all__`（字母序，`new_stack` 之后）。

**Step 4: 运行确认通过**

```bash
.venv/bin/python -m pytest tests/test_engine_parallel.py -v
```

Expected: PASS（6 项）。

**Step 5: Commit**

```bash
git add backend/engine/search.py backend/tests/test_engine_parallel.py
git commit -m "feat(engine): Lazy SMP 辅助线程轻量搜索上下文"
```

---

### Task 3: TT 无锁写序保护

**Files:**
- Modify: `backend/engine/search.py`（`_copy_slot`、`_write_straight`、`_write_step`、`set_root_tt`、`get_tt`）
- Test: `backend/tests/test_engine_parallel.py`

**Step 1: 写失败测试（追加）**

```python
def test_concurrent_tt_read_write_stays_in_range():
    """4 线程并发读写同一 TT：不崩、命中分数不越界、写入可回读。"""
    ctx = S.new_context(hash_size=1 << 12)
    errors = []

    def hammer(seed):
        rng = np.random.default_rng(seed)
        for _ in range(4000):
            play = int(rng.integers(0, 2))
            z32 = int(rng.integers(0, 1 << 20))
            z64 = int(rng.integers(1, 1 << 62))
            value = int(rng.integers(-9999, 9999))
            try:
                S.set_tt(ctx, play, z32, z64, S.HASH_PV, value, 6, C.pack_move(0, 1))
                hit, got, _ = S.get_tt(ctx, play, z32, z64, 6, -9999, 9999)
                if hit:
                    assert -20000 <= int(got) <= 20000
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

    threads = [threading.Thread(target=hammer, args=(seed,)) for seed in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
```

**Step 2: 运行确认当前实现也能过（该用例是回归护栏，不因新代码而红；跑一次记录基线）**

```bash
.venv/bin/python -m pytest tests/test_engine_parallel.py::test_concurrent_tt_read_write_stays_in_range -v
```

Expected: PASS（并发读写本身在 numpy 层面不崩；本任务保证的是「不脏读」的写序，由 Step 3 实现与后续并行分析用例共同覆盖）。

**Step 3: 实现写序保护（先数据后 key）**

`_copy_slot` 改为（key 移到最后）：

```python
    ctx.tt_type[play, dst_kind, slot] = ctx.tt_type[play, src_kind, slot]
    ctx.tt_value[play, dst_kind, slot] = ctx.tt_value[play, src_kind, slot]
    ctx.tt_depth[play, dst_kind, slot] = ctx.tt_depth[play, src_kind, slot]
    ctx.tt_move[play, dst_kind, slot] = ctx.tt_move[play, src_kind, slot]
    ctx.tt_exists[play, dst_kind, slot] = True
    # 共享 TT 无锁写序：key 最后写，读者以两次 key 一致判定条目完整
    ctx.tt_key[play, dst_kind, slot] = ctx.tt_key[play, src_kind, slot]
```

`_write_straight` 改为：

```python
    ctx.tt_type[play, SLOT_STRAIGHT, slot] = np.int8(entry_type)
    ctx.tt_value[play, SLOT_STRAIGHT, slot] = np.int32(value)
    ctx.tt_depth[play, SLOT_STRAIGHT, slot] = np.int8(depth)
    if move != 0:
        ctx.tt_move[play, SLOT_STRAIGHT, slot] = np.int32(move)
    ctx.tt_exists[play, SLOT_STRAIGHT, slot] = True
    # 共享 TT 无锁写序：key 最后写
    ctx.tt_key[play, SLOT_STRAIGHT, slot] = zob64
```

`_write_step` 改为（保持 move==0 写 0 的既有行为）：

```python
    ctx.tt_type[play, SLOT_STEP, slot] = np.int8(entry_type)
    ctx.tt_value[play, SLOT_STEP, slot] = np.int32(value)
    ctx.tt_depth[play, SLOT_STEP, slot] = np.int8(depth)
    if move != 0:
        ctx.tt_move[play, SLOT_STEP, slot] = np.int32(move)
    else:
        ctx.tt_move[play, SLOT_STEP, slot] = np.int32(0)
    ctx.tt_exists[play, SLOT_STEP, slot] = True
    # 共享 TT 无锁写序：key 最后写
    ctx.tt_key[play, SLOT_STEP, slot] = zob64
```

`set_root_tt` 改为（key 最后写）：

```python
    slot = zob32 & (ctx.tt_key.shape[2] - 1)
    if not _step_allocated(ctx, play, slot):
        ctx.tt_exists[play, SLOT_STEP, slot] = True
    ctx.tt_move[play, SLOT_STEP, slot] = np.int32(move)
    # 共享 TT 无锁写序：key 最后写
    ctx.tt_key[play, SLOT_STEP, slot] = zob64
```

`get_tt` 增加读复核（保持单线程语义不变；复核失败视为未命中）：

```python
    slot = zob32 & (ctx.tt_key.shape[2] - 1)
    value = 0
    move = 0

    step_key = ctx.tt_key[play, SLOT_STEP, slot]
    step_exists = ctx.tt_exists[play, SLOT_STEP, slot] and step_key == zob64
    if step_exists:
        step_value = _get_by_hash_item(ctx, play, SLOT_STEP, slot, depth, alpha, beta)
        # 共享 TT 无锁读：写者 key 最后写；两次 key 不一致说明条目正在被
        # 并发覆盖，放弃本槽（保守当作未命中）。
        if step_key == ctx.tt_key[play, SLOT_STEP, slot]:
            if step_value != FAIL:
                return True, step_value, ctx.tt_move[play, SLOT_STEP, slot]
            move = ctx.tt_move[play, SLOT_STEP, slot]
            value = ctx.tt_value[play, SLOT_STEP, slot]

    straight_key = ctx.tt_key[play, SLOT_STRAIGHT, slot]
    straight_exists = ctx.tt_exists[play, SLOT_STRAIGHT, slot] and straight_key == zob64
    if straight_exists:
        straight_value = _get_by_hash_item(
            ctx, play, SLOT_STRAIGHT, slot, depth, alpha, beta
        )
        if straight_key == ctx.tt_key[play, SLOT_STRAIGHT, slot]:
            if straight_value != FAIL:
                return True, straight_value, ctx.tt_move[play, SLOT_STRAIGHT, slot]
            move = ctx.tt_move[play, SLOT_STRAIGHT, slot]
            if (
                not step_exists
                or ctx.tt_depth[play, SLOT_STEP, slot]
                < ctx.tt_depth[play, SLOT_STRAIGHT, slot]
            ):
                value = ctx.tt_value[play, SLOT_STRAIGHT, slot]

    return False, value, move
```

**Step 4: 运行 TT 与搜索回归**

```bash
.venv/bin/python -m pytest tests/test_engine_search_tables.py tests/test_engine_search_main.py tests/test_engine_parallel.py -q
```

Expected: 全部 PASS（写序重排不改变单线程可观察行为）。

**Step 5: 更新模块 docstring（search.py 顶部「与 Java 的有意差异」列表追加一条）**

```text
- 共享 TT 多线程写序：`_write_*`/`_copy_slot`/`set_root_tt` 均最后写 `tt_key`，
  `get_tt` 以两次 key 一致复核条目；单线程行为不变，多线程仅把
  「数据已更新、key 未更新」的极短窗口当作未命中（见 Lazy SMP 设计文档）；
```

**Step 6: Commit**

```bash
git add backend/engine/search.py backend/tests/test_engine_parallel.py
git commit -m "feat(engine): 共享置换表无锁写序保护"
```

---

### Task 4: `analyze` 并行集成（核心）

**Files:**
- Modify: `backend/engine/analysis.py`（`analyze`、新增 `_worker_loop`/`_forward_stop`）
- Test: `backend/tests/test_engine_parallel.py`

**Step 1: 写失败测试（追加）**

```python
def test_parallel_analysis_produces_results():
    results = list(
        analyze(INITIAL, start_depth=6, max_depth=8, time_limit_ms=5000, threads=3)
    )
    depths = [r.depth for r in results]
    assert depths == sorted(depths)
    assert depths[0] >= 6 and depths[-1] <= 8
    assert all(r.pv for r in results)
    for r in results:
        assert r.score_red == (
            r.score_stm if r.side_to_move == C.RED else -r.score_stm
        )


def test_parallel_mate_consistent_across_thread_counts():
    for threads in (1, 2, 4):
        results = list(
            analyze(
                MATE_IN_ONE,
                start_depth=6,
                max_depth=6,
                time_limit_ms=5000,
                threads=threads,
            )
        )
        last = results[-1]
        assert last.mate == 1, threads
        assert last.score_red > C.MAX_SCORE - 100, threads


def test_parallel_stop_leaves_no_worker_threads():
    stop = np.zeros(1, dtype=np.int8)
    it = analyze(
        INITIAL,
        start_depth=6,
        max_depth=32,
        time_limit_ms=60000,
        stop=stop,
        threads=4,
    )
    first = next(it)
    assert first.depth >= 6
    stop[0] = 1
    list(it)
    leftovers = [
        t
        for t in threading.enumerate()
        if t.name.startswith("engine-helper-") or t.name == "engine-stop-forward"
    ]
    assert leftovers == []
```

**Step 2: 运行确认失败**

```bash
.venv/bin/python -m pytest tests/test_engine_parallel.py -v -k "parallel"
```

Expected: FAIL（`analyze() got an unexpected keyword argument 'threads'`）。

**Step 3: 实现辅助线程与停旗转发（analysis.py）**

在 `analyze` 之前新增：

```python
def _forward_stop(external_stop, stop_all, done):
    """把外部停旗轮询转发到内部总停旗；`done` 置位后退出。"""
    while not done.wait(0.01):
        if external_stop[0] != 0:
            stop_all[0] = 1
            return


def _worker_loop(fen, shared_ctx, stop_all, start_depth, max_depth):
    """Lazy SMP 辅助线程：独立 State/Stack/轻量 Ctx，共享 TT 与停旗。

    不产出结果、不做时限判断；主线程结束置位 `stop_all` 后自行退出。
    辅助线程异常只记录日志，不影响主线程结果。
    """
    from . import search as _search

    try:
        st = load_position(fen)
        prepare(st)
        ctx = _search.new_worker_context(shared_ctx, stop_all)
        stack = _search.new_stack()
        stack.zob32[0] = st.zob[0]
        stack.zob64[0] = st.zob[1]
        depth = start_depth
        while depth <= max_depth and stop_all[0] == 0:
            _search.search_depth(st, ctx, stack, depth)
            depth += 1
    except Exception:  # noqa: BLE001 - 辅助线程失败不影响主线程
        _log.debug("Lazy SMP 辅助线程异常退出", exc_info=True)
```

**Step 4: 改造 `analyze`**

签名改为：

```python
def analyze(
    fen,
    *,
    start_depth=C.DEFAULT_START_DEPTH,
    max_depth=C.DEFAULT_MAX_DEPTH,
    time_limit_ms=C.DEFAULT_TIME_LIMIT_MS,
    stop=None,
    threads=None,
):
```

docstring 的参数区补充（放在 `stop` 之后）：

```text
    - `threads`：搜索线程数，`None` 表示自动（显式值 > 环境变量
      `ENGINE_THREADS` > `max(1, min(cpu_count-1, 8))`，夹逼 `[1, MAX_THREADS]`）。
      `threads == 1` 时与串行实现完全一致；`> 1` 时启动辅助线程共享 TT
      （Lazy SMP），结果只取主线程，`nodes` 只统计主线程；并行结果存在
      非确定性（同局面分数/PV 可能微变），中断与时限语义不变。
```

夹逼之后插入线程数解析与资源准备（原「`st = load_position(fen)`」之前的代码改为）：

```python
    threads = _resolve_threads(threads)

    if start_depth > max_depth:
        return  # 无产出：不加载局面、不分配 Ctx/Stack

    if threads > 1:
        warmup()  # 幂等；避免多个搜索线程并发触发 JIT 编译

    st = load_position(fen)
    prepare(st)
    # 总停旗：并行时所有搜索线程共享；串行时直接复用外部停旗（现状）。
    stop_all = np.zeros(1, dtype=np.int8) if threads > 1 else None
    search_stop = stop_all if stop_all is not None else stop
    ctx = _search.new_context()._replace(stop=search_stop)
    stack = _search.new_stack()
    stack.zob32[0] = st.zob[0]
    stack.zob64[0] = st.zob[1]

    done = threading.Event()
    helpers = []
    forwarder = None
    if threads > 1:
        if stop is not None:
            forwarder = threading.Thread(
                target=_forward_stop,
                args=(stop, stop_all, done),
                name="engine-stop-forward",
                daemon=True,
            )
            forwarder.start()
        for i in range(1, threads):
            first_depth = C.ROOT_START_DEPTH + i
            if first_depth > max_depth:
                break
            helper = threading.Thread(
                target=_worker_loop,
                args=(fen, ctx, stop_all, first_depth, max_depth),
                name=f"engine-helper-{i}",
                daemon=True,
            )
            helper.start()
            helpers.append(helper)
```

主循环内所有 `stop[0]` 判定改为 `search_stop[0]`：

```python
        depth = C.ROOT_START_DEPTH
        last_layer_ms = 0
        while depth <= max_depth:
            if search_stop[0] != 0:
                break
            layer_t0 = time.perf_counter()
            score, _ = _search.search_depth(st, ctx, stack, depth)
            if search_stop[0] != 0:
                break  # 中断层结果不可信，丢弃
            ...
```

`finally` 改为：

```python
    finally:
        done.set()
        if stop_all is not None:
            stop_all[0] = 1
        for helper in helpers:
            helper.join(timeout=2.0)
        if forwarder is not None:
            forwarder.join(timeout=0.5)
        del ctx, stack, st
```

**Step 5: 运行并行测试确认通过**

```bash
.venv/bin/python -m pytest tests/test_engine_parallel.py -v
```

Expected: 全部 PASS。

**Step 6: 回归分析接口与引擎测试**

```bash
.venv/bin/python -m pytest tests/test_engine_analysis_api.py tests/test_engine_warmup.py tests/test_engine_search_main.py -q
```

Expected: 全部 PASS（`threads` 默认走 env=1 的串行路径，行为不变）。

**Step 7: Commit**

```bash
git add backend/engine/analysis.py backend/tests/test_engine_parallel.py
git commit -m "feat(engine): analyze 集成 Lazy SMP 辅助搜索线程"
```

---

### Task 5: `warmup` 并发幂等

**Files:**
- Modify: `backend/engine/analysis.py`（`warmup`）
- Test: `backend/tests/test_engine_parallel.py`

**Step 1: 写失败测试（追加）**

```python
def test_warmup_is_thread_safe():
    from engine import warmup

    errors = []

    def run():
        try:
            warmup()
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=run) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
```

（预热已完成时该用例接近零开销；未完成时验证互斥不重复编译。）

**Step 2: 实现（analysis.py）**

`_WARMED = False` 之后加：

```python
_WARMUP_LOCK = threading.Lock()
```

`warmup` 改为双重检查：

```python
def warmup():
    """用初始局面触发全链 JIT 编译（幂等、并发安全）。

    覆盖 `search_depth` 链、`init_root` 的外部默认签名、`clean_tt` 与
    `history_decay`。参数类型与正式调用保持一致（Python int），避免 numba
    对 np 标量重新特化。完成后置 `_WARMED`，重复调用近似零开销。
    """
    global _WARMED
    if _WARMED:
        return
    with _WARMUP_LOCK:
        if _WARMED:
            return
        ...（原函数体，最后 _WARMED = True）
```

**Step 3: 运行确认通过并回归**

```bash
.venv/bin/python -m pytest tests/test_engine_parallel.py tests/test_engine_warmup.py -q
```

Expected: 全部 PASS。

**Step 4: Commit**

```bash
git add backend/engine/analysis.py backend/tests/test_engine_parallel.py
git commit -m "fix(engine): warmup 加互斥锁防止并发重复编译"
```

---

### Task 6: 分析接口 `threads` 参数

**Files:**
- Modify: `backend/routes/engine.py`
- Test: `backend/tests/test_engine_api.py`

**Step 1: 写失败测试（追加到 `test_engine_api.py`）**

```python
def test_analyze_threads_parameter(client):
    messages = read_stream(
        client,
        {
            "fen": INITIAL_FEN,
            "start_depth": 4,
            "max_depth": 4,
            "time_limit_ms": 5000,
            "threads": 2,
        },
    )
    assert _of_type(messages, "done")[0]["reason"] == "max_depth"


def test_analyze_threads_clamped_and_optional(client):
    # 越界夹逼不报错；非法类型回退自动（测试环境 env=1）
    for threads in (999, "abc", None):
        payload = {
            "fen": INITIAL_FEN,
            "start_depth": 4,
            "max_depth": 4,
            "time_limit_ms": 5000,
        }
        if threads is not None:
            payload["threads"] = threads
        messages = read_stream(client, payload)
        assert _of_type(messages, "result")
```

**Step 2: 运行确认失败**

```bash
.venv/bin/python -m pytest tests/test_engine_api.py -q -k threads
```

Expected: PASS 或 FAIL 均可（`threads` 当前被忽略，`999` 也不会报错）；先跑一次记录基线，Step 3 之后必须全 PASS。

**Step 3: 实现（`routes/engine.py`）**

- 顶部常量区加：

```python
from engine import analysis as engine_analysis

MIN_THREADS = 1
MAX_THREADS = engine_analysis.MAX_THREADS
```

- `generate()` 内、`time_limit_ms` 解析之后加：

```python
            threads = _clamp_int(
                data.get("threads"),
                None,
                MIN_THREADS,
                MAX_THREADS,
            )
```

- `worker()` 中 `analyze(...)` 调用追加参数：

```python
                for result in analyze(
                    fen,
                    start_depth=start_depth,
                    max_depth=max_depth,
                    time_limit_ms=time_limit_ms,
                    stop=stop,
                    threads=threads,
                ):
```

- 模块 docstring 的接口说明补一句：

```text
    - 请求体可选 `threads`（1..16，越界夹逼；缺省自动：环境变量
      `ENGINE_THREADS` > `min(cpu-1, 8)`）；`analyze` 内部 Lazy SMP，
      响应字段不变。
```

**Step 4: 运行确认通过**

```bash
.venv/bin/python -m pytest tests/test_engine_api.py -q
```

Expected: 全部 PASS。

**Step 5: Commit**

```bash
git add backend/routes/engine.py backend/tests/test_engine_api.py
git commit -m "feat(api): 分析接口支持 threads 参数"
```

---

### Task 7: README 更新与本机加速比实测

**Files:**
- Modify: `README.md`

**Step 1: 实测加速比**

```bash
cd /home/nealian/chess/backend && .venv/bin/python - <<'EOF'
import time
from engine import analyze, warmup

FEN = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"
warmup()
for depth in (8, 10):
    base = None
    for threads in (1, 2, 4):
        t0 = time.perf_counter()
        list(analyze(FEN, start_depth=depth, max_depth=depth,
                     time_limit_ms=60000, threads=threads))
        dt = time.perf_counter() - t0
        if base is None:
            base = dt
        print(f"depth={depth} threads={threads} {dt:.2f}s speedup={base/dt:.2f}x")
EOF
```

将实测结果记入 README（见 Step 2 的占位）。

**Step 2: README 修改**

- 「环境要求」的 numba 段落后追加一段：

```markdown
- 并行搜索（Lazy SMP）：引擎默认使用 `max(1, min(cpu_count-1, 8))` 个线程
  并行分析（主线程产出结果、辅助线程共享置换表互补），可通过环境变量
  `ENGINE_THREADS` 或请求体 `threads` 字段（1..16）覆盖，`ENGINE_THREADS=1`
  即完全串行。并行模式下 `nodes` 只统计主线程，且同一局面的分数/PV 在
  多次运行间可能微变（非确定性），属预期行为。实测提速：
  depth 8 / depth 10，2 线程约 __x / __x，4 线程约 __x / __x（本机数据）。
```

- API 表格 `/api/engine/analyze` 行的说明补充 `threads` 参数；「已知限制」段落里的相关条目按需补充非确定性说明。

**Step 3: Commit**

```bash
git add README.md
git commit -m "docs: README 补充并行分析说明与实测提速"
```

---

### Task 8: 全量回归

**Files:** 无新增

**Step 1: 后端全量**

```bash
cd /home/nealian/chess/backend && .venv/bin/python -m pytest
```

Expected: 全部 PASS（原 428 项 + 新增并行用例；1 skipped 保持）。

**Step 2: 前端全量（未改动，防回归）**

```bash
cd /home/nealian/chess/frontend && npx vitest run
```

Expected: 149 项 PASS。

**Step 3: 手动验证（可选）**

```bash
cd /home/nealian/chess/backend && ENGINE_THREADS=4 .venv/bin/python -c "
from engine import analyze
for r in analyze('rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1', start_depth=6, max_depth=10, time_limit_ms=10000):
    print(r.depth, r.score_red, r.time_ms)
"
```

Expected: 逐层输出 6..10，无异常；观察 CPU 占用应接近多核。

---

## 收尾说明

- 全部任务完成后，如加速比不达设计目标（T=2 < 1.4x / T=4 < 2x），停下复盘：先用 Task 7 的脚本按线程数逐档测，确认是 TT 竞争、辅助相位还是 Python 线程调度问题，再决定是否调整相位策略（如辅助线程与主线程同层错位）或 TT 分片。
- 不要顺手做范围外的事（前端线程数 UI、TT 扩容、YBWC）。
