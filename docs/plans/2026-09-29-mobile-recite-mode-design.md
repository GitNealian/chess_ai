# 移动端背谱模式设计

日期：2026-09-29

## 目标

在移动端首页（`MobileHomeView`）现有棋盘上原地新增**背谱模式**，让用户凭记忆走出棋谱着法，并按现有 SRS 复习系统记录结果。

- **两个入口**：打开某条棋谱后进入；从顶栏「复习」队列选中棋谱后进入。
- 背谱时**红黑双方都由用户自己走**，不启用引擎。
- 走错：提示、不推进、允许重试，错误数累计；「看答案」揭示并替走当前正确着法，标记 `revealed`。
- 先浏览唤起记忆，再确认起点后开始背；支持从当前浏览位置起背。
- 完成后统一提交 SRS；中途退出不记录。
- 后端零改动，复用已有 `check-move` / `review/queue` / `review/submit`。

## 现状

- `backend/routes/games.py` 的 `check_move`（L407-444）：按 `ply` 重放棋谱前 N 步，校验用户着法，返回 `correct / expected / fen / side_to_move`。`ply` 越界或着法非法返回 400，合法但走错返回 200 + `correct=false`。已有 `backend/tests/test_check_move_api.py` 覆盖。
- `backend/routes/review.py`：`/review/queue`（L48）返回到期/新棋谱，`/review/<id>/submit`（L79）按 `mistake_count`/`revealed`/`duration_ms` 更新 SRS。
- `backend/srs.py` 的 `quality_from_result`（L4）：`revealed`→2；0 错→5；1 错→4；2 错→3；其余→2。
- `frontend/src/api/index.js` 已封装 `checkMove`（L136）、`reviewQueue`（L137）、`submitReview`（L138），但**全前端无任何调用**。
- `frontend/src/mobile/views/MobileHomeView.vue`：`isReview = !!currentGame`（L202），`onCellClick`（L305）在 `isReview` 时直接返回，即打开棋谱后棋盘只读；`onOpenGame`（L355）加载棋谱并进入浏览态。`MobileAnalysis`（L36-42）常显评分/意图。
- `frontend/src/mobile/components/BoardControls.vue`：纯 props/emit 组件（props L51-63，emits L65），按钮显隐由 `can*`/`show*` 控制。
- `frontend/src/mobile/layouts/MobileLayout.vue`：顶栏含收藏/打开棋谱/设置图标，通过 `window` 事件 `mobile-*` 与页面通信。

## 方案选择

**方案 A（采纳）：首页原地背谱 + 扩展 `BoardControls`**

- 背谱过程直接在首页棋盘上进行，不新增路由、不弹大窗；背谱只是首页的一种模式。
- `BoardControls` 增加 `mode`（`browse|recite`）与背谱按钮，背谱态隐藏无关按钮，符合「取消/禁用不可用控制按钮」的诉求。
- 复用 `checkMove` 服务端校验，前端不重写走子规则，也不会提前泄露答案。
- 后端零改动，风险集中在前端。

**方案 B（未采纳）：独立背谱控制条组件**

- 优点：`BoardControls` 零改动、职责更清晰；缺点：新增组件与重复样式。

**方案 C（未采纳）：独立路由页 `/recite`**

- 优点：长流程更规整；缺点：与当前「单页 + 全局弹窗 + window 事件」架构不一致，改动面大。

**方案 D（未采纳）：复用推演弹窗**

- 推演（自由走子 + 引擎分析）与背谱（校验 + 计分 + SRS）职责差异大，混用易出 bug。

## 交互设计

### 入口一 · 从棋谱进入

1. 打开棋谱后处于**浏览态**（现状，可翻页查看整盘棋），控制栏出现「背谱」按钮。
2. 点「背谱」→ 弹出**确认条**（见下），确认后棋盘回到所选起点并进入背谱态。
3. 已在终局（`ply == moves.length`）时「背谱」按钮禁用。

### 入口二 · 从复习队列进入

1. 顶栏新增「复习」图标，点开发送 `mobile-review` 事件，首页打开复习队列弹窗（数据来自 `review/queue`）。
2. 队列列出棋谱名、对手/分类、到期或新；空态提示「暂无待复习棋谱」。
3. 点选某条棋谱 → 关闭弹窗、加载该棋谱进入**浏览态**（不直接进背谱），用户可翻看唤起记忆后再点「背谱」。

### 确认条

- 展示：棋谱名 · 红方 vs 黑方 · 赛事 · 结果 · 分类（空字段不显示）；以及「将从第 N 步开始，背到第 M 步（共 K 步）」。
- 按钮：`从头背`（第 0 步起）、`从第 N 步起背`（当前浏览位置）、`取消`；`N=0` 时只显示「开始背谱」。
- 沿用 `MobileHomeView` 内 `settings-mask` 的内联遮罩卡片写法，不新增组件。

### 背谱中

- 当前轮到哪一方就由用户走哪一方，每一步经 `checkMove` 校验。
- 走对：推进到下一步，继续。
- 走错（200 + `correct=false`）：提示「着法错误，请重试」，不推进、不揭示答案，错误数 +1。
- 非法着法（400）：提示错误，不计错、不推进。
- 「看答案」：揭示并替走当前正确着法（取本地棋谱 `moves[ply]`），置 `revealed=true`，继续。
- 控制栏只保留「翻转 / 看答案 / 退出背谱」；翻页、编辑、扫描、推演、悔棋全部隐藏；引擎执子与右侧分析面板（评分/意图）不显示，避免泄露。

