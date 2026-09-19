# 象棋记谱 Web 项目设计

日期：2026-09-19
技术栈：Flask + Vue 3

## 1. 目标与核心用途

一个单用户本地使用的象棋棋谱管理与背谱工具，核心用途：

- **棋谱库**：录入、分类、检索、打谱回放。
- **背谱默写练习**：逐步默写，走出正着才前进，配合间隔重复调度。

明确不做（YAGNI）：多用户与登录、在线对战、AI 引擎分析、社交分享。

## 2. 需求要点

| 维度 | 决策 |
|---|---|
| 核心用途 | 棋谱库 + 背谱默写练习 |
| 棋谱录入 | 三种都支持：手动录入中文/坐标着法、PGN 文件导入、棋盘摆子自动记谱 |
| 用户与存储 | 单用户 + SQLite |
| 默写形式 | 逐步默写（走出正着才前进） |
| 阵营与复习 | 可选阵营（红/黑/双方）+ 间隔重复调度 |

## 3. 架构与目录结构

```
chess/
├── backend/
│   ├── app.py              # Flask 入口 + 蓝图注册
│   ├── config.py
│   ├── models.py           # SQLAlchemy 模型
│   ├── chess_engine/       # 纯 Python 规则引擎（无 Flask 依赖）
│   │   ├── board.py        # 9x10 棋盘、走子、合法性
│   │   ├── move.py         # 着法表示与生成
│   │   └── parser.py       # 中文/ICCS/PGN 解析
│   ├── srs.py              # SM-2 间隔重复调度
│   ├── routes/
│   │   ├── games.py        # 棋谱 CRUD + 解析
│   │   └── review.py       # 复习队列与提交
│   ├── tests/
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/     # ChessBoard.vue（SVG 自绘）、MoveList.vue 等
│   │   ├── views/          # Library / Editor / Practice / Review
│   │   ├── api/            # axios 封装
│   │   └── stores/         # Pinia
│   ├── package.json
│   └── vite.config.js
└── docs/plans/
```

前后端分离，开发期 Vite 代理 `/api` 到 Flask；生产期 Flask 托管前端构建产物。

### 技术选型汇总

| 层 | 选型 |
|---|---|
| 后端 | Flask + Flask-SQLAlchemy + SQLite，pytest |
| 规则 | 自研纯 Python 引擎 |
| 前端 | Vue 3 + Vite + Pinia + Vue Router + axios + Vitest |
| 棋盘 | 自绘 SVG 组件 |
| 部署 | 开发期 Vite 代理；生产 Flask 托管 dist |

## 4. 数据模型（SQLite）

**games**

- `id`
- `name` 棋谱名称
- `category` 开局体系分类
- `red_player` / `black_player`
- `event` 赛事
- `result` 结果
- `initial_fen` 起始局面（默认标准开局）
- `moves` 着法序列（JSON）
- `practice_side` 背谱阵营：`red` / `black` / `both`
- `created_at` / `updated_at`

**reviews**

- `id`
- `game_id`（FK）
- `due_date`
- `interval`
- `ease_factor`
- `repetitions`
- `lapses`
- `last_reviewed_at`

**review_logs**

- `id`
- `game_id`
- `reviewed_at`
- `correct`
- `mistake_count`
- `duration_ms`

