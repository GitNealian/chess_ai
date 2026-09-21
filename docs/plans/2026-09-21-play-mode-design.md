# 双人同屏对弈与实时分析设计

日期：2026-09-21

## 目标

1. 新增「人人对战」页面，两位棋手在同一台设备上轮流走子。
2. 对局可空白开局，也可从棋谱库某局的任意一步续下。
3. 棋盘支持手动翻转（黑方显示到下方）。
4. 走子合法性由后端规则引擎校验（不在前端重写规则，也不做落点提示）。
5. 每走一步自动对当前局面做 AI 分析，展示方式与打谱页一致（评分条 + 逐层结果 + 双方一步推演箭头）。
6. 支持悔棋（逐步回退，回退后重新分析）。
7. 对局可手动保存到棋谱库。

## 现状

- `ChessBoard.vue` 坐标固定（红方在下），不支持翻转；已支持 `selected` / `legalTargets` / `arrows` 渲染与 `cell-click` 事件。
- `PracticeView.vue` 已实现流式分析面板：`analyzeStream`（`frontend/src/api/index.js`）传 `initial_fen + moves + ply`，逐层结果、评分、箭头。
- 后端 `chess_engine` 具备完整规则能力：`Board.load_fen/apply_move/to_fen`、`board.legal_moves(board.side_to_move)`、`notation.move_to_chinese`。
- 现有 `POST /api/games/:id/check-move` 依赖已保存棋谱的 `moves`，无法用于自由对弈。
- 现有 `POST /api/games` 创建棋谱时会校验着法序列（`_validate_game_moves`），并要求 `initial_fen`。
- 前端无中国象棋规则实现（`utils/chess.js` 只做 FEN 解析与着法应用），故不在前端做合法性校验。

## 方案选择

**方案 A（采纳）：无状态校验接口 + 独立对弈页**

- 后端新增无状态走子校验接口，不依赖棋谱记录。
- 前端新增 `/play` 路由与 PlayView，复用 `ChessBoard` 与 `analyzeStream`。
- 保存时才创建棋谱，棋谱库不产生半成品/草稿数据。

**方案 B（未采纳）：草稿棋谱驱动**

- 进入对弈即创建棋谱记录，每步 PATCH 更新。
- 优点：刷新不丢。
- 缺点：棋谱库残留半成品记录，需要额外清理；与「手动保存」的需求相矛盾。

## 后端接口设计

### `POST /api/engine/validate-move`

无状态，加在 engine 蓝本（`backend/routes/engine.py`）。

请求：

```json
{
  "initial_fen": "可选，缺省为初始局面",
  "moves": [{ "x1": 1, "y1": 2, "x2": 4, "y2": 2 }],
  "move": { "x1": 1, "y1": 2, "x2": 4, "y2": 2 }
}
```

- `moves` 可选（默认 `[]`），按顺序重放；`move` 必填。
- 重放时对每一步做合法性校验，非法返回 400 `{error, detail}`。
- `initial_fen` 由 `Board.load_fen` 校验，非法返回 400。

响应（200）：

```json
{
  "legal": true,
  "fen": "走完后的局面 FEN",
  "side_to_move": "red | black",
  "chinese": "炮二平五",
  "check": false,
  "game_over": null
}
```

- `legal=false` 时返回 `{ "legal": false, "reason": "着法不合法" }`，不含 `fen`/`side_to_move`；用 200 而非 4xx，避免触发前端全局 toast，由对弈页内联提示。
- `reason` 文案覆盖：该方无此棋子、目标被己方棋子占据、着法不合法（含送将）。
- `chinese` 用 `move_to_chinese` 生成（走子前的局面为上下文）。
- `check`：走子后对方是否被将军。
- `game_over`：走子后对方无任何合法着法时给出：
  `{ "winner": "red | black", "reason": "checkmate | stalemate" }`（中国象棋困毙判负，胜方均为走子方）。
- 长将、重复局面和棋不做判定（见「不做」）。

## 前端设计

### 路由与入口

