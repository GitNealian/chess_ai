# 移动端棋谱分类浏览 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 「打开」弹窗按「棋谱（古谱集两级）/赛事/其它」分类浏览，列表按创建时间倒序、每页 20 条，底部分页条支持页码跳转。

**Architecture:** 后端新增 `GET /api/games/collections` 聚合古谱集，`GET /api/games` 增加 `scope/sort` 参数（缺省不变）。前端 `MobileGamePicker` 改为 `menu/collections/games` 状态机，抽出 `MobilePager.vue`。

**Tech Stack:** Flask + SQLAlchemy + pytest；Vue 3 + Vitest + Vue Test Utils。

**设计文档:** `docs/plans/2026-09-24-mobile-game-categories-design.md`

约定：`COLLECTION_PREFIX = "古谱 · "`；`event` 为空或 `'NA'` 视为无赛事。

---

### Task 1: 后端分类查询

**Files:**
- Modify: `backend/routes/games.py`
- Test: `backend/tests/test_games_api.py`

**Step 1: 写失败测试**（追加到 `test_games_api.py`）：

```python
def test_scope_collection_matches_exact(client):
    client.post("/api/games", json=_payload(name="古谱A", category="古谱 · 桔中秘"))
    client.post("/api/games", json=_payload(name="古谱B", category="古谱 · 梅花谱"))
    body = client.get("/api/games?scope=collection&collection=桔中秘").get_json()
    assert [g["name"] for g in body["items"]] == ["古谱A"]


def test_scope_collection_requires_name(client):
    assert client.get("/api/games?scope=collection").status_code == 400


def test_scope_tournament_excludes_old_and_blank(client):
    client.post("/api/games", json=_payload(name="赛事", category="棋手", event="联赛"))
    client.post("/api/games", json=_payload(name="古谱", category="古谱 · 桔中秘", event="桔中秘"))
    client.post("/api/games", json=_payload(name="空", category="棋手", event=""))
    body = client.get("/api/games?scope=tournament").get_json()
    assert [g["name"] for g in body["items"]] == ["赛事"]


def test_scope_other_blank_or_na(client):
    client.post("/api/games", json=_payload(name="空", category="棋手", event=""))
    client.post("/api/games", json=_payload(name="NA", category="棋手", event="NA"))
    client.post("/api/games", json=_payload(name="赛事", category="棋手", event="联赛"))
    body = client.get("/api/games?scope=other").get_json()
    assert sorted(g["name"] for g in body["items"]) == ["NA", "空"]


def test_scope_invalid(client):
    assert client.get("/api/games?scope=xx").status_code == 400


def test_collections_aggregate(client):
    client.post("/api/games", json=_payload(name="a1", category="古谱 · 桔中秘"))
    client.post("/api/games", json=_payload(name="a2", category="古谱 · 桔中秘"))
    client.post("/api/games", json=_payload(name="b1", category="古谱 · 梅花谱"))
    client.post("/api/games", json=_payload(name="c", category="棋手"))
    body = client.get("/api/games/collections").get_json()
    assert body["total"] == 2
    assert body["items"][0] == {"name": "桔中秘", "count": 2}
    assert body["items"][1] == {"name": "梅花谱", "count": 1}


def test_sort_created_desc(client):
    import time as _t
    for i in range(3):
        client.post("/api/games", json=_payload(name=f"n{i}"))
        _t.sleep(0.01)
    body = client.get("/api/games?sort=created_desc").get_json()
    assert body["items"][0]["name"] == "n2"
```

**Step 2: 运行确认失败** — `cd backend && .venv/bin/python -m pytest tests/test_games_api.py -q`。

**Step 3: 实现** — `backend/routes/games.py` 顶部加 `COLLECTION_PREFIX = "古谱 · "`；`list_games` 增加：

```python
    scope = request.args.get("scope")
    if scope == "collection":
        collection = request.args.get("collection")
        if not collection:
            return _error("scope=collection 需要 collection 参数")
        query = query.filter(Game.category == f"{COLLECTION_PREFIX}{collection}")
    elif scope == "tournament":
        query = query.filter(
            db.or_(Game.category.is_(None), ~Game.category.like(f"{COLLECTION_PREFIX}%")),
            Game.event.is_not(None),
            Game.event != "",
            Game.event != "NA",
        )
    elif scope == "other":
        query = query.filter(
            db.or_(Game.category.is_(None), ~Game.category.like(f"{COLLECTION_PREFIX}%")),
            db.or_(Game.event.is_(None), Game.event == "", Game.event == "NA"),
        )
    elif scope:
        return _error("scope 只能是 collection/tournament/other")

    sort = request.args.get("sort")
    if sort == "created_desc":
        order = (Game.created_at.desc(), Game.id.desc())
    elif sort:
        return _error("sort 只支持 created_desc")
    else:
        order = (Game.updated_at.desc(), Game.id.desc())
```

并把已有的 `query.order_by(Game.updated_at.desc(), Game.id.desc())` 改为 `query.order_by(*order)`。

新增端点：

