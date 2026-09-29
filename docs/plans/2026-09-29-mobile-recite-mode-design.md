# 移动端背谱模式设计

日期：2026-09-29

## 目标

在移动端首页（`MobileHomeView`）现有棋盘上原地新增**背谱模式**，让用户凭记忆走出棋谱着法，并按现有 SRS 复习系统记录结果。

- **复习入口**：在「打开棋谱」弹窗（`MobileGamePicker`）菜单中新增「复习」，列出待复习棋谱。
- 背谱时**红黑双方都由用户自己走**，不启用引擎。
- 走错：提示、不推进、允许重试，错误数累计；「看答案」揭示并替走当前正确着法，标记 `revealed`。
- 先浏览唤起记忆，再确认起点后开始背；支持从当前浏览位置起背。
- 新增「上一盘 / 下一盘」棋谱导航，按打开来源切换。
- 完成后统一提交 SRS；中途退出不记录。
- 后端零改动，复用已有 `check-move` / `review/queue` / `review/submit` / `games` 列表接口。

## 现状

- `backend/routes/games.py` 的 `check_move`（L407-444）：按 `ply` 重放棋谱前 N 步，校验用户着法，返回 `correct / expected / fen / side_to_move`。`ply` 越界或着法非法返回 400，合法但走错返回 200 + `correct=false`。已有 `backend/tests/test_check_move_api.py` 覆盖。
- `backend/routes/review.py`：`/review/queue`（L48）返回到期/新棋谱，`/review/<id>/submit`（L79）按 `mistake_count`/`revealed`/`duration_ms` 更新 SRS。
- `backend/routes/games.py` 的 `list_games`（L68）支持 `scope=collection/event/tournament/other/recent/favorite` 与分页，`COLLECTION_PREFIX = "古谱 · "`（L14）。
- `backend/srs.py` 的 `quality_from_result`（L4）：`revealed`→2；0 错→5；1 错→4；2 错→3；其余→2。
- `frontend/src/api/index.js` 已封装 `checkMove`（L136）、`reviewQueue`（L137）、`submitReview`（L138），但**全前端无任何调用**；`reviewQueue` 目前不接收参数。
- `frontend/src/mobile/views/MobileHomeView.vue`：`isReview = !!currentGame`（L202），`onCellClick`（L305）在 `isReview` 时直接返回，即打开棋谱后棋盘只读；`onOpenGame`（L355）加载棋谱并进入浏览态。`MobileAnalysis`（L36-42）常显评分/意图。
- `frontend/src/mobile/components/MobileGamePicker.vue`：菜单含 棋谱/赛事/其它/最近/收藏；`emit('select', item)` 只传棋谱；`load()`（L19）按 view 拉取数据。
- `frontend/src/mobile/components/BoardControls.vue`：纯 props/emit 组件，按钮平铺 `flex-wrap`（样式 L69-95）。
- `frontend/src/mobile/layouts/MobileLayout.vue`：顶栏含收藏/打开棋谱/设置图标，通过 `window` 事件 `mobile-*` 与页面通信。

## 方案选择

**方案 A（采纳）：首页原地背谱 + 扩展 `BoardControls`**

- 背谱过程直接在首页棋盘上进行，不新增路由、不弹大窗；背谱只是首页的一种模式。
- `BoardControls` 增加 `mode`（`browse|recite`）、导航与背谱按钮，并改为单行横向滚动布局。
- 复用 `checkMove` 服务端校验，前端不重写走子规则，也不会提前泄露答案。
- 后端零改动，风险集中在前端。

**方案 B（未采纳）：独立背谱控制条组件** —— 新增组件与重复样式。

**方案 C（未采纳）：独立路由页 `/recite`** —— 与「单页 + 全局弹窗 + window 事件」架构不一致。

**方案 D（未采纳）：复用推演弹窗** —— 推演与背谱职责差异大。

**方案 E（未采纳）：独立顶栏复习入口组件** —— 改为并入打开棋谱弹窗，减少入口与组件。

## 交互设计

### 入口 · 打开棋谱弹窗新增「复习」

- `MobileGamePicker` 菜单新增「复习」项（顺序：棋谱 / 赛事 / 复习 / 其它 / 最近 / 收藏 / 返回）。
- 进入后调用 `reviewQueue({ limit: 200 })`，列出棋谱名、对手、到期或「新」；空态「暂无待复习棋谱」。
- 点选某条棋谱 → `emit('select', game, source)`，`source = { type: 'review' }`。
- 顶栏**不新增**复习图标，仍为 收藏 / 打开棋谱 / 设置。

### 来源记录（`navSource`）

