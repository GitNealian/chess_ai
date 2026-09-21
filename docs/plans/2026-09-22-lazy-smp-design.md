# 引擎 Lazy SMP 并行搜索设计

日期：2026-09-22

## 背景与目标

引擎搜索（Alpha-Beta / NegaScout + 迭代加深）目前完全串行：`analyze()` 在单线程里逐层加深，`search_depth` 独占一个 CPU 核。性能瓶颈直接决定打谱/对弈页「分析到更深层」的等待时间。

目标：在不改变搜索算法正确性口径的前提下，用 Lazy SMP 让单次分析吃满多核，提升同等时间内的可达深度。

- 加速目标（本机实测记录，不做 CI 硬断言）：T=2 ≥ 1.4x，T=4 ≥ 2x；
- 中断目标：stop 置位后 < 50ms 全部搜索线程退出；
- 兼容目标：`threads=1` 时与现有实现零行为差异；现有 428 项后端测试全绿。

## 现状与并行条件

- `engine/search.py` 全模块 `@njit(nogil=True, cache=False)`：编译后的原生代码在搜索期间释放 GIL，Python `threading` 即可真并行（现有 stop 中断机制已实证：其他线程置位 `stop`，搜索 < 1ms 内响应）。
- 现有线程模型：`routes/engine.py` 用 `threading.Lock` 串行化整个分析请求；分析在单个 daemon 工作线程中执行；主生成器每 0.3s yield 保活行，客户端断开时置位 stop。
- 引擎状态构成（`Ctx`，search.py:182）：TT 六数组（`tt_key`/`tt_type`/`tt_value`/`tt_depth`/`tt_move`/`tt_exists`）、`killer`、`history`、`stop`、`nodes`、`root_moves`/`root_scores`/`root_count`/`root_inited`；局面 `State` 与 `Stack` 均为可变的 numpy 数组集合，搜索中原地 make/unmake。
- 迭代加深目前完全由 `analysis.analyze` 的主循环驱动（analysis.py:260-290），时限为层边界软时限 + 时间预算外推。

## 方案选型

| 方案 | 结论 |
|---|---|
| **异步 Lazy SMP（选定）** | 主线程产出结果，辅助线程各自独立迭代加深、共享 TT 互补；无需层间屏障，线程间进度与深度相位自然错开，收益随线程数增长最好。 |
| 每层同步辅助搜索 | 每层起辅助线程、层末 join；引入层间屏障与负载不均，辅助线程与主线程同相位、互补弱。不选。 |
| 根节点并行 | 根着法分片、各线程独立 TT；粒度粗、负载不均、TT 不能互补，收益上限低（且分片代码在 Lazy SMP 下会被废弃）。不选。 |
| YBWC / 动态窃取 | 同步复杂度最高，在 njit 内实现成本不可控。不选。 |
| 多进程 | TT 无法自然共享，搜索模块 `cache=False` 导致每进程独立 JIT 20-35s、内存翻倍。不选。 |

## 线程模型

### 主线程（结果线程）

保持现有迭代加深循环与原语义：`start_depth`/`max_depth` 夹逼、层边界时限检查、时间预算外推、`stop` 检查与中断层丢弃、逐层 yield `AnalysisResult`。`nodes` 只统计主线程。

### 辅助线程 × (T-1)

- 每个辅助线程：自建 `State`（`load_position(fen)` + `prepare(st)`）、自建 `Stack`、派生轻量 `Ctx`（共享 TT 与停旗，其余字段独立）。
- 各自独立迭代加深：深度从 `ROOT_START_DEPTH + i`（i = 1..T-1）起，逐层 +1 直到 `max_depth` 或停旗置位；起始深度已超过 `max_depth` 的线程不启动/立即退出。
- 不产出结果、不做时限预算判断、不写 `ctx.nodes` 展示口径（计数仅本地）。
- 辅助线程异常：捕获后忽略并退出（辅助线程失败不影响主线程结果；至少记录 debug 日志）。

### 派生轻量 Ctx（search.py 新增）

```python
def new_worker_context(ctx, stop):
    """从共享 TT 的 Ctx 派生工作线程上下文：TT 引用共享，其余全部独立。"""
```

- 共享：`tt_key`/`tt_type`/`tt_value`/`tt_depth`/`tt_move`/`tt_exists`、`stop`。
- 独立：`killer`、`history`、`nodes`、`root_moves`、`root_scores`、`root_count`、`root_inited`。

## 置换表无锁写序保护

多线程共享 TT 的核心风险：写者更新条目时读者读到「新 key + 旧数据」或「旧 key + 新数据」的组合。本项目选择无锁 + 写序保护（不引入锁、不加原子操作）：

- **写侧（先数据后 key）**：`_write_straight`、`_write_step`、`_copy_slot`、`set_root_tt` 调整为先写 `type/value/depth/move/exists`，**最后写 `tt_key`**。
- **读侧（复核 key）**：`get_tt` 在 STEP/STRAIGHT 槽读到匹配 key、并取完数据后，再读一次 `tt_key`；两次不一致（说明写者正在覆盖）即视为未命中。
- **残余窗口**：写者数据已更新、key 尚未更新的极短窗口内，读者可能仍以旧 key 匹配到新数据。该窗口内读到的分数/深度/着法仍是合法域内的值（不越界、不崩溃），影响是棋力级而非正确性级；此风险接受并记录在案。
- 实现后需审计 TT 着法 `tt_move` 的所有使用点（排序优先尝试等）是否都有合法性/列表校验，确保「错值」不会直接触发非法着法。
- 不加锁理由：每个节点都发生多次 TT 读写，锁开销会直接吃掉并行收益；Stockfish 系的无锁 TT 亦采用同思路。

