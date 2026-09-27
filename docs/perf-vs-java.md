# Python 引擎与 Java 原版性能对比分析

日期：2026-09-27
被测版本：`191c366`（含 `perf(engine): 内联热路径、预生成掩码表与动态子力排序` 优化）
对照版本：Java 原版 `pengjiu/ChineseChess`（GBK 源码，Temurin JDK 17 编译）

## 摘要

| 指标 | Python（当前） | Java 原版 | 差距 |
|---|---|---|---|
| 开局 d8 NPS | 241.7k | 790k | **3.3x** |
| 中局 d8 NPS | 278.0k | 1118k | **4.0x** |
| 残局 d7 NPS | 271k | 328k | 1.2x |

同深度节点数两边接近（Python 常更少），**差距全部来自单节点执行成本**，不是搜索树规模。

真实搜索中 Python 的时间构成（rdtsc 插桩，中局 d8，240948 节点，13389 cycles/节点）：

| 项 | 占比 | 说明 |
|---|---|---|
| `evaluate`（评估） | **29.8%** | 最大单项，约 1.28µs/次 |
| 搜索框架（递归、make/unmake、`_select_best`、位运算、数组访问等） | **49.7%** | 无单一函数，是每节点固定开销 |
| 置换表 get+set | 8.8% | 单次操作比 Java 慢 30~40x |
| 着法生成 | 6.2% | 不比 Java 慢 |
| `in_check` | 5.6% | 慢 2.3x |

## 方法

- **Java 侧**：Temurin JDK 17 编译原版；`EngineProbeBatch` 对拍同 FEN/同深度；`BenchJavaFuncs` 函数级微基准；JDK 内置 **JFR**（`settings=profile`）采样热点。
- **Python 侧**：函数级微基准（变化输入防 LLVM 提升）；**rdtsc 插桩**在真实搜索中累计各函数周期；**调用计数插桩**得到每节点调用次数；消融实验（编译期开关，逐项关闭）。
- 所有测量先 `warmup()`，取多轮中位数；插桩/优化原型只在 `/tmp/opencode/perf/` 副本进行，不改仓库。

## 结论 1：evaluate 内部构成（消融，微基准 1150.6 ns/次）

| 跳过项 | evaluate ns/op | 省下 | 占比 |
|---|---|---|---|
| baseline | 1150.6 | — | — |
| `comp_partition_score` | 448.3 | 702.3 | **61%** |
| `dynamic_partition_score` | 547.5 | 603.1 | **52%** |
| `chess_all_move` | 1080.9 | 69.7 | 6% |
| `chess_mobility` | 1123.4 | 27.2 | 2.4% |
| 控制位 `bitboard.count` | 1114.3 | 36.3 | 3.2% |
| 空头/沉底炮检测 | 1111.0 | 39.6 | 3.4% |
| 车马炮加分 | 1121.0 | 29.6 | 2.6% |
| 全部跳过 | 208.3 | 942.3 | 82% |

**Python 的 evaluate 主要慢在分区评分表**：
- `dynamic_partition_score` 每次评估对 48×2 的静态表做两次 `np.copy`（Python 为"避免全局可变状态"而引入；Java 是就地改静态表，零拷贝）；
- `comp_partition_score` 每评估调用 16 次（每个棋子一次），numba 下每次约 44ns；
- 两者合计约占 evaluate 的 82%、**总搜索时间的 ~24%**。

对比 Java 的 JFR：`compPartitionScore` 仅 1.8%、`dynamicCMPChessPartitionScore` 几乎不出现——**同一算法的两边瓶颈位置完全不同**。

## 结论 2：单函数 ns/op 对比（中局局面）

| 函数 | Python | Java | 倍数 |
|---|---|---|---|
| `make_move`+`unmake_move`（一对） | 130.6 | 27.2 | 4.8x |
| `in_check` | 34.2 | 15.2 | 2.3x |
| `getTranZobrist`（miss） | 124.2 | 3.1 | **40x** |
| `setTranZobrist` | 353.0 | 11.8 | **30x** |
| `evaluate`（中局） | ~1150 | 481.5 | 2.4x |
| 着法生成（全量） | 417.6 | 569.1（genEat+genNop） | 相当 |
| `chessAllMove` | 微基准被优化，不可靠 | 15.0 | — |

置换表单次操作差 30~40 倍，但总量占 8.8%。差距来源是多维 numpy 数组索引（`ctx.tt_key[play, kind, slot]`）与调用结构，**不是**此前怀疑的读复核内存屏障（原型实测关闭复核无提升）。

## 结论 3：Java 侧热点（JFR，120 次中局 d8 搜索，5210 样本）

