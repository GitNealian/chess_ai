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
│   ├── srs.py              # SM-2 间隔重复调度
│   ├── routes/
│   │   ├── games.py        # 棋谱 CRUD、解析、PGN 导入、走法校验
│   │   └── review.py       # 复习队列、提交、统计
│   ├── tests/              # pytest 测试
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/     # ChessBoard.vue（SVG 自绘）
│   │   ├── views/          # Library / Editor / Practice / Review
│   │   ├── stores/         # Pinia：library / practice
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
# 后端
cd backend && .venv/bin/python -m pytest

# 前端
cd frontend && npx vitest run
```

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
| GET | `/api/review/queue` | 今日复习队列 |
| POST | `/api/review/:gameId/submit` | 提交复习结果并更新调度 |
| GET | `/api/stats` | 掌握度统计 |

错误统一返回 `{error, detail?, step?}`。

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

## 设计文档与实现计划

- 设计文档：`docs/plans/2026-09-19-chess-practice-design.md`
- 实现计划：`docs/plans/2026-09-19-chess-practice-implementation.md`