打开棋谱时，`MobileGamePicker` 的 `select` 事件附带来源信息，首页经 `normalizeSource` 处理后保存为 `navSource`：

- 棋谱集/赛事/其它/最近/收藏 → `{ type, collection?, event? }`。
- 复习 → `{ type: 'review' }`。
- **「最近」特例**：转换为该棋谱所属分类——`category` 以「古谱 · 」开头 → `{ type: 'collection', collection }`；否则 `event` 非空且非 `NA` → `{ type: 'event', event }`；两者都无 → `navSource = null`（不提供导航）。

### 上一盘 / 下一盘

- 显示条件：已打开棋谱且 `navSource` 非空（自由摆盘、编辑局面不显示）。
- 取目标：按 `navSource` 重新拉取来源有序列表（复习用 `reviewQueue`，其余用 `listGames` 分页拉全），定位当前棋谱，取前/后一条。
- 边界：第一盘提示「已是第一盘」，最后一盘提示「已是最后一盘」。
- 切换后：退出背谱态（不提交 SRS）→ 加载目标棋谱 → **浏览态**，可再点「背谱」。

### 切换确认

- 若 `reciteMode` 为真（背谱进行中），点「上一盘/下一盘」先弹确认框：
  - 文案：「当前背谱尚未完成，切换将放弃本次进度且不记录。」
  - 按钮：`继续背谱`（取消）、`放弃并切换`。
- 确认后退出背谱态（不提交 SRS）→ 切换。
- 背谱已完成（`reciteMode=false`）时直接切换，不弹确认。

### 背谱确认条

- 浏览态点「背谱」→ 弹出确认条，展示：棋谱名 · 红方 vs 黑方 · 赛事 · 结果 · 分类（空字段不显示）；以及「将从第 N 步开始，背到第 M 步（共 K 步）」。
- 按钮：`从头背`（第 0 步起）、`从第 N 步起背`（当前浏览位置）、`取消`；`N=0` 时只显示「开始背谱」。
- 已在终局（`ply == moves.length`）时「背谱」按钮不显示。
- 沿用 `MobileHomeView` 内 `settings-mask` 的内联遮罩卡片写法。

### 背谱中

- 当前轮到哪一方就由用户走哪一方，每一步经 `checkMove` 校验。
- 走对：推进到下一步，继续。
- 走错（200 + `correct=false`）：提示「着法错误，请重试」，不推进、不揭示答案，错误数 +1。
- 非法着法（400）：提示错误，不计错、不推进。
- 「看答案」：揭示并替走当前正确着法（取本地棋谱 `moves[ply]`），置 `revealed=true`，继续。
- 背谱态控制栏：`上一盘 / 下一盘 / 翻转 / 看答案 / 退出背谱`；引擎执子与右侧分析面板（评分/意图）不显示，避免泄露。

### 结束

- `ply` 达到 `moves.length` → 完成：提交 SRS，显示「背谱完成 · 错 N 次 · 用时 X 秒」，退出背谱态，棋盘停在终局。
- 中途「退出背谱」→ 视为放弃，**不提交 SRS**，回到浏览态。
- 背谱中编辑、扫描、打开其他棋谱时先退出背谱态并重置。

## 组件设计

### `BoardControls.vue`（改动）

- **布局**：单行横向滚动。容器 `overflow-x` 隐藏滚动条（`scrollbar-width: none`、`::-webkit-scrollbar{display:none}`），按钮 `flex: 0 0 auto` 不换行；两端浮半透明箭头 `‹ / ›`，仅当该方向可滚动时显示，点击平滑滚动约 80% 视宽，通过 `scroll` 事件与 `ResizeObserver` 更新显隐。
- 新增 props：`mode`（默认 `browse`）、`showNav`、`showRecite`。
- 新增 emits：`prev-game`、`next-game`、`recite`、`reveal`、`exit-recite`。
- 按钮顺序：
  - 浏览态：`开局 后退 前进 终局` + `上一盘 下一盘`（`showNav`）+ `翻转` + `悔棋`（`showUndo`）+ `编辑 扫描` + `推演`（`showInfer`）+ `背谱`（`showRecite`）。
  - 背谱态：`上一盘 下一盘`（`showNav`）+ `翻转` + `看答案` + `退出背谱`。

### `MobileGamePicker.vue`（改动）

- 菜单新增「复习」按钮，`view='review'`。
- `load()` 支持 `view==='review'`：调用 `api.reviewQueue({ limit: 200 })`，`items` 存 `entry` 列表。
- `title()` / `back()` 支持 `review`（返回菜单）。
- 列表渲染 `review`：显示 `entry.game.name`、`红 vs 黑`、`新` 或 `到期 <due_date>`；点击 `emit('select', entry.game, { type: 'review' })`。
- 棋谱 `games` 视图点击改为 `emit('select', item, { type: scope, collection?, event? })`。