| 方法 | 自耗时占比 |
|---|---|
| `EvaluateCompute.chessAllMove` | 22.7% |
| `EvaluateCompute.bottomCannon` | 15.4% |
| `EvaluateComputeMiddleGame.evaluate` | 7.3% |
| `EvaluateCompute.chessMobility` | 6.9% |
| `ChessMoveAbs.chessEatMove` | 6.4% |
| `ChessMoveAbs.moveOperate` | 6.3% |
| `ChessMoveAbs.checked` | 6.0% |
| `MoveNodesSort.getSortAfterBestMove` | 5.3% |
| `ChessMoveAbs.setBoard` | 4.6% |
| `PrincipalVariation.negaScout` | 4.0% |

Java 的**评估类合计 54%**，其中 `chessAllMove`+`bottomCannon` 占 38%——Java 慢在"象棋计算本身"（位运算调用量大）；Python 慢在"数组拷贝/索引/调用结构"，`chess_all_move` 只占 evaluate 的 6%。**两边都是评估最重，但内部原因相反。**

## 已排除的假设（原型 A/B/C 实测）

| 假设 | 实验 | 结果 |
|---|---|---|
| 每节点 NRT 分配是瓶颈 | 预分配搜索缓冲（Stack 复用，12.9→9.0 次/节点） | NPS 278k→264k，**无提升** |
| TT 读复核（内存屏障）是瓶颈 | 单线程编译期跳过 `_key_unchanged` | NPS 278k→275k，**无变化** |
| `np.copy` 可用切片赋值替代 | 分区表改为预分配缓冲 `attack[:] = table` | NPS 278k→271k，**无提升**（切片赋值成本≈copy） |

## 根因

1. **分区评分表每次评估重建**（~24% 总时间）：`dynamic_partition_score` 的双 `np.copy` + `comp_partition_score` 的 16 次逐棋子累加。Java 用就地静态数组 + `switch`，近乎免费。这是移植时为"避免全局可变状态"引入的额外成本。
2. **每节点框架开销**（~50%）：`make+unmake` 2.13 次/节点、`_select_best` 1.95 次/节点、递归调用与参数传递、numpy 数组索引。Java 的同类操作被 C2 充分内联/标量替换，每节点仅约 0.36µs；Python 约 2.1µs（**6x**）。
3. **TT 访问**（8.8%）：单次 30~40x，源于多维 numpy 索引与函数边界。
4. 评估的"象棋计算"部分（`chess_all_move`/炮检测）在 Python 中不是瓶颈（总计 <10%），与 Java 的 38% 形成鲜明对照。

## 优化建议（按收益/风险）

1. **消除分区表每次重建**（预计总时间 -15%~-20%）：
   - 首选：把 8 个动态索引（19-22/35-38/23-26/39-42）的值直接内联进 `comp_partition_score` 的判断分支，其余查静态表——**零数组重建**；
   - 备选：把动态表缓存在 ctx 并在士/象数量变化时才重建。
2. **降低框架固定开销**（预计 -10%~-20%）：合并 `ctx`/`stack` 字段以减少递归传参宽度；`_select_best` 对小着法列表展开；`make_move`/`unmake_move` 内联（部分已由 191c366 完成）。
3. **TT 扁平化**：六个 TT 数组合并为带步长的单块内存，索引改一维，减少维度计算。
4. 若目标是接近 Java 绝对值：即使用尽上述手段，Python/numba 仍会保留 2~3 倍差距（框架 6x 属编译器/运行时特性），彻底对齐需引入 C/C++/Rust 扩展重写热点。

## 复现方法

脚本位于 `/tmp/opencode/perf/`（临时目录，不随仓库分发）：

| 脚本 | 用途 |
|---|---|
| `bench_py.py` / `ab_nps.py` | 分层耗时、NPS、NRT 分配统计 |
| `bench_funcs2.py` | Python 函数级微基准 |
| `count_search.py` | 调用次数（需 `prof_engine` 插桩副本） |
| `timing_search.py` | rdtsc 真实搜索耗时分解（需 `proc_timing.py` 插桩） |
| `eval_ab.py` + `bench_eval_ab.py` | evaluate 内部消融（每次需清 numba 缓存） |
| `opt_prealloc.py` / `opt_partition.py` | 原型 A/B/C 优化实验 |
| Java 侧：`EngineProbeBatch` / `BenchJavaFuncs` + `jfr print` | 对拍、微基准、JFR 热点 |

注意：修改 `@njit(cache=True)` 函数后必须删除 `__pycache__/*.nbi|*.nbc`，否则会复用旧编译产物导致测量失真（本次分析中曾因此得到错误结论）。
