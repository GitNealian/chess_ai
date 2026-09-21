# 象棋记谱 Web

一个单用户本地使用的象棋棋谱管理与背谱工具：**棋谱库** + **背谱默写复习**，配合 **SM-2 间隔重复** 安排复习节奏。后端 Flask 提供 REST API 与纯 Python 规则引擎，前端 Vue 3 + Vite 自绘 SVG 棋盘。

## 功能特性

- **三种棋谱录入**
  - 文本录入：粘贴中文记谱（如 `炮二平五`）或 ICCS 坐标（如 `h2e2`），实时解析预览。
  - PGN 导入：识别 `[Event]`、`[Red]`、`[Black]`、`[Result]` 等头部标签，兼容中文/ICCS 着法。
  - 棋盘摆子：点击走子自动记谱。
- **打谱回放**：逐步回放、点击着法列表跳转、切换视角。
- **背谱默写**：走对才前进，走错标红并计错，支持「看答案」；按红/黑/双方选择默写阵营。
- **间隔重复（SM-2）**：按错误次数与是否看答案评分，更新 `ease_factor` / `interval` / `repetitions` / `lapses`，到期自动进入今日复习队列。
- **棋谱库管理**：分类、关键字筛选，显示掌握度（新 / 学习中 / 已掌握）与下次复习日期。
- **规则引擎**：完整合法性判定（蹩马腿、塞象眼、炮翻山、将帅照面、过河兵、将死/困毙），规则单一真相源在后端。
- **人人对弈**：同屏双人轮流走子，支持翻转棋盘（黑方视角）、悔棋、每步自动 AI 分析；可从空白开局，也可从任意棋谱的当前步续下；对局可手动保存到棋谱库。
- **AI 局面分析**：打谱与对弈时逐层加深实时打分，红优/黑优评分 + 优势条 + 棋盘箭头标注双方一步推演（最新结果置顶）。

## 目录结构

```
chess/
├── backend/
│   ├── app.py              # Flask 入口 + 蓝图注册 + 前端静态托管
│   ├── config.py           # 配置（SQLite、测试配置）
│   ├── models.py           # SQLAlchemy 模型：Game / Review / ReviewLog
│   ├── chess_engine/       # 纯 Python 规则引擎（无 Flask 依赖）
│   │   ├── board.py        # 9x10 棋盘、走子与合法性
│   │   ├── fen.py          # 中国象棋 FEN
│   │   ├── move.py         # 着法表示
│   │   ├── notation.py     # 中文记谱生成/解析
│   │   └── parser.py       # 中文 / ICCS / PGN 解析
│   ├── engine/             # numba 加速的 AI 引擎（位棋盘 + negaScout/PVS）
│   │   ├── analysis.py     # 对外 analyze / warmup：迭代加深，每层 yield
│   │   ├── search.py       # 置换表、杀手/历史启发、静态搜索、主搜索
│   │   ├── movegen.py      # 着法生成、将军检测与合法性
│   │   ├── position.py     # 局面状态与 make/unmake 增量维护
│   │   ├── evaluate.py     # 中局 / 残局评估
│   │   ├── bitboard.py     # 位棋盘原语（90 位打包为两个 int64）
│   │   ├── tables.py       # 预生成基础表
│   │   ├── eval_tables.py  # 自动生成的评估表（脚本提取自 Java 源码）
│   │   ├── zobrist.py      # Zobrist 哈希（固定种子自生成）
│   │   └── constants.py    # 常量与 site/(x,y) 坐标转换
│   ├── srs.py              # SM-2 间隔重复调度
│   ├── routes/
│   │   ├── engine.py       # 引擎分析 NDJSON 流式接口 + 走子校验
│   │   ├── games.py        # 棋谱 CRUD、解析、PGN 导入、走法校验
│   │   └── review.py       # 复习队列、提交、统计
│   ├── scripts/            # 工具脚本（评估表提取、PGN 批量导入）
│   ├── tests/              # pytest 测试
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/     # ChessBoard.vue（SVG 自绘）
│   │   ├── views/          # Library / Editor / Practice / Review / Play
│   │   ├── stores/         # Pinia：library / practice；play 对弈会话（reactive 工厂）
│   │   ├── api/            # axios 封装
│   │   ├── utils/          # 坐标与记谱工具
│   │   └── router/         # Vue Router
│   ├── package.json
│   └── vite.config.js
└── docs/plans/             # 设计文档与实现计划
```