- `/play`：空白开局。
- `/play?game=:id&ply=N`：载入棋谱 `game` 的前 `N` 步作为起始（`initial_fen + moves[:N]`）。
- 打谱页新增「从此处开始对弈」按钮，携带当前 `game.id` 与 `ply` 跳转。
- 棋谱库工具栏新增「新对局」按钮，跳 `/play`。

### ChessBoard 翻转

- 新增 `flipped` prop（默认 `false`）。
- 显示坐标经 180° 旋转映射：`x' = 8 - x`、`y' = 9 - y`；该变换自逆，点击时对 `data-cell` 坐标做同一映射即可反解真实坐标。
- `pieces` / `selected` / `legalTargets` / `arrows` 全部沿用真实坐标，映射只在组件内部完成。
- 楚河汉界文字随翻转旋转 180°。
- 不影响现有页面（默认不翻转）。

### 对弈状态与交互（PlayView）

状态：`initialFen`、`moves`（含后端返回的 `chinese`）、`flipped`、`selected`、`sideToMove`、`gameOver`、`hint`（非法提示）。

- 点击 `side_to_move` 的己方棋子 → 选中；点击同方其他棋子 → 切换选中；点击对方棋子或空白 → 清除选中。
- 选中状态下点击目标格 → 调 `validate-move`：
  - `legal=true` → 应用着法（追加 `move` 与 `chinese`）、更新 `side_to_move`、清除选中、记录 `check`/`game_over`、重启分析。
  - `legal=false` → 内联提示 `reason`，保持选中；下一步操作时清除提示。
- 悔棋按钮：弹出最后一步（对局结束时先清除 `game_over`），截断着法列表，重新分析。
- 翻转按钮：切换 `flipped`。
- 分析面板：沿用打谱页组件结构（评分条 + 逐层结果列表 + 箭头），每步与悔棋后自动重启 `analyzeStream`；参数只传 `initial_fen + moves`（沿用默认时限与深度）。
- 状态区：显示「红方走棋 / 黑方走棋」、将军提示、终局横幅（「红方胜（绝杀）」等），终局后棋盘锁定不可再走。

### 保存到棋谱库

- 对弈页「保存到棋谱库」按钮 → 表单弹窗：名称（默认 `红方 vs 黑方`）、红方、黑方、赛事、分类（默认「对弈」）、结果（下拉 `*` / `1-0` / `0-1` / `1/2-1/2`，终局时自动预填）。
- 提交调 `POST /api/games`（`initial_fen`、`moves`、`practice_side: "both"` 等），成功后跳转该棋谱的打谱页。
- 走子未结束时保存：结果为 `*`（未结束）。

## 错误处理

- 校验请求网络失败/超时：内联提示「校验失败，请重试」，不改变局面。
- `validate-move` 400（FEN 或 moves 非法）：内联提示后端 `detail`。
- 保存失败：弹窗内显示后端 `error`，可重试。
- 对弈页加载棋谱失败（URL 带 `game` 但不存在）：显示错误与重试按钮。

## 测试

- 后端 `tests/test_engine_validate_api.py`：
  - 合法着法返回 `fen/side_to_move/chinese`；
  - 非法着法 `legal=false`；
  - `moves` 重放后校验（含重放序列非法 → 400）；
  - 将军 `check=true`；将死与困毙的 `game_over`；
  - `initial_fen`/`move` 格式错误 → 400。
- 前端 `ChessBoard` 测试：`flipped` 下棋子渲染坐标与点击反解。
- 前端 `PlayView` 测试：选中→校验→走子、非法提示、悔棋、翻转、每步触发 `analyzeStream`、终局锁定、保存参数。
- 打谱页测试：「从此处开始对弈」跳转携带 `game/ply`。

## 不做（YAGNI）

- 棋钟、读秒、计时；
- 长将判负、重复局面和棋、自然限着；
- 自动保存/断线恢复（刷新丢局，由手动保存兜底）；
- 联网对战、观战、AI 自动走子；
- 合法落点提示（此前已知限制不变，本轮不做）。