### 结束

- `ply` 达到 `moves.length` → 完成：提交 SRS，显示「背谱完成 · 错 N 次 · 用时 X 秒」，退出背谱态，棋盘停在终局。
- 中途「退出背谱」→ 视为放弃，**不提交 SRS**，回到浏览态。
- 背谱中编辑、扫描、打开其他棋谱时先退出背谱态并重置。

## 组件设计

### `BoardControls.vue`（改动）

- 新增 props：`mode`（默认 `browse`，可选 `recite`）、`showRecite`（浏览态是否显示「背谱」）。
- 新增 emits：`recite`、`reveal`、`exit-recite`。
- 渲染：`mode==='recite'` 时只渲染「翻转 / 看答案 / 退出背谱」；否则渲染现有按钮，并在 `showRecite` 时追加「背谱」。

### `MobileReviewQueue.vue`（新增）

- 打开时调用 `api.reviewQueue()`；props：无；emits：`select(game)`、`cancel`。
- 列表项：棋谱名、对手/分类、到期日或「新」。
- 空态：「暂无待复习棋谱」；加载失败由 axios 拦截器 toast。
- 遮罩/卡片样式复用 `MobileGamePicker.vue`。

### `MobileHomeView.vue`（改动）

- 新增状态：`reciteMode`、`reciteMistakes`、`reciteRevealed`、`reciteStartedAt`、`reciteConfirmOpen`、`reciteStartPly`、`queueOpen`。
- `openReciteConfirm()`：记录默认起点为当前 `ply`，打开确认条。
- `confirmRecite(fromStart)`：`reciteStartPly = fromStart ? 0 : ply.value`；`ply = reciteStartPly`；重置错误数/`revealed`/计时；`reciteMode=true`；关闭确认条。
- `submitReciteMove(move)`：`api.checkMove(currentGame.id, { ply, move })`；`correct` → `ply+1`，到达末尾则 `finishRecite()`；否则错误数 +1、提示。复用 `moveToken` 防竞态。
- `revealAnswer()`：`reciteRevealed=true`；`ply+1`（走出 `moves[ply]`）；到达末尾则 `finishRecite()`。
- `finishRecite()`：计算 `duration_ms`；`api.submitReview(id, { mistake_count, duration_ms, revealed })`；提示结果；`reciteMode=false`。
- `exitRecite()`：`reciteMode=false`，不提交。
- `onOpenGame` / `onApply`：重置背谱状态；队列选择走加载棋谱 + 浏览态。
- `onCellClick`：改为 `if (isReview && !reciteMode) return;`，背谱态走 `submitReciteMove`；背谱态不触发引擎。
- 模板：`MobileAnalysis` 加 `v-if="!reciteMode"`；`BoardControls` 传 `mode`/`show-recite` 并监听 `recite`/`reveal`/`exit-recite`；新增复习队列弹窗与确认条。
- 监听 `mobile-review` 事件打开 `queueOpen`。

### `MobileLayout.vue`（改动）

- 顶栏新增「复习」图标按钮，`publish('mobile-review')`。

### `api/index.js`（不变）

- 已具备 `checkMove` / `reviewQueue` / `submitReview`。

## 数据流

- 走子校验：`POST /api/games/<id>/check-move`，入参 `{ ply, move }`；`ply` 为当前要走的步索引，天然支持任意起点。
- 队列：`GET /api/review/queue`。
- 结果提交：`POST /api/review/<id>/submit`，入参 `{ mistake_count, duration_ms, revealed }`。

## SRS 记录规则

完成时提交一次：

- `mistake_count` = 本次背谱区间内所有走错尝试的累计次数（同一处错 2 次记 2）。
- `revealed` = 是否点过「看答案」。
- `duration_ms` = 从确认开始背谱到完成的耗时。
- quality 由后端 `quality_from_result` 计算：看过答案→2；0 错→5；1 错→4；2 错→3；≥3 错→2。
- 中途退出、网络异常不计入。

## 边界与错误处理

- `check-move` 对非法着法返回 400，对合法但走错返回 200 + `correct=false`，两者分别处理（前者不计错）。
- 网络异常/超时：提示「校验失败，请重试」，不计错、不推进、不置 `revealed`。
- 空棋谱（`moves` 为空）不显示「背谱」按钮。
- 背谱态下引擎执子不介入（`onCellClick` 背谱分支优先，`maybeEngineMove` 不触发），设置中「执子」暂时无效。
- 背谱中编辑、扫描、打开其他棋谱先退出背谱态并归零状态。
- 起点与完成判定：起点可为 0 到 `moves.length-1`；`ply` 到达 `moves.length` 即完成。

## 测试

- `BoardControls.test.js`：新增背谱模式断言（仅「翻转/看答案/退出背谱」及事件）与 `showRecite` 下「背谱」按钮显隐。
- `MobileReviewQueue.test.js`（新增）：mock `api.reviewQueue`，覆盖列表渲染、空态、`select` 事件。
- `MobileHomeView` 背谱流程测试：mock api 覆盖「走对推进 / 走错计错 / 看答案置 revealed / 完成提交 submitReview / 中途退出不提交 / 从指定步起背」。
- 后端 `test_check_move_api.py`、`test_review_api.py` 已存在，无需新增。
- 完成后在 `frontend/` 执行 `npm run build` 更新 `dist/`。
