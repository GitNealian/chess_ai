# 移动端棋盘编辑器设计

日期：2026-09-24

## 背景与目标

移动端 `/m` 首页（`src/mobile/views/MobileHomeView.vue`）已有棋盘与控制栏，控制栏「编辑」按钮当前禁用占位。

目标：点击「编辑」弹出编辑窗口，支持摆子，确认后更新首页棋盘。复用 `ChessBoard.vue` 渲染与 `api.validatePosition` 后端校验。

## 交互模型

弹窗分三部分：上方棋盘、下方候选棋子区、底部（行棋方 + 错误提示 + 确认/取消）。

**状态**：无选中 / 选中棋盘某格棋子 / 选中候选某类型。

棋盘点击（`ChessBoard` 的 `cell-click`）：

| 当前状态 | 目标格 | 行为 |
|---|---|---|
| 无选中 | 有棋子 | 选中该棋子（黄色高亮） |
| 无选中 | 空 | 无操作 |
| 选中棋盘棋子 A | 点 A 自己 | 删除 A，清除选中 |
| 选中棋盘棋子 A | 其他格（空/有子） | 移动 A 过去并覆盖，清除选中 |
| 选中候选类型 T | 任意格（空/有子） | 放置 T 并覆盖，清除选中 |

候选区点击：

| 当前状态 | 行为 |
|---|---|
| 未选中 T | 选中 T |
| 已选中 T | 取消选中 T |

- 点棋盘外空白区域 → 取消选中。
- 候选区某类型 `盘面数量 >= 上限` 时置灰（`filter: grayscale(1)` + 降透明度）且不可点。
- 弹窗内含「清空棋盘」按钮：清空草稿并清除选中。
- 盘面无图片资源，棋子沿用 SVG 汉字绘制。

**数量上限**：帅/将 1；仕/士、相/象、马、车、炮 2；兵/卒 5。

**确认**：调 `api.validatePosition({ pieces, side_to_move })`。`valid:false` 时逐条显示 `errors`；成功则 `emit("apply", pieces)`，首页替换局面并关闭弹窗。校验中禁用交互并显示「校验中…」。
**取消**：关闭弹窗，丢弃草稿，首页不变。

## 方案选型

| 方案 | 结论 |
|---|---|
| **移动端独立组件（选定）** | 新增 `MobileBoardEditor.vue`（弹窗/草稿/交互）+ `MobilePieceChooser.vue`（候选区）。复用 `ChessBoard` 与 `api.validatePosition`，不碰 PC 端代码，符合移动端独立 UI 目标。 |
| 改造 PC 端 `PiecePalette` 两端共用 | 会改动 PC 端并可能回归 `PlayView`；且两端交互语义不同（PC 点子即删），强行共用更绕。不选。 |
| 编辑内嵌首页、不做弹窗 | 偏离「弹窗」要求。不选。 |

## 组件与数据流

新增文件：

```
src/mobile/components/MobileBoardEditor.vue   # 弹窗，props:{pieces} emits:{cancel,apply}
src/mobile/components/MobilePieceChooser.vue  # 候选区，props:{pieces,selected} emits:{select}
src/mobile/components/__tests__/MobileBoardEditor.test.js
src/mobile/components/__tests__/MobilePieceChooser.test.js
```

修改：

- `src/utils/chess.js`：新增导出 `MAX_COUNTS = { K:1, A:2, B:2, N:2, R:2, C:2, P:5 }`（不改现有导出行为）。
- `src/mobile/views/MobileHomeView.vue`：新增 `pieces` 状态（初值 `fenToPieces(INITIAL_FEN)`）、`editorOpen`；棋盘改用 `pieces`；`BoardControls` 传 `:can-edit="true"`、`@edit`；`<MobileBoardEditor v-if="editorOpen" ... @apply @cancel>`。

数据流：打开弹窗复制首页 `pieces` 为草稿 → 编辑只改草稿 → 确认校验成功 `emit apply` → 首页 `pieces` 替换。

## 错误处理

- 校验返回 `valid:false`：显示 `errors` 列表。
- 请求异常：显示 `err.response.data.detail || error || "校验失败，请重试"`。
- 请求期间 `applying=true`，确认按钮禁用，棋盘/候选区点击忽略。

## 测试策略

- `MobilePieceChooser.test.js`：两行顺序与各 7 项；达上限项 disabled；可点项 emit `select`；`selected` 高亮。
- `MobileBoardEditor.test.js`：无选中点棋子=选中；再点自己=删除；选中后点空格=移动；移动覆盖；选候选后点格=放置；取消清除选中；确认不合法显示 errors；确认合法 emit `apply`。
- `MobileHomeView.test.js`：点「编辑」打开弹窗；应用后首页棋盘局面更新。
- 现有测试保持通过。

## 不在本次范围

- 编辑结果保存到棋谱库；
- 走子合法性/对局逻辑（仅摆子合法性校验）；
- 候选区显示同类型多个数量；
- PC 端改动。