## 停旗与中断

- `analyze` 内建 `stop_all`（`np.int8[1]`）；**所有搜索线程**（含主线程）的 `ctx.stop` 均指向它。
- 主线程在 `finally` 中置位 `stop_all`，随后 `join` 全部辅助线程（带兜底 timeout；辅助线程为 daemon，避免泄漏阻塞进程）。
- **外部 stop 转发**：若调用方传入外部 `stop`，启动一个 10ms 轮询的转发线程：外部置位 → 置位 `stop_all`；主线程结束时退出转发线程。转发线程的存在保证「客户端断开 → routes 层置位外部 stop」链路对辅助线程同样有效，且**不改变现有 stop 契约**（analyze 只读外部 stop，不复位）。
- `threads == 1` 时不创建辅助线程与转发线程，`ctx.stop` 直接使用外部 stop（或自建），代码路径与现状一致。

## 生命周期

1. `analyze()` 参数解析：`threads` 显式值 > 环境变量 `ENGINE_THREADS` > 自动（`max(1, min(cpu_count() - 1, 8))`），夹逼到 `[1, MAX_THREADS=16]`；解析函数 `_resolve_threads()` 独立可测。
2. `threads > 1` 时先调用 `warmup()`（幂等；`warmup` 增加互斥锁防并发重复编译）。
3. 建 `Ctx`（共享 TT）、主线程 `State`/`Stack`、`stop_all`（与外部 stop 绑定）。
4. 派生并启动辅助线程（`threading.Thread(daemon=True)`），深度相位错开。
5. 主线程逐层搜索并 yield（流式行为不变）。
6. `finally`：置 `stop_all` → join 辅助线程（timeout）→ 停止转发线程 → 释放 `ctx`/`st`/`stack`。
7. 提前关闭（`GeneratorExit`/客户端断开）走同一 `finally`，不残留线程。

## 线程数配置与 API

- `analysis.analyze(..., threads=None)` 新增参数；`None` 表示自动解析。
- `routes/engine.py`：请求体可选 `threads`（夹逼 1..16），传入 `analyze`；未传时走环境变量/自动。响应 `result`/`done` 行保持不变（不新增字段，避免前端契约变更）。
- README 补充：并行分析的开关方式（`ENGINE_THREADS`）、默认线程数规则、非确定性说明、CPU 占用提示。
- 前端不改动。

## 测试策略

- `tests/conftest.py` 新增 autouse fixture：`ENGINE_THREADS=1`，保证现有测试（尤其 `test_engine_analysis_api.py` 对 `search_depth` 的 monkeypatch 与层序断言）确定性不变。
- 新增 `tests/test_engine_parallel.py`：
  - `_resolve_threads`：显式参数 > env > 自动；夹逼；非法 env 值回退自动。
  - `threads=2/4` 的分析：层序递增、`score_red` 口径、PV 非空、`done` 正常结束。
  - 确定性局面（一步杀 FEN）下 `threads=1/2/4` 的 `score`/`mate` 一致。
  - stop 中断：`threads=4` 时置位 stop，分析在数百毫秒内结束；结束后无 `engine-analyze` 辅助线程残留（`threading.enumerate()`）。
  - 连续多次并行分析无异常、分数始终在合法域。
- 现有测试：全部保持 threads=1 路径。
- 加速比：本机实测记录写进 README/设计文档，不做 CI 断言（防慢机 flaky）。

## 风险与缓解

| 风险 | 缓解 |
|---|---|
| TT 无锁竞争导致偶发脏读 | 写序保护 + 读复核；残余窗口为棋力级影响并记录；必要时后续升级为 payload 打包 |
| 结果非确定性（同局面分数/PV 微变） | 文档注明；测试只在确定局面做严格断言；前端历史列表天然容忍波动 |
| 辅助线程异常拖垮分析 | 辅助线程异常捕获并退出；主线程结果独立产出 |
| 辅助线程泄漏 / 挂起 | daemon + `finally` 置旗 + join(timeout) + 无残留线程测试 |
| 多线程并发 JIT 编译 | `threads>1` 前调用 `warmup()`（加锁幂等） |
| 默认吃多核影响他人使用 | `ENGINE_THREADS=1` 一键关闭；README 提示 |
| 性能收益不达标 | 实测阶段记录各线程数加速比；不达标时保留串行默认并复盘 |

## 不在本次范围

- 前端线程数选择 UI、分析结果并行标识；
- TT 扩容与 entry 打包（payload 打包留作后续彻底消除脏读的升级路径）；
- YBWC、动态任务窃取、多进程/共享内存 TT；
- `routes/engine.py` 的分析请求并发（`_ANALYZE_LOCK` 串行化不变，本次只优化单次分析内部的并行）。
