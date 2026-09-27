# 移动端棋谱推演设计

日期：2026-09-27

## 目标

在移动端首页（`MobileHomeView`）区分两种模式：

1. **自由走子模式**（未打开棋谱：初始状态、编辑局面后）：棋盘可直接自定义走棋，红黑双方均可手动落子。
2. **棋谱只读模式**（打开棋谱后）：棋盘只允许前进/后退浏览，不可走棋。
3. **推演弹窗**：棋谱只读模式下提供「推演」入口。弹窗以「打开弹窗时的棋盘局面」为起点，在弹窗内自由走子，完全不影响棋谱本身，并实时显示该局面的评分。

## 现状

- `frontend/src/mobile/views/MobileHomeView.vue`
  - `onCellClick`（L311）：`engineSide === 'none'` 直接返回；且要求 `ply === moves.length`（回放中不能走子）。因此打开棋谱后（`onOpenGame` L362 会把 `engineSide` 置为 `none`）棋盘完全不可点。
  - `engineSide`（L182）、`isEngineTurn`/`isPlayerTurn`（L213-218）驱动引擎自动走子。
  - `submitMove`（L277）经 `POST /api/engine/validate-move` 校验后写入 `moves`；`onApply`（L395）为编辑局面后回调。
  - `currentGame`（L176）标识是否已打开棋谱。
- `frontend/src/mobile/components/BoardControls.vue`：开局/后退/前进/终局/翻转/悔棋/编辑按钮，`showUndo` 由父组件传入。
- `frontend/src/mobile/components/MobileAnalysis.vue`：以 `initial-fen + moves` 调用 `analyzeStream`，展示评分条、逐层历史与主变，并 `emit('arrows')`。
- `frontend/src/components/ChessBoard.vue`：支持 `position` / `selected` / `arrows` / `flipped` / `cell-click`，规则不在此实现。
- 走子合法性、评分全部由后端判定（`validate-move` / `analyze`），前端不重写规则。

## 方案选择

**方案 A（采纳）：模式区分 + 独立推演弹窗**

- 用 `currentGame` 是否存在区分「棋谱只读」与「自由走子」，改动集中在 `MobileHomeView.onCellClick`。
- 推演以独立弹窗组件承载，快照打开时的局面，内部维护自己的着法序列，关闭即丢弃，天然不影响棋谱。
- 评分直接复用 `MobileAnalysis`，不新增后端接口。

**方案 B（未采纳）：在棋谱 `moves` 上做分支数组**

- 优点：可在主棋盘上直接推演。
- 缺点：与「打开棋谱后棋盘只读」的需求冲突，主/分支状态纠缠，前进后退语义复杂。

## 交互设计

### 模式区分

- `isReview = !!currentGame`。
- **棋谱只读模式**：`onCellClick` 直接返回；不触发引擎走子；`BoardControls` 显示「推演」按钮。
- **自由走子模式**：`onCellClick` 放开 `engineSide === 'none'` 限制，双方手动走子；走子仍经 `validateMove` 校验；保留「执红/执黑」引擎自动应对；状态栏显示轮走方；「悔棋」可用。
- 自由走子模式允许在任意 `ply` 落子（落子即在当前位置截断后续并追加新着法，与现有 `submitMove` 的 `slice(0, ply)` 语义一致）。

### 推演弹窗

- 入口：棋谱只读模式下的「推演」按钮。
- 打开时快照：
  - `baseFen = initialFen.value`
  - `baseMoves = moves.value.slice(0, ply.value)`（即当前看到的棋盘局面）
  - 快照后固定不变，棋谱的 `moves`/`ply` 不再被读写。
- 弹窗内：
  - 棋盘 = 快照局面 + 推演着法；点选起点→终点走子，`validateMove` 校验后追加到内部 `moves`。
  - 红黑双方均手动落子，不启用引擎。
  - 评分复用 `MobileAnalysis`（`score=true`、`intent=false`），传入 `initial-fen=baseFen`、`moves=baseMoves + 推演moves`，随推演实时刷新；`arrows` 回传棋盘显示。
  - 操作：悔棋（撤销一步推演）、翻转、关闭。
- 关闭弹窗即销毁内部状态，丢弃全部推演着法。

## 组件设计

### `MobileHomeView.vue`（改动）

- 新增 `isReview` computed 与推演弹窗状态 `inferOpen`。
- `onCellClick`：`isReview` 时返回；否则放开 `engineSide === 'none'` 限制。
- `statusText`：自由走子模式下显示轮走方/将军；棋谱模式维持只读文案。
- `BoardControls` 传参：`show-undo = !isReview || engineSide !== 'none'`、`can-undo` 对应；新增 `show-infer = isReview`、`can-infer`，监听 `@infer`。
- 打开棋谱（`onOpenGame`）时关闭推演弹窗并强制 `engineSide='none'`。

### `BoardControls.vue`（改动）

- 新增 props `showInfer` / `canInfer`，新增按钮「推演」，`emit('infer')`，仅棋谱模式显示。

### `MobileInferenceDialog.vue`（新增）

- props：`initialFen: String`、`baseMoves: Array`；emits：`close`。
- 内部状态：`moves`（推演着法，初始 `[]`）、`selected`、`hint`、`flipped`、`pending`、`arrows`。
- `pieces` computed = `fenToPieces(initialFen)` 依次 `applyMove` `baseMoves` 与 `moves`。
- 走子：`api.validateMove({ initial_fen, moves: baseMoves + moves, move })`，合法则 `moves.push`。
- 评分：`<MobileAnalysis :initial-fen="initialFen" :moves="baseMoves + moves" :score="true" :intent="false" @arrows="..." />`。
- 遮罩/卡片样式复用 `MobileBoardEditor.vue` 的 `.editor-mask` / `.editor-card` 风格。

## 数据流

- 推演走子校验：`POST /api/engine/validate-move`（无状态，基于 `initial_fen + moves + move`），与自由走子完全一致。
- 推演评分：`POST /api/engine/analyze`（流式），由 `MobileAnalysis` 承担。
- 后端无改动。

## 边界与错误处理

- 棋谱停在回放中间（`ply < moves.length`）打开推演，即以该中间局面为起点。
- 非法着法沿用现有提示（`hint`）。
- 结束后局面（`gameOver`）不阻止推演，仍允许尝试走子，由后端返回结果。
- 关闭弹窗、切换/重新打开棋谱、编辑局面时清空推演状态。
- 推演期间不读写棋谱的 `moves` / `ply` / `selected`，保证「不影响棋谱本身」。

## 测试

- `MobileHomeView.test.js`：棋谱模式下棋盘点击不走子、显示推演按钮；自由模式（无 `currentGame`）下双方手动可走子。
- `BoardControls.test.js`：`showInfer` 控制按钮显隐、点击发 `infer`。
- `MobileInferenceDialog.test.js`（新增）：快照局面正确；走子调用 `validateMove` 且参数含 `baseMoves + 推演moves`；非法着法提示；悔棋；评分组件收到的 `moves` 随推演更新；关闭发 `close`。
- 完成后在 `frontend/` 执行 `npm run build` 更新 `dist/`。