## 5. 后端 API

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/api/games` | 列表（按分类/关键字筛选） |
| POST | `/api/games` | 创建（含三种录入提交） |
| GET/PUT/DELETE | `/api/games/:id` | 详情/更新/删除 |
| POST | `/api/games/parse` | 解析文本棋谱（预览，不入库） |
| POST | `/api/games/import-pgn` | PGN 批量导入 |
| POST | `/api/games/:id/check-move` | 校验某步是否正着 |
| GET | `/api/review/queue` | 今日复习队列 |
| POST | `/api/review/:gameId/submit` | 提交结果并更新调度 |
| GET | `/api/stats` | 掌握度统计 |

**关键点**：`check-move` 由后端规则引擎判定，前端只传当前局面 + 用户着法，规则单一真相源。

## 6. 规则引擎（纯 Python，无 Flask 依赖）

- **棋盘表示**：`9 列 × 10 行`，内部坐标 `(x, y)`，`x∈0..8` 从左到右，`y∈0..9` 从下到上（红方在下）。棋子用 `(side, type)`，side=`red/black`，type=`K/A/B/N/R/C/P`（帅仕相马车炮兵）。
- **核心能力**：
  - `legal_moves(side)`：生成某方全部合法着法（含蹩马腿、塞象眼、炮翻山、将帅照面、过河兵规则）。
  - `is_legal(move)`、`apply_move(move)`、`in_check(side)`、`is_checkmate/stalemate`。
  - **着法表示**：内部统一用 `Move(from, to)`；展示层再转中文/ICCS。
- **解析器 `parser.py`**：
  - **中文着法**（`炮二平五`）：解析“棋子 + 起始纵线 + 动作(进/退/平) + 目标”，注意红黑纵线计数方向相反、同线多子用前/后区分。
  - **ICCS 坐标**（`h2e2`）：直接映射。
  - **PGN**：读取头部标签 + 着法体，兼容中文/ICCS 两种着法，按回合分割。
  - 解析失败给出**具体第几步**的错误信息，便于修正。
- **FEN**：支持中国象棋 FEN（`initial_fen`），默认为标准开局，可支持残局/变着起始局面。

## 7. 间隔重复（SM-2 变体）

- 每个 `game` 对应一条 `reviews` 记录，按 `practice_side` 在复习时确定默写方。
- 提交结果后评分：
  - 全对无提示：`quality=5`
  - 错 1 次：`4`
  - 错 2 次：`3`
  - 错 ≥3 或看答案：`2`
- 标准 SM-2 更新 `ease_factor`（下限 1.3）、`interval`、`repetitions`。
- 错 ≥3 次或看答案 → `lapses+1`，`repetitions` 归零，次日重来。
- **队列规则**：`due_date <= 今天` 的棋谱进入今日队列，按 `due_date` 升序；新棋谱（无 review 记录）默认今日到期。

## 8. 前端交互（Vue 3 + Vite + Pinia）

四个视图：

1. **Library 棋谱库**：卡片/表格列出棋谱，支持按分类、关键字筛选；显示掌握度（新/学习中/已掌握）与下次复习日期；入口按钮：编辑、打谱、默写、删除。
2. **Editor 录入**：
   - **棋盘摆子**：点击棋子→点目标格走子，自动生成着法并实时转中文记谱显示；支持悔棋、清空。
   - **文本粘贴**：粘贴中文着法或 ICCS，点“解析预览”调 `/parse`，成功则逐步高亮预览，失败显示错误步骤。
   - **PGN 导入**：上传 `.pgn` 文件或粘贴内容，批量入库，显示成功/失败清单。
   - 表单字段：名称、分类、红黑方、赛事、结果、背谱阵营。
3. **Practice 打谱**：`ChessBoard` 逐步回放着法，配合 `MoveList` 点击任意步跳转；可切换视角。
4. **Review 默写**：
   - 顶部进度（今日第 N / 共 M）、当前棋谱名。
   - 棋盘只显示局面，轮到需默写方时用户走子；走对则前进并显示对局记录；走错则**标红提示并计错**，允许重试；可点“看答案”。
   - 底部显示实时错误计数与用时；全部走完进入结果页，选择评分后提交 `/submit` 更新调度。

**ChessBoard.vue（SVG 自绘）**：9×10 网格 + 楚河汉界 + 九宫斜线；棋子用圆 + 汉字；点击选中高亮、合法落点圆点提示（调后端合法着法）；响应式尺寸。

## 9. 错误处理与边界

- 后端统一 JSON 错误格式 `{error, detail, step?}`；解析错误带步号。
- 前端 axios 拦截器统一 toast 提示。
- 走子校验失败不改变前端棋盘状态，仅提示。
- 空棋谱、无 due 复习项、非法 FEN 等均有明确提示。

## 10. 测试策略

- **后端 pytest**：规则引擎为核心——马腿/象眼/炮/将帅照面/过河兵/将死判定；中文与 ICCS 解析往返一致性；SM-2 调度边界（ease 下限、lapses 归零）；API 集成测试。
- **前端 Vitest**：棋盘坐标换算、着法显示转换、默写状态机（对/错/看答案）。
- 手动验收：三种录入各走一遍、一次完整默写、复习队列次日到期验证。

## 11. 明确不做的范围

- 多用户、登录、权限
- 在线对战、联机
- AI 引擎分析、局面评估
- 社交分享、排行榜
