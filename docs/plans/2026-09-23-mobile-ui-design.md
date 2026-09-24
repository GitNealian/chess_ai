# 新移动端 UI（/m）骨架设计

日期：2026-09-23

## 背景与目标

现有前端是单一 Vue3 SPA，PC 与移动端共用同一套页面，靠 `@media`（768px 断点）做响应式适配。随着功能增多，响应式适配逐渐难以同时满足两端交互诉求。

目标：新起一套「移动端与 PC 端各自独立实现」的 UI，本次先只搭移动端骨架，通过独立路由地址呈现，不改动现有 UI 的视觉与行为。

- 隔离目标：现有 5 条路由、`App.vue` 的 topbar/tabbar 渲染结果与样式保持不变。
- 复用目标：新 UI 复用现有 `src/api` 与 `src/stores` 数据层，不重复造数据逻辑。
- 本次范围：移动端 shell + 单个占位首页；具体页面后续按需扩展。

## 方案选型

| 方案 | 结论 |
|---|---|
| **新目录 + `/m` 前缀，复用 api/stores（选定）** | 新建 `src/mobile/` 存放移动端专属页面与组件，路由挂 `/m/*`；数据层复用。改动隔离、不污染旧 UI，且不重复造数据层。 |
| 新目录 + `/m` 前缀，数据层也独立 | 与旧 UI 完全隔离，但短期重复代码；当前数据交互方式无大改需求。不选。 |
| 独立构建入口（独立 HTML/应用） | 隔离最彻底，但需新增 Vite 入口与部署分流，配置成本最高，与「先搭架子」不匹配。不选。 |

## 路由与目录结构

现有路由全部保持不变，仅追加移动端路由：

```
/m            → MobileLayout（父）
  ""          → MobileHomeView（占位首页）
/m/:pathMatch(.*)* → 兜底重定向回 /m
```

新增文件（与旧代码物理隔离）：

```
src/mobile/
  layouts/MobileLayout.vue    # 移动端 shell：顶部标题栏 + 底部 tabbar + <router-view/>
  views/MobileHomeView.vue    # 占位首页
  views/__tests__/MobileHomeView.test.js
```

## 旧 shell 让位方式

`App.vue` 新增判断：当 `route.path` 以 `/m` 开头时，只渲染 `<router-view/>`（移动端 shell 由 `MobileLayout` 自带）；其余路径走现有 topbar/tabbar 逻辑。旧 UI 的模板分支、DOM 与样式零改动。全局 toast 保留。

## 复用与数据层

`src/api`、`src/stores` 直接复用；骨架阶段占位页不接数据，仅预留结构。

首页上方展示初始局面棋盘：复用现有纯 props 驱动的 `src/components/ChessBoard.vue`（公共渲染组件复用，页面布局与交互仍由移动端独立实现），局面由 `src/utils/chess.js` 的 `INITIAL_FEN` + `fenToPieces` 在本地生成，不涉及接口。

## 进入方式

直接访问 `/m`。旧 UI 不加任何入口链接，保持不动。

## 测试策略

新增 `MobileHomeView` 冒烟测试：挂载占位页断言渲染，并验证路由表存在 `/m` 且解析到移动端布局。现有测试全部保持通过。

## 不在本次范围

- 移动端具体业务页面（棋谱库/录入/练习/对弈/复习）的实现；
- PC 端新 UI；
- 旧 UI 的迁移或下线；
- 设备自动分流（按 UA 跳转 `/m`）。