```python
@games_bp.get("/collections")
def list_collections():
    page, error = _parse_positive_int(request.args.get("page"), 1, 1)
    if error:
        return _error(f"page {error}")
    page_size, error = _parse_positive_int(
        request.args.get("page_size"), DEFAULT_PAGE_SIZE, 1, MAX_PAGE_SIZE
    )
    if error:
        return _error(f"page_size {error}")

    name = db.func.replace(Game.category, COLLECTION_PREFIX, "").label("name")
    grouped = (
        db.session.query(name, db.func.count().label("count"))
        .filter(Game.category.like(f"{COLLECTION_PREFIX}%"))
        .group_by(name)
        .subquery()
    )
    total = db.session.query(db.func.count()).select_from(grouped).scalar()
    rows = (
        db.session.query(grouped.c.name, grouped.c.count)
        .order_by(grouped.c.count.desc(), grouped.c.name.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return jsonify(
        {
            "items": [{"name": n, "count": c} for n, c in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )
```

**Step 4: 运行确认通过** — 同 Step 2。

---

### Task 2: 前端 api

**Files:** Modify `frontend/src/api/index.js`

在 `api` 对象加：

```js
  listCollections: (params) => http.get("/games/collections", { params }).then((r) => r.data),
```

`listGames` 已透传 params，无需改。

---

### Task 3: MobilePager

**Files:**
- Create: `frontend/src/mobile/components/MobilePager.vue`
- Test: `frontend/src/mobile/components/__tests__/MobilePager.test.js`

**组件实现：**

```vue
<script setup>
import { ref, watch } from "vue";

const props = defineProps({
  page: { type: Number, required: true },
  pageSize: { type: Number, default: 20 },
  total: { type: Number, required: true },
});
const emit = defineEmits(["change"]);
const input = ref(String(props.page));
watch(
  () => props.page,
  (value) => {
    input.value = String(value);
  }
);
const totalPages = () => Math.max(1, Math.ceil(props.total / props.pageSize));

function jump() {
  const value = Number(input.value);
  if (!Number.isInteger(value)) {
    input.value = String(props.page);
    return;
  }
  const target = Math.min(Math.max(value, 1), totalPages());
  input.value = String(target);
  if (target !== props.page) emit("change", target);
}
</script>

<template>
  <div class="pager">
    <button
      type="button"
      class="pager-btn"
      data-test="pager-prev"
      :disabled="page <= 1"
      @click="emit('change', page - 1)"
    >
      上一页
    </button>
    <div class="pager-jump">
      <input
        v-model="input"
        class="pager-input"
        data-test="pager-input"
        inputmode="numeric"
        @keyup.enter="jump"
      />
      <span class="pager-total">/ {{ totalPages() }}</span>
      <button type="button" class="pager-go" data-test="pager-go" @click="jump">跳转</button>
    </div>
    <button
      type="button"
      class="pager-btn"
      data-test="pager-next"
      :disabled="page >= totalPages()"
      @click="emit('change', page + 1)"
    >
      下一页
    </button>
  </div>
</template>

<style scoped>
.pager {
  display: flex;
  align-items: center;
  gap: 8px;
}

.pager-btn {
  flex: 0 0 auto;
  min-height: 40px;
  padding: 0 12px;
  border: 1px solid #cbb89a;
  border-radius: 6px;
  background: #fff;
  color: #7a3b2e;
  cursor: pointer;
}

.pager-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.pager-jump {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}

.pager-input {
  width: 56px;
  min-height: 40px;
  text-align: center;
  border: 1px solid #cbb89a;
  border-radius: 6px;
  font: inherit;
}

.pager-total {
  color: #6b5a45;
  font-size: 13px;
}

.pager-go {
  min-height: 40px;
  padding: 0 10px;
  border: 1px solid #cbb89a;
  border-radius: 6px;
  background: #fff;
  color: #7a3b2e;
  cursor: pointer;
}
</style>
```

**测试要点**：第 1 页「上一页」禁用、末页「下一页」禁用；点下一页 emit `change` 2；输入 5 点跳转 emit 5；输入超范围钳制到末页；非数字输入还原。

---

### Task 4: MobileGamePicker 分类浏览

**Files:**
- Modify: `frontend/src/mobile/components/MobileGamePicker.vue`
- Test: `frontend/src/mobile/components/__tests__/MobileGamePicker.test.js`

**组件实现：**