## 环境要求

- Python 3.11+
- Node.js 18+
- 引擎依赖 `numba` / `numpy`（见 `backend/requirements.txt`）。首次启动时后台线程预热引擎：首次 JIT 约 20-35s（期间其他功能可正常使用），之后进程内即时。大部分引擎模块启用 numba 磁盘缓存（`backend/engine/__pycache__/`），编译产物可跨进程复用；但**搜索模块（`search.py`）因 numba 0.67「递归 + 跨函数调用 + 磁盘缓存」缺陷不使用磁盘缓存**，因此**每个新进程首次分析仍需 ~20-35s 预热**。建议部署后等预热线程完成（或先发一个浅层分析请求）再对外服务；gunicorn 多 worker 各自独立预热。
- numba 缓存目录会随源码变更 / numba 升级累积历史编译产物而增长。运行一段时间后可安全删除 `backend/engine/__pycache__/`，代价是下次冷启动重新编译（即上述预热耗时）。
- **并行搜索（Lazy SMP）**：引擎默认使用 `max(1, min(cpu_count-1, 8))` 个线程并行分析：主线程产出结果，辅助线程共享置换表互补搜索。可用环境变量 `ENGINE_THREADS`（如 `ENGINE_THREADS=1` 完全串行）或分析请求的 `threads` 字段（1..16）覆盖。并行模式下 `nodes` 只统计主线程；同一局面的分数/PV 在多次运行间可能微变（非确定性），属预期行为。本机实测（nproc=20 逻辑核，固定深度、`time_limit_ms=60000`、预热完成后测量（无额外基准负载，测量时系统 load≈1），每档重复 3 次取中位数，depth 8 / 10）：2 线程 1.5x / 1.6x，4 线程 1.9x / 2.1x；默认 8 线程档未测。
- **`gunicorn --preload` 注意**：请在 gunicorn 配置的 `on_starting(server)` 钩子中同步调用 `engine.warmup()` 完成预热后再 fork worker（或直接不使用 `--preload`）。若在预热线程运行期间 fork，子进程可能继承 numba 自身的编译锁（本项目的 `_WARMUP_LOCK` 已做 fork 重建，numba 编译锁不能），导致子进程首次编译（含 `threads=1` 串行搜索）阻塞。

## 后端启动

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python app.py
```

默认监听 `http://localhost:5000`，数据库为 `backend/chess.db`（SQLite，首次启动自动建表）。

## 前端启动（开发期）

```bash
cd frontend
npm install
npm run dev
```

开发服务器运行在 `http://localhost:5173`，Vite 将 `/api` 代理到 `http://localhost:5000`。

## 测试

```bash
# 后端（428 项：427 通过 + 1 跳过；其中引擎相关 254 项）
cd backend && .venv/bin/python -m pytest

# 前端（149 项）
cd frontend && npx vitest run
```

后端首次运行需等待 numba JIT 编译（搜索模块不使用磁盘缓存，每个新进程都要重新编译），整体约 40s；引擎预热耗时见「环境要求」。

## 生产构建（单端口 5000）

```bash
cd frontend && npm run build      # 产物输出到 frontend/dist
cd backend && .venv/bin/python app.py
```

Flask 检测到 `frontend/dist` 后会托管静态资源，访问 `http://localhost:5000/` 即可；非 `/api/*` 的未知路径回退到 `index.html`（支持前端路由）。

### 手机 / 局域网访问

前端已做移动端适配（移动优先响应式，手机竖屏可用）。若要在同一局域网用手机访问，让后端监听所有网卡：

