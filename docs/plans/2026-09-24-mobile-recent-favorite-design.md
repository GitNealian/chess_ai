# 移动端「最近」「收藏」设计

日期：2026-09-24

## 背景与目标

「打开」弹窗已有「棋谱 / 赛事 / 其它」分类。新增两个分类：

- **最近**：打开棋谱时记录/更新打开时间，按打开时间倒序直接列出。
- **收藏**：打开棋谱后，首页棋盘左上角（与「打开/设置」同行）显示星标按钮，未收藏空心 ☆、已收藏实心 ★，点击切换；「收藏」分类按收藏时间倒序直接列出。

## 数据模型

新增表 `game_activity`（不改动既有 `games` 表，`db.create_all()` 会自动建表）：

```
game_activity:
  game_id        PK, FK games.id
  last_opened_at DateTime NULL
  favorited_at   DateTime NULL
```

`Game` 增加关系 `activity = relationship("GameActivity", uselist=False, cascade="all, delete-orphan")`；`Game.to_dict()` 增加 `"favorited": bool(activity and activity.favorited_at)`。

## 接口

| 方法 | 路径 | 行为 |
|---|---|---|
| POST | `/api/games/<id>/open` | upsert `last_opened_at = now`；返回 `{ last_opened_at, favorited }` |
| POST | `/api/games/<id>/favorite` | 切换 `favorited_at`（有→null，无→now）；返回 `{ favorited, favorited_at }` |
| GET | `/api/games?scope=recent` | join `game_activity`，`last_opened_at` 非空，按 `last_opened_at desc, id desc` 分页 |
| GET | `/api/games?scope=favorite` | `favorited_at` 非空，按 `favorited_at desc, id desc` 分页 |

`<id>` 不存在返回 404。其余 `scope/sort` 与既有行为不变。

## 前端

- `api.openGame(id)`、`api.favoriteGame(id)`。
- `MobileGamePicker`：菜单增加「最近」「收藏」，共 5 个分类 + 取消，竖排居中同样式；两者都直接进入 `games` 列表（`scope=recent` / `scope=favorite`），不分两级。
- `MobileHomeView`：
  - 新增 `currentGame` 状态（载入棋谱时设为该棋谱，编辑应用后置空）。
  - 顶部工具条：左侧星标按钮（`v-if="currentGame"`），右侧「打开/设置」；星标显示 ★/☆，点击调 `api.favoriteGame` 并更新状态。
  - 载入棋谱（`onOpenGame`）时调用 `api.openGame(id)`，成功后以返回的 `favorited` 校准星标；请求失败静默（不阻塞载入）。
- 「最近」「收藏」列表项点击同样走载入流程，因此会更新打开时间。

## 错误与边界

- 打开/收藏接口 404：前端静默忽略。
- 星标状态以服务端返回为准。
- 打开时间/收藏时间为 UTC。

## 测试策略

- 后端 pytest：`open` 写入并更新、`favorite` 切换、`recent`/`favorite` 排序与分页、404。
- 前端 Vitest：`MobileGamePicker` 最近/收藏入口与列表；`MobileHomeView` 星标显示条件、点击切换、载入时记录打开。

## 不在本次范围

- 收藏夹分组、批量管理、取消打开记录；
- PC 端改动。