### `MobileHomeView.vue`（改动）

- 新增状态：`reciteMode`、`reciteMistakes`、`reciteRevealed`、`reciteStartedAt`、`reciteConfirmOpen`、`reciteStartPly`、`navSource`、`navConfirmOpen`、`navDirection`。
- `onOpenGame(game, source)`：保存 `navSource = normalizeSource(game, source)`；重置背谱状态与导航确认。
- `normalizeSource(game, source)`：实现「最近」特例。
- `openReciteConfirm()` / `confirmRecite(fromStart)`：确认条与进入背谱，`ply` 从 `reciteStartPly` 开始。
- `submitReciteMove(move)`：`api.checkMove(currentGame.id, { ply, move })`；走对 `ply+1` 并判完成；走错错误数 +1；网络失败不计错。复用 `moveToken`。
- `revealAnswer()`：`reciteRevealed=true`；`ply+1`（走出 `moves[ply]`）；判完成。
- `finishRecite()`：计算 `duration_ms`；`api.submitReview`；提示结果；`reciteMode=false`。
- `exitRecite()`：`reciteMode=false`，不提交。
- `requestNav(direction)` / `confirmNav()` / `runNav(direction)` / `findAdjacent(src, currentId, direction)` / `collectSourceGames(src)`：导航逻辑与边界提示。
- `onCellClick`：`if (isReview.value && !reciteMode.value) return;`，背谱态走 `submitReciteMove`，不触发引擎。
- 模板：`MobileAnalysis` 加 `v-if="!reciteMode"`；`BoardControls` 传 `mode` / `show-nav` / `show-recite` 并监听导航与背谱事件；新增背谱确认条与切换确认框。
- `onApply` 与自由摆盘状态重置 `navSource`。

### `MobileLayout.vue`（不变）

- 顶栏不加复习图标。

### `api/index.js`（小改）

- `reviewQueue: (params) => http.get("/review/queue", { params })`，其余不变。

## 数据流

- 走子校验：`POST /api/games/<id>/check-move`，入参 `{ ply, move }`。
- 复习列表与导航：`GET /api/review/queue?limit=200`。
- 其它来源导航：`GET /api/games?scope=&collection=&event=&sort=created_desc&page=&page_size=100` 循环拉页。
- 结果提交：`POST /api/review/<id>/submit`，入参 `{ mistake_count, duration_ms, revealed }`。

## SRS 记录规则

完成时提交一次：

- `mistake_count` = 本次背谱区间内所有走错尝试的累计次数（同一处错 2 次记 2）。
- `revealed` = 是否点过「看答案」。
- `duration_ms` = 从确认开始背谱到完成的耗时。
- quality 由后端 `quality_from_result` 计算：看过答案→2；0 错→5；1 错→4；2 错→3；≥3 错→2。
- 中途退出、切换棋谱、网络异常不计入。

## 边界与错误处理

- `check-move` 对非法着法返回 400，对合法但走错返回 200 + `correct=false`，两者分别处理（前者不计错）。
- 网络异常/超时：提示「校验失败，请重试」，不计错、不推进、不置 `revealed`。
- 空棋谱（`moves` 为空）不显示「背谱」按钮。
- 导航：来源列表拉取失败提示「切换失败，请重试」；定位不到当前棋谱不提供切换。
- 「最近」谱无棋谱集且无赛事时不显示导航。
- 背谱态下引擎执子不介入，设置中「执子」暂时无效。
- 起点与完成判定：起点可为 0 到 `moves.length-1`；`ply` 到达 `moves.length` 即完成。

## 测试

- `BoardControls.test.js`：默认 7 按钮；`showRecite` 显隐与 `recite` 事件；`showNav` 显隐与 `prev-game`/`next-game` 事件；`mode='recite'` 按钮组与 `reveal`/`exit-recite` 事件。
- `MobileGamePicker.test.js`：菜单「复习」进入后调 `reviewQueue`；空态；点选 `select` 携带 `{ type:'review' }`；棋谱视图 `select` 携带来源 `{ type, collection/event }`。
- `MobileHomeView` 测试：背谱入口与确认条；走对推进 / 走错计错 / 看答案置 `revealed` / 完成提交 `submitReview` / 中途退出不提交；上一盘下一盘切换、边界提示、背谱中切换弹确认、最近来源转换。
- 后端 `test_check_move_api.py`、`test_review_api.py` 已存在，无需新增。
- 完成后在 `frontend/` 执行 `npm run build` 更新 `dist/`。
