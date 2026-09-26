# 移动端打开棋谱与打谱设计

日期：2026-09-24

## 背景与目标

移动端 `/m` 首页（`src/mobile/views/MobileHomeView.vue`）已有棋盘、控制栏（开局/后退/前进/终局/翻转/编辑）与编辑弹窗，但控制栏的前进后退一直禁用，页面也无入口载入棋谱。

目标：在棋盘上方靠右新增「打开」「设置」两个按钮。

- 「打开」：弹出棋谱库列表，选一局载入首页，进入打谱状态，控制栏开局/后退/前进/终局用于逐步回放。
- 「设置」：弹出空弹窗（占位，后续再填）。

将首页局面模型从单一 `pieces` 改为「初始局面 + 着法 + 当前步」：

```
pieces = basePieces 依次应用 moves[0..ply)
```

自由局面（初始/编辑后）即 `moves = []`、`ply = 0`。

## 交互与状态

**顶部工具条**：棋盘上方、靠右，「打开」「设置」。

**打开弹窗** `MobileGamePicker.vue`：

- 打开时 `api.listGames()`，列出棋谱（主标题名称，副标题「红方 vs 黑方」）。
- 点击某局 → `emit("select", game)`；底部「取消」→ `emit("cancel")`；点遮罩空白 → `cancel`。
- 空列表显示「暂无棋谱」；加载中/失败有提示，失败可重试。

后端 `Game.to_dict()` 已含 `initial_fen` 与 `moves`，列表项可直接载入，无需二次拉详情。

**打谱状态**（`MobileHomeView`）：

- 载入：`basePieces = fenToPieces(game.initial_fen)`、`moves = game.moves || []`、`ply = 0`，关闭弹窗。
- 控制栏：`canStart = canPrev = ply > 0`；`canNext = canEnd = ply < moves.length`。
  - 开局 → `ply = 0`；后退 → `ply - 1`；前进 → `ply + 1`；终局 → `ply = moves.length`。
- 翻转保持当前值。

**编辑**：编辑弹窗展示当前显示的局面；应用后 `basePieces = 草稿`、`moves = []`、`ply = 0`，即退出打谱回到自由局面。

**设置**：空弹窗，标题「设置」+「关闭」按钮。

## 方案选型

| 方案 | 结论 |
|---|---|
| **新增 `MobileGamePicker.vue` + 首页内联设置弹窗（选定）** | 打开选择器独立可测；设置仅占位，内联足够。首页用 `basePieces/moves/ply` 统一自由与打谱局面。 |
| 打开/设置都抽成组件 | 设置弹窗仅标题与关闭，抽组件收益低。不选。 |
| 打开跳转到独立打谱页 | 与「载入首页 + 控制栏回放」需求不符。不选。 |

## 组件与数据流

新增：

```
src/mobile/components/MobileGamePicker.vue
src/mobile/components/__tests__/MobileGamePicker.test.js
```

修改：

- `src/mobile/views/MobileHomeView.vue`：顶部按钮、`basePieces/moves/ply`、控制栏接线、打开选择器、设置弹窗。
- `src/mobile/views/__tests__/MobileHomeView.test.js`：新增用例。

复用：`ChessBoard`、`BoardControls`、`MobileBoardEditor`、`utils/chess` 的 `applyMove`、`api.listGames`。

## 错误处理

- 棋谱列表加载失败：显示「加载失败」+「重试」。
- 载入的棋谱 `initial_fen` 缺失时回退 `INITIAL_FEN`。
- 编辑应用校验失败走 `MobileBoardEditor` 既有逻辑，不改变首页。

## 测试策略

- `MobileGamePicker.test.js`：加载渲染列表；点击 emit `select`；空列表提示；取消 emit `cancel`。
- `MobileHomeView.test.js`：点打开显示选择器；选中棋谱后棋盘为初始局面、前进可用、点击前进后局面变化；点设置显示弹窗；打谱中点编辑应用后退出打谱（前进禁用）。
- 现有测试保持通过。

## 不在本次范围

- 设置项具体内容；
- 着法列表/步数显示；
- 保存棋谱、自动播放；
- PC 端改动。
