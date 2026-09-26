# 移动端棋谱分类浏览设计

日期：2026-09-24

## 背景与目标

移动端「打开」弹窗（`src/mobile/components/MobileGamePicker.vue`）当前只平铺列出棋谱库全部棋谱（`api.listGames` 第一页）。

目标：把棋谱分成「棋谱 / 赛事 / 其它」三类浏览：

- **棋谱**：`category` 以「古谱 · 」开头，两级——先按棋谱集名（如「桔中秘」）分组，进入某集再列出该集棋谱。
- **赛事**：其余且 `event` 非空且 ≠ `'NA'`，直接平铺列表。
- **其它**：其余（`event` 为空或 `'NA'`），直接平铺列表。

列表统一按创建时间倒序（`created_at desc, id desc`），每页 20 条，底部固定分页条（上一页 / 页码输入跳转 / 下一页）。

分类首页三个按钮竖排、居中。非首页视图顶部有「返回」。

## 数据依据

导入脚本 `backend/scripts/import_pgns.py` 写入：`category` 为「古谱 · {书名}」（古谱导入，`--category-prefix "古谱 · "`）或棋手名/「其他棋手」；`event` 为赛事名或书名，缺失时可能为 `'NA'`。

实测库中：`古谱 · 象棋路边摊`、`古谱 · 适情雅趣` 等为古谱集；`China Team Championship` 等为赛事。`event='NA'` 约 731 条，按「无赛事」处理归「其它」。

## 方案选型

| 方案 | 结论 |
|---|---|
| **后端加 `collections` 端点 + `listGames` 增 `scope/sort`，前端状态机（选定）** | 14 万条数据必须服务端过滤分页；不改动未传 `scope` 的现有行为，PC 端不受影响。 |
| 前端拉全量再分类 | 数据量过大，不可行。 |
| 新增独立分类表/字段并迁移数据 | 现有 `category` 前缀已能表达古谱集，YAGNI。不选。 |

## 后端设计

新增 `GET /api/games/collections`：

- 查询参数：`page`（默认 1）、`page_size`（默认 20）。
- 过滤 `Game.category LIKE '古谱 · %'`，按 `category` 分组、去前缀得集名，统计 `count`。
- 排序：`count desc, name asc`。
- 返回 `{ items: [{ name, count }], total, page, page_size }`。

扩展 `GET /api/games`（仅新增可选参数，缺省行为不变）：

| 参数 | 行为 |
|---|---|
| `scope=collection` + `collection={集名}` | `category == f"古谱 · {集名}"` |
| `scope=tournament` | `category NOT LIKE '古谱 · %'` 且 `event` 非空且 ≠ `'NA'` |
| `scope=other` | `category NOT LIKE '古谱 · %'` 且（`event` 为空或 `'NA'`） |
| `sort=created_desc` | 排序 `created_at desc, id desc`；否则沿用现有 `updated_at desc, id desc` |
| 都不传 | 完全保持现状（PC 端 `LibraryView` 不受影响） |

`scope=collection` 且缺 `collection`、或非法 `scope` → 400。

## 前端设计

`api` 新增 `listCollections(params)`；`listGames` 透传 `scope/collection/sort`。

`MobileGamePicker.vue` 内部状态机：

```
view: 'menu' | 'collections' | 'games'
scope: 'collection' | 'tournament' | 'other'   // games 视图用
collection: string                              // collection 时用
page, total, pageSize=20, items, loading, error
```

- `menu`：标题下方四个竖排居中按钮「棋谱」「赛事」「其它」「取消」，样式与布局一致。
  - 棋谱 → `view='collections'`；赛事 → `scope='tournament'` 进 `games`；其它 → `scope='other'` 进 `games`；取消 → `cancel`。
- `collections`：`api.listCollections({page, page_size})`，条目显示集名 + 数量；点击 → `scope='collection'`、`collection=集名`、`page=1`、`view='games'`。
- `games`：`api.listGames({scope, collection, sort:'created_desc', page, page_size})`；点击条目 → `emit('select', game)`。
- 非 `menu` 顶部「返回」：`games`（来源为 collection）→ `collections`；其余 → `menu`，并重置 `page`。非 `menu` 视图的「取消」在底部操作区。
- 底部固定分页条 `MobilePager.vue`：上一页（`page<=1` 禁用）、页码输入框（回车或点跳转）、下一页（`page>=总页数` 禁用）；显示「第 x / y 页」。

新增 `MobilePager.vue`：`props:{ page, pageSize, total }`，`emits:{ change }`，纯展示 + 校验输入页码后 `emit('change', n)`。

## 错误与边界

- 页面为 0 或超出范围时钳制到 `[1, totalPages]`。
- 列表加载失败显示「加载失败」+「重试」（重试当前视图）。
- 空列表显示「暂无棋谱」。

## 测试策略

后端（pytest，`backend/tests/`）：

- `/games/collections`：仅聚合古谱集、去前缀、count、排序、分页。
- `scope=collection` 精确命中该集。
- `scope=tournament` 排除古谱、空 event、`'NA'`。
- `scope=other` 仅无赛事非古谱。
- `sort=created_desc` 与默认排序差异。

前端（Vitest）：

- `MobilePager.test.js`：上一页/下一页禁用态、输入页码跳转、非法输入。
- `MobileGamePicker.test.js`：菜单三按钮；棋谱→集列表→集内棋谱；赛事/其它直接列表；分页跳转；返回；点击棋谱 emit `select`。
- `MobileHomeView.test.js` 现有用例保持通过。

## 不在本次范围

- 分类搜索/筛选、集名搜索；
- 设置弹窗内容；
- PC 端界面改动。