```bash
cd backend && HOST=0.0.0.0 .venv/bin/python app.py
```

然后在手机浏览器打开 `http://<电脑局域网IP>:5000`（如 `http://192.168.1.10:5000`）。查看 IP：Linux/macOS 用 `hostname -I` 或 `ip addr`，Windows 用 `ipconfig`。也可用环境变量 `PORT` 改端口（如 `PORT=8080`）。

注意：`HOST=0.0.0.0` 会对局域网暴露服务，仅在可信网络中临时使用；默认仍为 `127.0.0.1`（仅本机）。

### 生产部署（WSGI 服务器）

推荐用 gunicorn 托管，多 worker 且无调试器：

```bash
cd backend && .venv/bin/gunicorn -w 2 -b 0.0.0.0:5000 "app:create_app()"
```

`create_app()` 在应用工厂内自动建表（幂等），gunicorn 导入时即可完成初始化。
调试器默认关闭；仅在本地需要时通过环境变量开启：`FLASK_DEBUG=1 .venv/bin/python app.py`（切勿在生产启用）。

## API 一览

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/api/health` | 健康检查 |
| GET | `/api/games` | 棋谱列表（`category` / `keyword` 筛选） |
| POST | `/api/games` | 创建棋谱（保存前校验着法合法性） |
| GET | `/api/games/:id` | 棋谱详情（含 `initial_fen` 与 `moves`） |
| PUT | `/api/games/:id` | 更新棋谱 |
| DELETE | `/api/games/:id` | 删除棋谱 |
| POST | `/api/games/parse` | 解析文本棋谱（预览，不入库） |
| POST | `/api/games/import-pgn` | PGN 导入 |
| POST | `/api/games/:id/check-move` | 校验某步是否为正确着法 |
| POST | `/api/engine/analyze` | 局面分析（NDJSON 流式，逐层返回；可选 threads 1..16） |
| POST | `/api/engine/validate-move` | 无状态走子校验（返回新局面 / 中文记谱 / 将军 / 终局） |
| GET | `/api/review/queue` | 今日复习队列 |
| POST | `/api/review/:gameId/submit` | 提交复习结果并更新调度 |
| GET | `/api/stats` | 掌握度统计 |

错误统一返回 `{error, detail?, step?}`。

`POST /api/engine/analyze` 为 NDJSON 流式响应（`application/x-ndjson`，每行一个 JSON）：请求体可用 `fen`，或用 `initial_fen` + `moves` + `ply` 重放局面；可选 `start_depth`（默认 6）、`max_depth`（默认 16，上限 16）、`time_limit_ms`（默认 30000，范围 100–30000，层边界软时限：按「上一层耗时 × 1.5」外推下一层预算，通常完成时间不超过其 ~1.5 倍）、`threads`（可选，1..16，越界夹逼；缺省自动：环境变量 `ENGINE_THREADS` > `max(1, min(cpu_count-1, 8))`；`threads=1` 即串行）。流内依次可能出现：

- `{"type":"result", ...}`：每完成一层一条，含 `depth` / `score_red` / `score_stm` / `mate` / `pv`（每步含 `x1,y1,x2,y2` / `chinese` / `iccs`）/ `time_ms` / `nodes` / `side_to_move`；
- `{"type":"ping", "elapsed_ms": ...}`：约每 0.3s 的保活行，客户端可忽略；
- `{"type":"done", "depth":..., "time_ms":..., "reason":...}`：正常结束（`reason` 为 `max_depth` / `time_limit` / `stop`）；
- `{"type":"error", "message":...}`：参数、FEN 或着法错误。

`POST /api/engine/validate-move` 为无状态走子校验（供人人对弈页调用）：请求体 `{ "initial_fen"?, "moves"?, "move" }`，重放 `initial_fen + moves`（缺省初始局面 / 空序列）后校验 `move`。合法返回 `{ "legal": true, "fen", "side_to_move", "chinese", "check", "game_over" }`，其中 `check` 为走子后对方是否被将军、`game_over` 为 `{ "winner", "reason": "checkmate" | "stalemate" }` 或 `null`（中国象棋困毙判负），`chinese` 生成失败时回退 ICCS；非法着法返回 200 `{ "legal": false, "reason" }`（"起点没有棋子" / "该棋子不属于行棋方" / "该棋子不能这样走" / "不能送将"）；参数、FEN 或重放序列错误返回 400 `{ "error", "detail"? }`（`moves` 上限 1024 步）。

## 已知限制

- 前端「棋盘摆子」入口不校验着法合法性；后端保存时会校验并拒绝非法序列（错误信息带步号）。
- 打谱 / 录入视图的着法列表显示坐标 `(x1,y1)→(x2,y2)`，而非中文记谱；中文记谱能力位于后端规则引擎，前端尚未接入转换接口。
- 中文记谱的「前 / 后」仅处理同列两子，三子及以上不支持生成（生成端会明确报错）。
- **合法落点提示未接入**：`ChessBoard` 组件已支持 `legalTargets` 渲染，但后端未提供「查询合法着法」接口，因此摆子与默写时暂无落点圆点提示。
- `check-move` 在着法错误时仍会应用用户着法并返回其后的局面（前端目前未使用该接口，仅作预留）。
- 部分设计承诺尚未落地：PGN 文件上传（当前仅支持粘贴内容）、文本解析的逐步高亮预览、打谱视角切换、默写手动评分（当前按错误次数与是否看答案自动评分）。
- 掌握度阈值：`repetitions >= 3` 视为「已掌握」，与 `/api/stats` 的 `mastered` 口径一致。
- 棋谱列表对每条棋谱的复习信息为惰性加载（本地单用户规模下可接受）。
- 单用户、无登录；数据存于 SQLite。
- AI 分析接入打谱页与对弈页；录入 / 默写视图未接入。
- 人人对弈为同屏双人，不联网、不自动保存（手动保存到棋谱库）；不判定长将、重复局面和棋；从棋谱续下的将军/终局提示由一次探测请求恢复，悔棋到该步之前时提示不恢复（着法合法性始终由后端保证）。
- 搜索中断在毫秒级（层内逐节点检查停旗），客户端断开后服务端在下一个 ping 周期内停止；`time_limit_ms` 是层边界软时限，完成一层后按「上一层耗时 × 1.5」外推下一层预算，预判超支即不再开始下一层（通常完成时间不超过其 ~1.5 倍）；若下一层实际耗时相对上一层暴涨，仍可能超出。
- 并行分析下 `nodes` 仅统计主线程，且结果非确定性（同局面多次分析的分数/PV 可能微变，将杀步数可能 ±1 ply 级偏差）。
- 显式线程数（含环境变量 `ENGINE_THREADS`）不按核数降级（夹逼 1..16），低核机器上设大值会线程超订；不设时自动取 `max(1, min(cpu_count-1, 8))`，需要完全串行可用 `ENGINE_THREADS=1`。
- Zobrist 哈希为自生成（固定种子），与 Java 版哈希值不兼容，仅保证引擎内部自洽。
- mate 分数不入置换表（修正 Java 继承缺陷，避免深层杀步失真）。
- 黑方着法生成顺序与 Java 版略有差异（按 site 升序扫描），不影响棋力。

## 设计文档与实现计划

- 棋谱练习（初版）：`docs/plans/2026-09-19-chess-practice-design.md` / `docs/plans/2026-09-19-chess-practice-implementation.md`
- 移动端适配：`docs/plans/2026-09-19-mobile-responsive-design.md`
- AI 引擎：`docs/plans/2026-09-20-ai-engine-design.md` / `docs/plans/2026-09-20-ai-engine-implementation.md`
- 人人对弈：`docs/plans/2026-09-21-play-mode-design.md` / `docs/plans/2026-09-21-play-mode-implementation.md`
- Lazy SMP 并行搜索：`docs/plans/2026-09-22-lazy-smp-design.md` / `docs/plans/2026-09-22-lazy-smp-implementation.md`
