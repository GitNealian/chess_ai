# 移动端棋盘控制栏设计

日期：2026-09-24

## 背景与目标

移动端 `/m` 首页（`src/mobile/views/MobileHomeView.vue`）已在棋盘上方展示初始局面，但棋盘下方缺少操作入口。

目标：在首页棋盘下方新增一排控制按钮，为后续打谱/复盘/编辑交互预留统一入口。

本次范围：

- 在棋盘下方渲染一排控制按钮：开局、后退、前进、终局、翻转、编辑；
- 仅「翻转」生效（切换 `ChessBoard` 的 `flipped`）；
- 其余按钮因当前首页无着法数据而禁用占位；
- 不改动现有 PC 端 UI 与其它路由。

## 方案选型

| 方案 | 结论 |
|---|---|
| **抽独立展示组件 `BoardControls.vue`（选定）** | 纯 props/emits 驱动，页面持有状态与业务。后续移动端打谱/编辑页可复用，职责清晰、易测。 |
| 内联写进 `MobileHomeView` | 改动最小，但视图臃肿，后续复用需搬代码。不选。 |
| 组件 + 导航组合式函数 | 本次无真实着法数据，属过度设计（YAGNI）。不选。 |

## 组件设计

新增 `src/mobile/components/BoardControls.vue`（纯展示组件）：

```
props:
  flipped:  Boolean   # 当前棋盘是否翻转
  canStart: Boolean   # 能否跳到开局
  canPrev:  Boolean   # 能否后退一步
  canNext:  Boolean   # 能否前进一步
  canEnd:   Boolean   # 能否跳到终局
  canEdit:  Boolean   # 能否进入编辑
emits:
  start / prev / next / end / flip / edit
```

- 按「开局、后退、前进、终局、翻转、编辑」顺序渲染 6 个文字按钮；
- 每个按钮 `type="button"`，`disabled` 由对应 `canXxx` 决定；未禁用时点击原样 `emit` 对应事件；
- 组件不持有任何业务状态。

## 页面接线

`MobileHomeView.vue`：

- 棋盘下方插入 `<BoardControls>`；
- 持有本地 `flipped` ref（`false`），`@flip="flipped = !flipped"`；
- 向 `ChessBoard` 传入 `:flipped="flipped"`；
- 本次 `canStart/canPrev/canNext/canEnd/canEdit` 全部传 `false`（无着法数据 → 禁用占位）。

## 布局样式

- `display: flex; gap: 8px`，每个按钮 `flex: 1 1 0`，`min-height: 44px`（触控友好），字号 14px，`white-space: nowrap`；
- 浅底描边风格：白底 + `#cbb89a` 边框 + `#7a3b2e` 文字，避免 6 个深色块视觉过重；
- 禁用态：`opacity: .4; cursor: not-allowed`。

## 测试策略

- 新增 `src/mobile/components/__tests__/BoardControls.test.js`：渲染 6 个按钮；点击「翻转」emit `flip`；`canXxx` 为 false 时按钮禁用且不 emit。
- 更新 `src/mobile/views/__tests__/MobileHomeView.test.js`：控制栏存在；点击「翻转」后 `ChessBoard` 收到 `flipped=true`。
- 现有测试保持通过。

## 不在本次范围

- 真实着法数据加载与逐步回放；
- 编辑按钮跳转 `/editor`；
- 自动播放/暂停；
- PC 端新 UI。
