# 背谱模式支持引擎执子设计

日期：2026-10-04

## 目标

在移动端背谱模式（`MobileHomeView` 的 `reciteMode`）中支持「引擎执子」：用户只需背自己一方的着法，轮到另一方时由「引擎」自动走出棋谱正着，保持背谱流程（校验、计错、SRS）不变。

- 复用设置面板的「执子」值（`none`/`red`/`black`），进入背谱时锁定，背谱中不可改。
- 引擎方自动走**棋谱正着**（直接取本地 `moves[ply]`），不做实时搜索。
- 引擎方落子延迟约 0.5 秒，让用户看清对手着法。
- 引擎方着法不计错、不标记 `revealed`；若为最后一步，走完即完成背谱并提交 SRS。
- 零后端改动，不调用 `best-move`。

## 现状

- `frontend/src/mobile/views/MobileHomeView.vue`：
  - `engineSide`（L271）为设置中的执子方；`onEngineSide`（L518）在 `reciteMode` 时直接 return，即背谱中执子不可改。
  - `isEngineTurn`（L326）/ `maybeEngineMove`（L336）/ `runEngineMove`（L342）是浏览态的引擎自动走子逻辑，调用 `api.bestMove`，仅当 `ply === moves.length` 时生效。
  - `submitReciteMove`（L409）调 `api.checkMove` 按 `ply` 校验棋谱着法；`advanceRecite`（L431）推进并在终局调 `finishRecite`。
  - `revealAnswer`（L437）看答案并推进；`confirmRecite`（L663）进入背谱；`exitRecite`（L466）放弃；`onCellClick`（L477）在背谱态只处理用户走子，不区分执子方。
  - `onOpenGame`（L693）打开棋谱时把 `engineSide` 重置为 `none`。
- `backend/routes/games.py` 的 `check_move`（L535）：按 `ply` 重放棋谱前 N 步并比对 `moves[ply]`，与屏幕实际局面无关；因此引擎方必须走棋谱正着，实时计算会偏离棋谱导致校验错位。
- `frontend/src/mobile/views/__tests__/MobileHomeView.test.js` 已有背谱测试（L514 起），含「背谱态切换执子不会截断棋谱」（L694）。

## 方案选择

**方案 A（采纳）：纯前端状态机推进**

- 新增 `maybeEngineReciteMove()`：背谱中轮到引擎方时，延迟 500ms 直接取 `moves.value[ply]` 推进 `ply+1`，用定时器 + token 防竞态。
- 优点：零后端改动、无网络失败点、与现有 `checkMove` 校验和 SRS 提交流程完全兼容；引擎着法即棋谱正着，天然正确。
- 缺点：无真实引擎参与，仅用延迟营造节奏（需求即走棋谱正着，无需搜索）。

**方案 B（未采纳）：后端接口化** —— 新增接口返回「引擎方该走哪步」，多一次网络往返与失败分支，当前无收益。

**方案 C（未采纳）：复用 `best-move` 实时计算** —— 引擎着法会偏离棋谱，`checkMove` 按棋谱 ply 校验必然错位，背谱无法继续。

## 交互设计

### 进入背谱

- 背谱确认条（`recite-confirm`）新增一行提示，复用当前 `engineSide`：
  - `engineSide === 'red'` → `引擎执红 · 你背黑方`
  - `engineSide === 'black'` → `引擎执黑 · 你背红方`
  - `engineSide === 'none'` → 不显示（保持现状：双方都由用户走）
- 确认「从头背 / 从第 N 步起背」后，若起始 `ply` 轮到引擎方，约 0.5 秒后引擎自动落子。

### 背谱中

- 用户回合：行为不变（`checkMove` 校验，走对推进、走错计错、看答案标记 `revealed`）。
- 引擎回合：延迟 500ms 自动走 `moves[ply]` 并推进；不调后端、不计错、不置 `revealed`。
- 引擎回合（含延迟等待期间）用户点击棋盘无效，不能选中或替走引擎方棋子。
- 用户走对推进后、看答案推进后，若轮到引擎方则自动接走；引擎走完后若仍轮到引擎方则继续（防连续引擎步，理论上象棋红黑交替不会出现）。
- 「看答案」仅在用户回合有意义；引擎回合引擎会自动落子。

### 结束与退出

- 引擎方着法为最后一步（`ply` 到 `moves.length`）→ 自动完成：提交 SRS，提示「背谱完成 · 错 N 次 · 用时 X 秒」。
- 中途「退出背谱」、切换棋谱、编辑/扫描局面、重新进入背谱：取消待执行的引擎定时器，防止幽灵走子。
- `engineSide` 在背谱中保持不变；退出背谱后仍为进入前的设置值（浏览态引擎行为不受影响）。

## 组件设计

### `MobileHomeView.vue`（改动）

- 新增模块级变量：`let reciteEngineTimer = null; let reciteEngineToken = 0;`
- 新增函数：
  - `clearReciteEngineTimer()`：`clearTimeout` + `reciteEngineToken += 1`。
  - `maybeEngineReciteMove()`：条件 `reciteMode && engineSide !== 'none' && !gameOver && ply < moves.length && sideToMove === engineSide`；`setTimeout` 500ms 后 token 校验通过则 `advanceRecite()`；后续引擎接步由 `advanceRecite()` 统一调度。
- 触发点：
  - `confirmRecite()` 末尾（进入背谱，起始轮到引擎方时）。
  - `submitReciteMove()` 走对推进后（在 `finally` 中 `pending=false` 之后）。
  - `revealAnswer()` 推进后。
- 清理点：`exitRecite()`、`confirmRecite()` 开头、`finishRecite()`、`onOpenGame()`、`onApply()`、`onUnmounted()` 调用 `clearReciteEngineTimer()`。
- `onCellClick()` 背谱分支开头新增拦截：`if (engineSide.value !== 'none' && sideToMove.value === engineSide.value) return;`。
- 模板：确认条新增执子提示行（`data-test="recite-engine-side"`，`none` 时不渲染）。
- 不修改 `BoardControls.vue`（控制栏按钮组不变）。

### 后端（不变）

- 复用 `check-move` / `review/submit`，无接口改动。

## 边界与错误处理

- 引擎走子为本地同步推进，无网络失败路径。
- 延迟期间用户退出背谱/切换棋谱：定时器被清理，token 失效，不再落子。
- 起始 `ply` 已到终局时「背谱」按钮本就不显示（`openReciteConfirm` 已有 `ply >= moves.length` 拦截）。
- 引擎方着法数据来自已加载棋谱 `moves[ply]`，包含 `chinese`/`check`/`gameOver`，与浏览态前进一致。
- `none` 时所有新增逻辑 no-op，现有背谱行为与测试不受影响。

## 测试

在 `frontend/src/mobile/views/__tests__/MobileHomeView.test.js` 新增（使用 `vi.useFakeTimers()` 推进 500ms）：

- `engineSide='red'` 进入背谱后自动走第 0 步（`ply` 变 1），且不调 `checkMove`。
- 用户走对推进后，引擎自动接走下一步。
- 引擎方着法为最后一步时自动完成并提交 `submitReview`。
- 延迟期间「退出背谱」后推进定时器不再落子（`ply` 不变）。
- 引擎回合点击棋盘不产生选中/走子。
- 引擎方着法不计错（`reciteMistakes` 不变）。
- 确认条展示执子提示；`none` 时不展示。
- 既有背谱测试保持全绿（`none` 行为不变）。

完成后在 `frontend/` 执行 `npm run build` 更新 `dist/`。