```vue
<script setup>
import { ref, watch } from "vue";
import { api } from "../../api";
import MobilePager from "./MobilePager.vue";

const emit = defineEmits(["select", "cancel"]);
const PAGE_SIZE = 20;

const view = ref("menu");
const scope = ref("tournament");
const collection = ref("");
const page = ref(1);
const total = ref(0);
const items = ref([]);
const loading = ref(false);
const error = ref(false);

async function load() {
  loading.value = true;
  error.value = false;
  try {
    if (view.value === "collections") {
      const data = await api.listCollections({ page: page.value, page_size: PAGE_SIZE });
      items.value = data.items || [];
      total.value = data.total || 0;
    } else if (view.value === "games") {
      const data = await api.listGames({
        scope: scope.value,
        collection: collection.value || undefined,
        sort: "created_desc",
        page: page.value,
        page_size: PAGE_SIZE,
      });
      items.value = data.items || [];
      total.value = data.total || 0;
    }
  } catch {
    error.value = true;
  } finally {
    loading.value = false;
  }
}

watch([view, page], () => {
  if (view.value !== "menu") load();
});

function openCategory(name) {
  if (name === "collection") {
    scope.value = "collection";
    collection.value = "";
    view.value = "collections";
    page.value = 1;
  } else {
    scope.value = name;
    collection.value = "";
    view.value = "games";
    page.value = 1;
  }
}

function openCollection(name) {
  scope.value = "collection";
  collection.value = name;
  view.value = "games";
  page.value = 1;
}

function back() {
  if (view.value === "games" && scope.value === "collection") {
    view.value = "collections";
  } else {
    view.value = "menu";
  }
  page.value = 1;
}

const title = () => {
  if (view.value === "collections") return "棋谱集";
  if (view.value === "games") {
    if (scope.value === "collection") return collection.value;
    return scope.value === "tournament" ? "赛事" : "其它";
  }
  return "打开棋谱";
};
</script>

<template>
  <div class="picker-mask" data-test="picker-mask" @click.self="emit('cancel')">
    <div class="picker-card" data-test="picker-card">
      <div class="picker-head">
        <button
          v-if="view !== 'menu'"
          type="button"
          class="picker-back"
          data-test="picker-back"
          @click="back"
        >
          返回
        </button>
        <h3 class="picker-title">{{ title() }}</h3>
      </div>

      <div v-if="view === 'menu'" class="picker-menu">
        <button type="button" data-test="menu-collection" @click="openCategory('collection')">
          棋谱
        </button>
        <button type="button" data-test="menu-tournament" @click="openCategory('tournament')">
          赛事
        </button>
        <button type="button" data-test="menu-other" @click="openCategory('other')">
          其它
        </button>
      </div>

      <template v-else>
        <p v-if="loading" class="picker-hint">加载中…</p>
        <p v-else-if="error" class="picker-hint">
          加载失败
          <button type="button" data-test="picker-retry" @click="load">重试</button>
        </p>
        <p v-else-if="items.length === 0" class="picker-hint" data-test="picker-empty">
          暂无棋谱
        </p>
        <ul v-else class="picker-list">
          <li v-if="view === 'collections'" v-for="item in items" :key="item.name">
            <button
              type="button"
              class="picker-item"
              :data-collection="item.name"
              @click="openCollection(item.name)"
            >
              <span class="picker-name">{{ item.name }}</span>
              <span class="picker-sub">{{ item.count }} 局</span>
            </button>
          </li>
          <li v-else v-for="game in items" :key="game.id">
            <button
              type="button"
              class="picker-item"
              :data-game="game.id"
              @click="emit('select', game)"
            >
              <span class="picker-name">{{ game.name }}</span>
              <span class="picker-sub">
                {{ game.red_player || "红方" }} vs {{ game.black_player || "黑方" }}
              </span>
            </button>
          </li>
        </ul>
      </template>

      <MobilePager
        v-if="view !== 'menu'"
        :page="page"
        :page-size="PAGE_SIZE"
        :total="total"
        @change="page = $event"
      />
      <div class="picker-actions">
        <button type="button" data-test="picker-cancel" @click="emit('cancel')">取消</button>
      </div>
    </div>
  </div>
</template>
```

（样式沿用原 picker 样式，追加 `.picker-head`、`.picker-back`、`.picker-menu`（竖排居中按钮，`min-height:56px`）、`.picker-list` 的 `flex:1; overflow-y:auto`，并把分页条固定在卡片底部视觉区。）

**测试要点**（mock `../../../api` 的 `listGames`/`listCollections`）：

- 初始渲染 `[data-test='menu-collection']` 等 3 个菜单按钮。
- 点「棋谱」→ 调 `listCollections`，渲染 `[data-collection='桔中秘']`。
- 点集名 → 调 `listGames` 且 `scope='collection'`、`collection='桔中秘'`，渲染 `[data-game]`，点击 emit `select`。
- 点「赛事」→ `listGames` 且 `scope='tournament'`，渲染棋谱。
- 点「其它」→ `listGames` 且 `scope='other'`。
- 点「下一页」→ `listGames`/`listCollections` 收到 `page=2`。
- 「返回」：集内 → 集列表 → 菜单。

---

### Task 5: MobileHomeView 测试更新

**Files:** Modify `frontend/src/mobile/views/__tests__/MobileHomeView.test.js`

「选中棋谱后可前进打谱」「打谱中应用编辑后退出打谱」两个用例：打开选择器后先点 `[data-test='menu-tournament']` 再点 `[data-game='1']`。

---

### Task 6: 全量回归

- `cd backend && .venv/bin/python -m pytest -q`
- `cd frontend && npm test && npm run build`
