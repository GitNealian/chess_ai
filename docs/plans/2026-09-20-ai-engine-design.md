# 中国象棋 AI 引擎迁移与接入设计

日期：2026-09-20

## 目标

把原 Java 中国象棋 AI 引擎（[pengjiu/ChineseChess](https://github.com/pengjiu/ChineseChess)，位棋盘 + negaScout/PVS 深搜）迁移为本仓库的 Python 实现，并接入记谱系统：

1. 打谱回放（PracticeView）中，每次翻步后**对最新局面实时打分**。
2. 分析采用**渐进加深**：从 6 层开始，每完成一层立即出结果，层数逐层 +1。
3. 展示方式：以优势方显示评分（红优 +X / 黑优 -X）+ 棋盘上箭头标注**双方各一步推演**。
4. 结果历史采用 **append 模式**，最新结果在最前。

## 现状

- 后端 `backend/chess_engine/` 是纯 Python 规则引擎（无 AI、无评估），坐标 `(x,y)`（x∈0..8 左→右，y∈0..9 下→上，红方在下）与 ICCS、标准中国象棋 FEN 一一对应。
- 前端 PracticeView 用 `initial_fen + moves[:ply]` 在本地重建局面；无 FEN 序列化、无箭头渲染层。
- 设计文档 `2026-09-19-chess-practice-design.md` 第 11 节把「AI 评估」列入不做；本设计为范围变更，单独成文。
- 原 Java 引擎要点：4×int 位棋盘（27+27+27+9 切片）、90 格坐标 `site = row*9+col`（row=0 为黑方底线）、棋子索引 16-31 黑 / 32-47 红、预生成走法表、迭代加深 + 根/内部 PVS + LMR + Futility + 空着裁剪 + 静态搜索、Zobrist + 2 槽置换表、历史启发、中残局双评估。

## 技术选型

**numba JIT**（已装 numba 0.67 + llvmlite 0.49，支持 Python 3.12）：

- 本机微基准：numba 92.6 M 简化节点/s vs 纯 Python 0.65 M/s（约 140×）。
- 源码保持纯 Python；`cache=True` 持久化编译产物；应用启动时后台预热编译。
- 约束：引擎核心不能用 dict/对象（numba 支持差），全部用固定宽度整数与 ndarray，与原 Java 风格天然契合。

## 引擎架构（新包 `backend/engine/`）

| 模块 | 迁移自（Java） | 内容 |
|---|---|---|
| `constants.py` | ChessConstant | 棋子/角色编码、值分数、难度参数、搜索参数表 |
| `bitboard.py` | BitBoard | 4×int32 切片操作、popcount、MSB 取位、腿位折叠校验和 |
| `tables.py` | ChessInitialize | 预生成：马/象腿位与攻击表、车炮行列攻击/平移/假攻击/重炮表、士象将兵走法、机动性、危险区掩码、分区表 |
| `zobrist.py` | InitZobristList32And64 | 确定性随机表（固定种子，保证 numba 缓存不失效） |
| `position.py` | ChessParam | board[90]、allChess[48]、boardBitRow/Col、剩余子计数、按方/角色位棋盘、baseScore[2]；make/unmake 增量维护（含 Zobrist XOR） |
| `movegen.py` | ChessMoveAbs/Play/Quiesc、MoveNodesSort | 吃子/非吃子生成（保留原生成顺序）、MVV-LVA + 历史排序、killer/TT 着法优先、合法性校验、将军检测（含飞将、炮、马、兵）、`oppAttackSite` 保护判断 |
| `evaluate.py` | EvaluateCompute(MiddleGame/EndGame) | 中局：子力+位置表、士象动态分区、机动性惩罚、空头/沉底炮、缺士象、攻防分区差、车马炮奖励；残局：兵保护数表、炮马对缺士象；动态子力价值（兵/马/炮随局面调整，须保持与原版相同的调用时序） |
| `search.py` | PrincipalVariation / SearchEngine / TranspositionTable / CHistoryHeuritic | 迭代加深（从 4 层起）、根 PVS、内部 PVS（零窗口+重归约+全窗口）、LMR、Futility 跳过、空着裁剪+两次验证、静态搜索、杀手着法、历史启发表（每步衰减 /512）、2 槽置换表（直存+深度替换，含 mate 分数调整）、长将（8888）与和棋检测、被吃将检测 |
| `analysis.py` | AICoreHandler | 对外非 JIT 接口：`analyze(fen, start_depth=6, max_depth=16, time_limit_ms=2000, stop_flag) -> Iterator[AnalysisResult]`；中残局判定（双方车马炮+兵>3 计数 <7 判定残局，残局深度 +1）；**每完成一层迭代 yield 一次结果** |
| `__init__.py` | — | 公共 API 与预热函数 `warmup()` |

实现原则：

- 行为等价于原 Java 版（含搜索参数、评估权重、生成顺序）；Zobrist 用自生成表，不要求与原版哈希碰撞模式一致。
- 停止机制：numpy 数组作 stop flag，搜索循环定期检查；超时/客户端断开都走该标志。
- 表构建为确定性、幂等，可缓存到磁盘（npy）加速冷启动。

## 后端 API

`POST /api/engine/analyze`，**NDJSON 流式响应**（`application/x-ndjson`，每行一个 JSON）：

请求：

```json
{ "initial_fen": "...", "moves": [{"x1":0,"y1":3,"x2":0,"y2":4}], "ply": 1,
  "start_depth": 6, "max_depth": 16, "time_limit_ms": 2000 }
```

或直接 `{ "fen": "..." }`（二者必居其一；`initial_fen+moves+ply` 由后端权威重建并校验）。

响应流：

```
{"type":"result","depth":6,"score_red":96,"score_stm":-96,"pv":[{"x1":..,"y1":..,"x2":..,"y2":..,"iccs":"h2e2","chinese":"炮二平五"},...],"time_ms":152,"nodes":123456}
{"type":"result","depth":7,...}
{"type":"done","max_depth":16,"time_ms":2010,"reason":"time"}
```

- `score_red`：红方视角分数（centipawn 风格，与原引擎子力分值同尺度，兵=100）；`score_stm` 为引擎原始走子方视角。
- `pv`：主变前两步（当前方最佳着法 + 对方应着），附 ICCS 与中文记谱。
- 客户端断开 → 生成器 `close` → 置 stop flag → 搜索安全退出。
- 输入非法（FEN 解析失败、着法不合法、ply 越界）→ 单行 `{"type":"error","message":...}`。
- 复用 `chess_engine` 做输入校验与中文记谱（Board + notation）。
- 引擎实例进程内单例 + 并发锁（本地单用户，同时只跑一个分析）；预热在 `create_app` 后台线程进行（不阻塞启动）。

## 前端

- **`ChessBoard.vue`**：新增 `arrows` prop（`[{x1,y1,x2,y2,kind:"best"|"reply"}]`），SVG `<defs><marker>` 渲染带箭头的连线；不影响现有 props/测试（默认空数组）。
- **`PracticeView.vue`**：新增「AI 分析」面板：
  - 评分区：`红优 +1.2` / `黑优 -0.8`（走子方为黑时自动翻转显示），配红蓝双色优势条。
  - 迭代历史（append，最新在最上）：每条含 `深度 / 耗时 / 分数 / 双方一步推演（中文记谱）`。
  - 状态提示：分析中（转圈）/ 完成（原因：时间或深度上限）/ 已中断。
  - 翻步、跳转、切换棋谱时：abort 旧分析请求，立即对最新局面发起新分析。
  - 移动端沿用单列（棋盘上、面板下）；桌面端 `.side` 右栏。
  - 离开页面（unmount）时 abort 请求。
- **`api/index.js`**：新增 `analyzeStream(payload, { signal, onResult, onDone, onError })`，用 `fetch` + `ReadableStream` 按行解析 NDJSON（axios 浏览器端不支持流式读取）。
- 箭头颜色：最佳着法（当前方）用蓝色 `#2563eb`，对方应着用橙色 `#ea580c`。

## 性能目标与验收

- 首次冷启动：后台预热（JIT 编译）完成，不阻塞页面；numba 磁盘缓存命中后启动 < 2s。
- 分析速度：典型中局 depth 6 ≤ 200ms、depth 8 ≤ 1s；单次分析默认时间上限 2s、深度上限 16。
- 前端：翻步后 ~200ms 内出现首个结果（6 层）；每加深一层历史列表自动追加。
- 现有后端 pytest 与前端 vitest 全量通过，新增测试全绿。

## 测试策略

- 引擎：
  - perft：初始局面各深度节点数（与已知中国象棋 perft 值对照，如 depth1=44、depth2=1920、depth3=79666、depth4=3290240），并覆盖特殊规则（飞将、蹩腿、塞象眼、炮翻山、过河兵）。
  - 搜索：一步杀/两步杀必能找到；将死分数正确（±(maxScore-depth)）；静态搜索不丢子（简单吃子局面）。
  - 评估：初始局面分数接近 0；红方多一车时红方视角为正。
  - 置换表/历史表：同局面重复搜索更快（节点数下降）为加分项。
  - `analysis.analyze` 逐层 yield：层数递增、深度/时间上限生效、stop_flag 可中断。
- API：NDJSON 行格式与字段、两种入参形式、非法输入错误行、中断释放（停止标志置位）。
- 前端：面板渲染评分与历史、翻步触发分析（mock stream）、abort 调用、箭头渲染（ChessBoard 单测）、移动端类名/结构不回归。

## 风险与缓解

| 风险 | 缓解 |
|---|---|
| numba 对模块级全局数组 + cache 的限制 | 表作为函数参数传递（首选）或确定性全局；实现阶段先做最小验证 |
| WSGI 流式响应缓冲导致「逐层推送」变「一次性」 | Werkzeug dev server 直接验证；若 gunicorn 缓冲，则每行末尾 padding 或降级为任务轮询（备用方案） |
| 移植 7000 行算法引入行为偏差 | 以 perft/杀棋测试锚定正确性；评估与搜索参数逐项对照 Java 源码 |
| 搜索占 CPU 影响 Flask 响应 | 分析专用锁 + 单实例排队；时间上限强制收敛；中断及时释放 |
| 大 DB（14 万局）与内存 | 分析接口只吃 FEN/moves 切片，不查库、不加载棋谱 |

## 不在本次范围

- 默写复习页（ReviewView）的接入（面板做成组件，后续可低成本接入）。
- 引擎自我对弈/棋力测试平台、开局库、云库。
- Top-N 多主变输出（当前只输出单条主变前两步）。
- 引擎难度选择 UI（分析固定为「深度递进至时间上限」）。

## 参考

- 原 Java 引擎：`https://github.com/pengjiu/ChineseChess`（`com/pj/chess/`）
- 现有坐标/FEN 约定：`docs/plans/2026-09-19-chess-practice-design.md` 第 6 节
