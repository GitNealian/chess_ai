# 移动端背谱模式 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在移动端首页棋盘上原地新增背谱模式，支持从打开棋谱弹窗的「复习」入口进入，凭记忆走子、看答案、按来源「上一盘/下一盘」切换，并统一提交 SRS。

**Architecture:** 复用后端已有 `check-move` / `review/queue` / `review/submit` / `games` 接口，后端零改动。前端扩展 `BoardControls`（单行横向滚动 + 导航/背谱按钮）、`MobileGamePicker`（复习入口 + 来源传递）、`MobileHomeView`（背谱状态机与来源导航），`api.reviewQueue` 支持参数。

**Tech Stack:** Vue 3 `<script setup>`、Pinia、axios、Vitest + @vue/test-utils、Vite。

**设计文档:** `docs/plans/2026-09-29-mobile-recite-mode-design.md`

---

## 约定

- 所有前端命令在 `frontend/` 目录执行。
- 每个任务完成后提交一次。
- 不新增代码注释，遵循项目现有风格。

---

## Task 1: BoardControls 单行横向滚动 + 导航与背谱按钮

**Files:**
- Modify: `frontend/src/mobile/components/BoardControls.vue`
- Test: `frontend/src/mobile/components/__tests__/BoardControls.test.js`

**Step 1: 写失败测试**

在 `BoardControls.test.js` 的 `describe` 内追加：

```js
  it("showNav 为 true 时渲染上一盘/下一盘并发出事件", async () => {
    const wrapper = mount(BoardControls, { props: { showNav: true } });
    const prev = wrapper.find("[data-test='ctrl-prev-game']");
    const next = wrapper.find("[data-test='ctrl-next-game']");
    expect(prev.exists()).toBe(true);
    expect(next.exists()).toBe(true);
    await prev.trigger("click");
    await next.trigger("click");
    expect(wrapper.emitted("prev-game")).toHaveLength(1);
    expect(wrapper.emitted("next-game")).toHaveLength(1);
  });

  it("showNav 缺省不渲染上一盘/下一盘", () => {
    const wrapper = mount(BoardControls);
    expect(wrapper.find("[data-test='ctrl-prev-game']").exists()).toBe(false);
    expect(wrapper.find("[data-test='ctrl-next-game']").exists()).toBe(false);
  });

  it("showRecite 为 true 时渲染背谱按钮并发出 recite", async () => {
    const wrapper = mount(BoardControls, { props: { showRecite: true } });
    const recite = wrapper.find("[data-test='ctrl-recite']");
    expect(recite.exists()).toBe(true);
    await recite.trigger("click");
    expect(wrapper.emitted("recite")).toHaveLength(1);
  });

  it("showRecite 缺省不渲染背谱按钮", () => {
    const wrapper = mount(BoardControls);
    expect(wrapper.find("[data-test='ctrl-recite']").exists()).toBe(false);
  });

  it("mode 为 recite 时只渲染导航与背谱操作按钮", async () => {
    const wrapper = mount(BoardControls, { props: { mode: "recite", showNav: true } });
    const buttons = wrapper.findAll(".board-controls__track button");
    expect(buttons.map((b) => b.text())).toEqual([
      "上一盘",
      "下一盘",
      "翻转",
      "看答案",
      "退出背谱",
    ]);
    await wrapper.find("[data-test='ctrl-reveal']").trigger("click");
    await wrapper.find("[data-test='ctrl-exit-recite']").trigger("click");
    expect(wrapper.emitted("reveal")).toHaveLength(1);
    expect(wrapper.emitted("exit-recite")).toHaveLength(1);
  });
```

同时把原有两条断言按钮数量的用例，改从 `.board-controls__track button` 查找：

```js
  it("渲染 7 个控制按钮", () => {
    const wrapper = mount(BoardControls);
    const buttons = wrapper.findAll(".board-controls__track button");
    expect(buttons).toHaveLength(7);
    expect(buttons.map((b) => b.text())).toEqual([
      "开局",
      "后退",
      "前进",
      "终局",
      "翻转",
      "编辑",
      "扫描",
    ]);
  });
```

**Step 2: 运行测试确认失败**

Run: `npx vitest run src/mobile/components/__tests__/BoardControls.test.js`
Expected: 新增用例 FAIL

**Step 3: 实现**

用以下内容替换 `BoardControls.vue` 的 `<template>`、`<script setup>`、`<style scoped>`：

```vue
<template>
  <div class="board-controls">
    <button
      v-if="canLeft"
      type="button"
      class="board-controls__arrow board-controls__arrow--left"
      data-test="ctrl-scroll-left"
      aria-label="向左滚动"
      @click="scrollBy(-1)"
    >
      ‹
    </button>
    <div ref="scroller" class="board-controls__scroller">
      <div class="board-controls__track">
        <template v-if="mode === 'recite'">
          <button
            v-if="showNav"
            type="button"
            data-test="ctrl-prev-game"
            @click="emit('prev-game')"
          >
            上一盘
          </button>
          <button
            v-if="showNav"
            type="button"
            data-test="ctrl-next-game"
            @click="emit('next-game')"
          >
            下一盘
          </button>
          <button
            type="button"
            data-test="ctrl-flip"
            :aria-pressed="flipped ? 'true' : 'false'"
            @click="emit('flip')"
          >
            翻转
          </button>
          <button type="button" data-test="ctrl-reveal" @click="emit('reveal')">看答案</button>
          <button type="button" data-test="ctrl-exit-recite" @click="emit('exit-recite')">
            退出背谱
          </button>
        </template>
        <template v-else>
          <button type="button" data-test="ctrl-start" :disabled="!canStart" @click="emit('start')">
            开局
          </button>
          <button type="button" data-test="ctrl-prev" :disabled="!canPrev" @click="emit('prev')">
            后退
          </button>
          <button type="button" data-test="ctrl-next" :disabled="!canNext" @click="emit('next')">
            前进
          </button>
          <button type="button" data-test="ctrl-end" :disabled="!canEnd" @click="emit('end')">
            终局
          </button>
          <button
            v-if="showNav"
            type="button"
            data-test="ctrl-prev-game"
            @click="emit('prev-game')"
          >
            上一盘
          </button>
          <button
            v-if="showNav"
            type="button"
            data-test="ctrl-next-game"
            @click="emit('next-game')"
          >
            下一盘
          </button>
          <button
            type="button"
            data-test="ctrl-flip"
            :aria-pressed="flipped ? 'true' : 'false'"
            @click="emit('flip')"
          >
            翻转
          </button>
          <button
            v-if="showUndo"
            type="button"
            data-test="ctrl-undo"
            :disabled="!canUndo"
            @click="emit('undo')"
          >
            悔棋
          </button>
          <button type="button" data-test="ctrl-edit" :disabled="!canEdit" @click="emit('edit')">
            编辑
          </button>
          <button type="button" data-test="ctrl-scan" :disabled="!canScan" @click="emit('scan')">
            扫描
          </button>
          <button
            v-if="showInfer"
            type="button"
            data-test="ctrl-infer"
            :disabled="!canInfer"
            @click="emit('infer')"
          >
            推演
          </button>
          <button
            v-if="showRecite"
            type="button"
            data-test="ctrl-recite"
            @click="emit('recite')"
          >
            背谱
          </button>
        </template>
      </div>
    </div>
    <button
      v-if="canRight"
      type="button"
      class="board-controls__arrow board-controls__arrow--right"
      data-test="ctrl-scroll-right"
      aria-label="向右滚动"
      @click="scrollBy(1)"
    >
      ›
    </button>
  </div>
</template>

<script setup>
import { nextTick, onMounted, onUnmounted, ref, watch } from "vue";

const props = defineProps({
  flipped: { type: Boolean, default: false },
  canStart: { type: Boolean, default: false },
  canPrev: { type: Boolean, default: false },
  canNext: { type: Boolean, default: false },
  canEnd: { type: Boolean, default: false },
  canEdit: { type: Boolean, default: false },
  canScan: { type: Boolean, default: false },
  showInfer: { type: Boolean, default: false },
  canInfer: { type: Boolean, default: false },
  showUndo: { type: Boolean, default: false },
  canUndo: { type: Boolean, default: false },
  mode: { type: String, default: "browse" },
  showNav: { type: Boolean, default: false },
  showRecite: { type: Boolean, default: false },
});

const emit = defineEmits([
  "start",
  "prev",
  "next",
  "end",
  "flip",
  "edit",
  "scan",
  "undo",
  "infer",
  "prev-game",
  "next-game",
  "recite",
  "reveal",
  "exit-recite",
]);

const scroller = ref(null);
const canLeft = ref(false);
const canRight = ref(false);
let resizeObserver = null;

function updateArrows() {
  const el = scroller.value;
  if (!el) return;
  canLeft.value = el.scrollLeft > 1;
  canRight.value = Math.ceil(el.scrollLeft + el.clientWidth) < el.scrollWidth - 1;
}

function scrollBy(direction) {
  const el = scroller.value;
  if (!el) return;
  el.scrollBy({ left: direction * Math.round(el.clientWidth * 0.8), behavior: "smooth" });
}

onMounted(() => {
  updateArrows();
  const el = scroller.value;
  el?.addEventListener("scroll", updateArrows, { passive: true });
  if (typeof ResizeObserver !== "undefined" && el) {
    resizeObserver = new ResizeObserver(updateArrows);
    resizeObserver.observe(el);
    const track = el.firstElementChild;
    if (track) resizeObserver.observe(track);
  }
});

onUnmounted(() => {
  scroller.value?.removeEventListener("scroll", updateArrows);
  resizeObserver?.disconnect();
});

watch(
  () => [props.mode, props.showNav, props.showRecite, props.showUndo, props.showInfer],
  () => nextTick(updateArrows)
);
</script>

<style scoped>
.board-controls {
  position: relative;
  display: flex;
  align-items: stretch;
}

.board-controls__scroller {
  flex: 1;
  min-width: 0;
  overflow-x: auto;
  scrollbar-width: none;
  -ms-overflow-style: none;
}

.board-controls__scroller::-webkit-scrollbar {
  display: none;
}

.board-controls__track {
  display: flex;
  gap: 8px;
  width: max-content;
  padding: 2px;
}

.board-controls__track button {
  flex: 0 0 auto;
  min-height: 44px;
  padding: 8px 14px;
  font-size: 14px;
  white-space: nowrap;
  color: #7a3b2e;
  background: #fff;
  border: 1px solid #cbb89a;
  border-radius: 6px;
  cursor: pointer;
}

.board-controls__track button:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.board-controls__track button[aria-pressed="true"] {
  background: #f4e3c1;
  border-color: #7a3b2e;
}

.board-controls__arrow {
  flex: 0 0 auto;
  width: 28px;
  padding: 0;
  border: none;
  background: rgba(250, 246, 238, 0.95);
  color: #7a3b2e;
  font-size: 22px;
  line-height: 1;
  cursor: pointer;
}

.board-controls__arrow--left {
  border-radius: 6px 0 0 6px;
}

.board-controls__arrow--right {
  border-radius: 0 6px 6px 0;
}
</style>
```

**Step 4: 运行测试确认通过**

Run: `npx vitest run src/mobile/components/__tests__/BoardControls.test.js`
Expected: 全部 PASS（jsdom 中 `clientWidth/scrollWidth` 为 0，箭头不渲染，不影响按钮计数）

**Step 5: 提交**

```bash
git add frontend/src/mobile/components/BoardControls.vue frontend/src/mobile/components/__tests__/BoardControls.test.js
git commit -m "refactor(mobile): 控制栏改为单行横向滚动并新增导航/背谱按钮"
```

---

## Task 2: MobileGamePicker 新增「复习」入口与来源传递

**Files:**
- Modify: `frontend/src/api/index.js`
- Modify: `frontend/src/mobile/components/MobileGamePicker.vue`
- Test: `frontend/src/mobile/components/__tests__/MobileGamePicker.test.js`

**Step 1: 写失败测试**

修改 `MobileGamePicker.test.js` 的 mock 与 beforeEach，加入 `reviewQueue`：

```js
vi.mock("../../../api", () => ({
  api: { listGames: vi.fn(), listCollections: vi.fn(), listEvents: vi.fn(), reviewQueue: vi.fn() },
}));
```

```js
  beforeEach(() => {
    api.listGames.mockReset();
    api.listCollections.mockReset();
    api.listEvents.mockReset();
    api.reviewQueue.mockReset();
  });
```

在 `describe` 内追加：

```js
  it("复习入口加载待复习棋谱并携带来源", async () => {
    api.reviewQueue.mockResolvedValue({
      items: [
        {
          game: { id: 5, name: "待复习局", red_player: "红甲", black_player: "黑乙" },
          due_date: "2026-09-29",
          is_new: false,
        },
      ],
      count: 1,
    });
    const wrapper = mount(MobileGamePicker);
    await wrapper.find("[data-test='menu-review']").trigger("click");
    await flushPromises();
    expect(api.reviewQueue).toHaveBeenCalledWith({ limit: 200 });
    expect(wrapper.find("[data-review='5']").exists()).toBe(true);
    await wrapper.find("[data-review='5']").trigger("click");
    expect(wrapper.emitted("select")[0][1]).toEqual({ type: "review" });
  });

  it("复习空队列显示空态", async () => {
    api.reviewQueue.mockResolvedValue({ items: [], count: 0 });
    const wrapper = mount(MobileGamePicker);
    await wrapper.find("[data-test='menu-review']").trigger("click");
    await flushPromises();
    expect(wrapper.find("[data-test='picker-empty']").exists()).toBe(true);
  });

  it("棋谱选择携带来源", async () => {
    api.listGames.mockResolvedValue({ items: [game(7, "开局")], total: 1 });
    const wrapper = mount(MobileGamePicker);
    await wrapper.find("[data-test='menu-other']").trigger("click");
    await flushPromises();
    await wrapper.find("[data-game='7']").trigger("click");
    expect(wrapper.emitted("select")[0][1]).toMatchObject({ type: "other" });
  });
```

**Step 2: 运行测试确认失败**

Run: `npx vitest run src/mobile/components/__tests__/MobileGamePicker.test.js`
Expected: 新增用例 FAIL

**Step 3: 实现**

`api/index.js` 修改 `reviewQueue`：

```js
  reviewQueue: (params) => http.get("/review/queue", { params }).then((r) => r.data),
```

`MobileGamePicker.vue` 的 `load()` 增加 `review` 分支：

```js
    } else if (view.value === "review") {
      const data = await api.reviewQueue({ limit: 200 });
      items.value = data.items || [];
      total.value = items.value.length;
    } else if (view.value === "games") {
```

`openCategory` 增加 `review` 分支：

```js
  } else if (name === "review") {
    scope.value = "review";
    view.value = "review";
  } else {
```

`title()` 增加：

```js
  if (view.value === "review") return "复习";
```

`back()` 保持不变（非 games 一律回 menu，已覆盖 review）。

新增方法（放在 `back` 之后）：

```js
function gamesSource() {
  return {
    type: scope.value,
    collection: collection.value || undefined,
    event: event.value || undefined,
  };
}

function selectGame(item) {
  emit("select", item, gamesSource());
}

function selectReview(entry) {
  emit("select", entry.game, { type: "review" });
}

function reviewMeta(entry) {
  return entry.is_new ? "新" : `到期 ${entry.due_date}`;
}
```

模板菜单中 `menu-tournament` 之后插入：

```html
        <button type="button" class="picker-menu-btn" data-test="menu-review" @click="openCategory('review')">
          复习
        </button>
```

模板列表 `events` 分支之后、`v-else`（games）之前插入 review 分支，并把 games 的 `emit('select', item)` 改为 `selectGame(item)`：

```html
          <template v-else-if="view === 'review'">
            <li v-for="entry in items" :key="entry.game.id">
              <button
                type="button"
                class="picker-item"
                :data-review="entry.game.id"
                @click="selectReview(entry)"
              >
                <span class="picker-name">{{ entry.game.name }}</span>
                <span class="picker-sub">
                  {{ entry.game.red_player || "红方" }} vs {{ entry.game.black_player || "黑方" }} ·
                  {{ reviewMeta(entry) }}
                </span>
              </button>
            </li>
          </template>
          <template v-else>
```

**Step 4: 运行测试确认通过**

Run: `npx vitest run src/mobile/components/__tests__/MobileGamePicker.test.js`
Expected: 全部 PASS

**Step 5: 提交**

```bash
git add frontend/src/api/index.js frontend/src/mobile/components/MobileGamePicker.vue frontend/src/mobile/components/__tests__/MobileGamePicker.test.js
git commit -m "feat(mobile): 打开棋谱弹窗新增复习入口并传递来源"
```

---

## Task 3: MobileHomeView 背谱入口、确认条与来源记录

**Files:**
- Modify: `frontend/src/mobile/views/MobileHomeView.vue`
- Test: `frontend/src/mobile/views/__tests__/MobileHomeView.test.js`（新建）

**Step 1: 写失败测试**

创建 `MobileHomeView.test.js`：

```js
import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { INITIAL_FEN } from "../../../utils/chess";

vi.mock("../../../api", () => ({
  api: {
    checkMove: vi.fn(),
    submitReview: vi.fn(() => Promise.resolve({ quality: 5 })),
    reviewQueue: vi.fn(() => Promise.resolve({ items: [], count: 0 })),
    listGames: vi.fn(() => Promise.resolve({ items: [], total: 0 })),
    openGame: vi.fn(() => Promise.resolve({ favorited: false })),
    favoriteGame: vi.fn(),
    bestMove: vi.fn(),
  },
}));

import { api } from "../../../api";
import MobileHomeView from "../MobileHomeView.vue";

const GAME = {
  id: 1,
  name: "测试谱",
  initial_fen: INITIAL_FEN,
  moves: [
    { x1: 0, y1: 3, x2: 0, y2: 4 },
    { x1: 0, y1: 6, x2: 0, y2: 5 },
  ],
  red_player: "红方甲",
  black_player: "黑方乙",
  event: "测试赛",
  result: "红胜",
  category: "古谱 · 测试",
  favorited: false,
};

function makeWrapper() {
  return mount(MobileHomeView, {
    global: {
      stubs: {
        ChessBoard: {
          name: "ChessBoard",
          props: ["position", "selected", "lastMove", "arrows", "flipped"],
          emits: ["cell-click"],
          template: '<div data-test="board"></div>',
        },
        MobileAnalysis: true,
        MobileBoardEditor: true,
        MobileScanDialog: true,
        MobileInferenceDialog: true,
        MobileGamePicker: {
          name: "MobileGamePicker",
          emits: ["select", "cancel"],
          template: '<div data-test="game-picker"></div>',
        },
      },
    },
  });
}

async function openGame(wrapper, game = GAME, source = { type: "collection", collection: "测试" }) {
  window.dispatchEvent(new CustomEvent("mobile-open"));
  await flushPromises();
  wrapper.findComponent({ name: "MobileGamePicker" }).vm.$emit("select", game, source);
  await flushPromises();
}

describe("MobileHomeView 背谱", () => {
  beforeEach(() => {
    api.checkMove.mockReset();
    api.submitReview.mockClear();
    api.openGame.mockClear();
    api.listGames.mockReset();
  });

  it("打开棋谱后显示背谱按钮，点击弹出确认条", async () => {
    const wrapper = makeWrapper();
    await openGame(wrapper);
    const recite = wrapper.find("[data-test='ctrl-recite']");
    expect(recite.exists()).toBe(true);
    await recite.trigger("click");
    expect(wrapper.find("[data-test='recite-confirm']").exists()).toBe(true);
    expect(wrapper.find("[data-test='recite-meta']").text()).toContain("红方甲");
    expect(wrapper.find("[data-test='recite-meta']").text()).toContain("测试赛");
  });

  it("取消确认条不进入背谱", async () => {
    const wrapper = makeWrapper();
    await openGame(wrapper);
    await wrapper.find("[data-test='ctrl-recite']").trigger("click");
    await wrapper.find("[data-test='recite-cancel']").trigger("click");
    expect(wrapper.find("[data-test='recite-confirm']").exists()).toBe(false);
    expect(wrapper.find("[data-test='ctrl-reveal']").exists()).toBe(false);
  });

  it("从头背进入背谱态，控制栏切换为背谱按钮组", async () => {
    const wrapper = makeWrapper();
    await openGame(wrapper);
    await wrapper.find("[data-test='ctrl-recite']").trigger("click");
    await wrapper.find("[data-test='recite-from-start']").trigger("click");
    expect(wrapper.find("[data-test='ctrl-reveal']").exists()).toBe(true);
    expect(wrapper.find("[data-test='ctrl-exit-recite']").exists()).toBe(true);
    expect(wrapper.find("[data-test='ctrl-start']").exists()).toBe(false);
  });

  it("翻到终局后背谱按钮不显示", async () => {
    const wrapper = makeWrapper();
    await openGame(wrapper);
    await wrapper.find("[data-test='ctrl-end']").trigger("click");
    expect(wrapper.find("[data-test='ctrl-recite']").exists()).toBe(false);
  });

  it("最近来源的有分类棋谱转换为棋谱集来源并显示导航", async () => {
    const wrapper = makeWrapper();
    await openGame(wrapper, GAME, { type: "recent" });
    expect(wrapper.find("[data-test='ctrl-next-game']").exists()).toBe(true);
  });

  it("最近来源的无分类棋谱不显示导航", async () => {
    const wrapper = makeWrapper();
    await openGame(wrapper, { ...GAME, category: "", event: "" }, { type: "recent" });
    expect(wrapper.find("[data-test='ctrl-next-game']").exists()).toBe(false);
  });
});
```

**Step 2: 运行测试确认失败**

Run: `npx vitest run src/mobile/views/__tests__/MobileHomeView.test.js`
Expected: FAIL

**Step 3: 实现**

`MobileHomeView.vue` `<script setup>` 新增状态：

```js
const reciteMode = ref(false);
const reciteConfirmOpen = ref(false);
const reciteStartPly = ref(0);
const reciteMistakes = ref(0);
const reciteRevealed = ref(false);
const reciteStartedAt = ref(0);
const navSource = ref(null);
const COLLECTION_PREFIX = "古谱 · ";
```

新增计算属性：

```js
const reciteMeta = computed(() => {
  const game = currentGame.value || {};
  const players = [game.red_player, game.black_player].filter(Boolean).join(" vs ");
  return [players, game.event, game.result, game.category].filter(Boolean).join(" · ");
});

const showNav = computed(() => !!currentGame.value && !!navSource.value);
```

新增方法：

```js
function normalizeSource(game, source) {
  if (!source) return null;
  if (source.type !== "recent") return source;
  if ((game.category || "").startsWith(COLLECTION_PREFIX)) {
    return { type: "collection", collection: game.category.slice(COLLECTION_PREFIX.length) };
  }
  if (game.event && game.event !== "NA") {
    return { type: "event", event: game.event };
  }
  return null;
}

function openReciteConfirm() {
  if (!currentGame.value || ply.value >= moves.value.length) return;
  reciteConfirmOpen.value = true;
}

function confirmRecite(fromStart) {
  reciteStartPly.value = fromStart ? 0 : ply.value;
  ply.value = reciteStartPly.value;
  reciteMistakes.value = 0;
  reciteRevealed.value = false;
  reciteStartedAt.value = Date.now();
  reciteMode.value = true;
  reciteConfirmOpen.value = false;
  selected.value = null;
  hint.value = "";
  moveToken += 1;
  engineToken += 1;
  engineThinking.value = false;
}
```

修改 `onOpenGame` 签名为 `function onOpenGame(game, source)`，把 `currentGame.value = game;` 之后改为同时记录来源，并在函数末尾重置背谱状态：

```js
function onOpenGame(game, source = null) {
  const fen = game.initial_fen || INITIAL_FEN;
  basePieces.value = fenToPieces(fen);
  initialFen.value = fen;
  moves.value = game.moves || [];
  ply.value = 0;
  pickerOpen.value = false;
  currentGame.value = game;
  favorited.value = !!game.favorited;
  navSource.value = normalizeSource(game, source);
  engineSide.value = "none";
  inferOpen.value = false;
  reciteMode.value = false;
  reciteConfirmOpen.value = false;
  engineToken += 1;
  moveToken += 1;
  engineThinking.value = false;
  selected.value = null;
  hint.value = "";
  api
    .openGame(game.id)
    .then((res) => {
      favorited.value = !!res.favorited;
      publishFavoriteState();
    })
    .catch(() => {});
}
```

`onApply` 中在 `currentGame.value = null;` 附近补 `navSource.value = null; reciteMode.value = false; reciteConfirmOpen.value = false;`。

模板 `BoardControls` 改为：

```html
    <BoardControls
      :mode="reciteMode ? 'recite' : 'browse'"
      :flipped="flipped"
      :can-start="canBack"
      :can-prev="canBack"
      :can-next="canForward"
      :can-end="canForward"
      :can-edit="true"
      :can-scan="true"
      :show-undo="!isReview || engineSide !== 'none'"
      :can-undo="(!isReview || engineSide !== 'none') && moves.length > 0"
      :show-infer="isReview && !reciteMode"
      :can-infer="isReview && !reciteMode"
      :show-nav="showNav"
      :show-recite="isReview && !reciteMode && moves.length > ply"
      @start="ply = 0"
      @prev="ply -= 1"
      @next="ply += 1"
      @end="ply = moves.length"
      @flip="flipped = !flipped"
      @edit="editorOpen = true"
      @scan="scanOpen = true"
      @undo="undo"
      @infer="inferOpen = true"
      @recite="openReciteConfirm"
    />
```

模板 `MobileAnalysis` 增加 `v-if="!reciteMode"`。

在模板 `settings-mask` 之前插入背谱确认条：

```html
    <div
      v-if="reciteConfirmOpen"
      class="settings-mask"
      data-test="recite-confirm"
      @click.self="reciteConfirmOpen = false"
    >
      <div class="settings-card">
        <h3 class="settings-title">{{ currentGame && currentGame.name }}</h3>
        <p class="recite-meta" data-test="recite-meta">{{ reciteMeta }}</p>
        <p class="recite-range" data-test="recite-range">
          将从第 {{ ply }} 步开始，背到第 {{ moves.length }} 步（共 {{ moves.length - ply }} 步）
        </p>
        <div class="settings-actions">
          <button
            v-if="ply > 0"
            type="button"
            data-test="recite-from-start"
            @click="confirmRecite(true)"
          >
            从头背
          </button>
          <button type="button" data-test="recite-from-here" @click="confirmRecite(false)">
            {{ ply > 0 ? `从第 ${ply} 步起背` : "开始背谱" }}
          </button>
          <button type="button" data-test="recite-cancel" @click="reciteConfirmOpen = false">
            取消
          </button>
        </div>
      </div>
    </div>
```

`<style scoped>` 末尾补充：

```css
.recite-meta {
  margin: 0;
  color: #6b5a45;
  font-size: 13px;
}

.recite-range {
  margin: 0;
  color: #7a3b2e;
}
```

**Step 4: 运行测试确认通过**

Run: `npx vitest run src/mobile/views/__tests__/MobileHomeView.test.js`
Expected: 全部 PASS

**Step 5: 提交**

```bash
git add frontend/src/mobile/views/MobileHomeView.vue frontend/src/mobile/views/__tests__/MobileHomeView.test.js
git commit -m "feat(mobile): 背谱入口、确认条与来源记录"
```

---

## Task 4: 背谱走子校验与错误计数

**Files:**
- Modify: `frontend/src/mobile/views/MobileHomeView.vue`
- Test: `frontend/src/mobile/views/__tests__/MobileHomeView.test.js`

**Step 1: 写失败测试**

在 `MobileHomeView.test.js` 的 `describe` 内追加：

```js
  it("背谱走对推进一步", async () => {
    api.checkMove.mockResolvedValue({ correct: true });
    const wrapper = makeWrapper();
    await openGame(wrapper);
    await wrapper.find("[data-test='ctrl-recite']").trigger("click");
    await wrapper.find("[data-test='recite-from-start']").trigger("click");
    const board = wrapper.findComponent({ name: "ChessBoard" });
    board.vm.$emit("cell-click", 0, 3);
    board.vm.$emit("cell-click", 0, 4);
    await flushPromises();
    expect(api.checkMove).toHaveBeenCalledWith(1, {
      ply: 0,
      move: { x1: 0, y1: 3, x2: 0, y2: 4 },
    });
    expect(wrapper.find("[data-test='ctrl-reveal']").exists()).toBe(true);
  });

  it("背谱走错不推进且提示错误", async () => {
    api.checkMove.mockResolvedValue({ correct: false });
    const wrapper = makeWrapper();
    await openGame(wrapper);
    await wrapper.find("[data-test='ctrl-recite']").trigger("click");
    await wrapper.find("[data-test='recite-from-start']").trigger("click");
    const board = wrapper.findComponent({ name: "ChessBoard" });
    board.vm.$emit("cell-click", 0, 3);
    board.vm.$emit("cell-click", 0, 5);
    await flushPromises();
    expect(wrapper.find("[data-test='hint']").text()).toContain("错误");
    expect(api.submitReview).not.toHaveBeenCalled();
  });

  it("背谱走子网络失败提示且不计错", async () => {
    api.checkMove.mockRejectedValue({ response: { data: { error: "校验失败" } } });
    const wrapper = makeWrapper();
    await openGame(wrapper);
    await wrapper.find("[data-test='ctrl-recite']").trigger("click");
    await wrapper.find("[data-test='recite-from-start']").trigger("click");
    const board = wrapper.findComponent({ name: "ChessBoard" });
    board.vm.$emit("cell-click", 0, 3);
    board.vm.$emit("cell-click", 0, 4);
    await flushPromises();
    expect(wrapper.find("[data-test='hint']").exists()).toBe(true);
    expect(api.submitReview).not.toHaveBeenCalled();
  });
```

**Step 2: 运行测试确认失败**

Run: `npx vitest run src/mobile/views/__tests__/MobileHomeView.test.js`
Expected: 新增用例 FAIL

**Step 3: 实现**

改造 `onCellClick`：

```js
function onCellClick(x, y) {
  if (isReview.value && !reciteMode.value) return;
  if (pending) return;
  if (!reciteMode.value) {
    if (engineSide.value !== "none" && ply.value !== moves.value.length) return;
    if (gameOver.value || engineThinking.value) return;
    if (isEngineTurn.value) {
      runEngineMove();
      return;
    }
  }
  const piece = pieces.value.find((p) => p.x === x && p.y === y);
  if (selected.value) {
    if (piece && piece.side === sideToMove.value) {
      const same = selected.value.x === x && selected.value.y === y;
      selected.value = same ? null : { x, y };
      return;
    }
    const move = { x1: selected.value.x, y1: selected.value.y, x2: x, y2: y };
    if (reciteMode.value) submitReciteMove(move);
    else submitMove(move);
    return;
  }
  if (piece && piece.side === sideToMove.value) selected.value = { x, y };
}
```

新增 `submitReciteMove`：

```js
async function submitReciteMove(move) {
  hint.value = "";
  pending = true;
  const token = ++moveToken;
  try {
    const data = await api.checkMove(currentGame.value.id, { ply: ply.value, move });
    if (token !== moveToken) return;
    if (!data.correct) {
      reciteMistakes.value += 1;
      hint.value = "着法错误，请重试";
      return;
    }
    ply.value += 1;
    selected.value = null;
  } catch (err) {
    if (token !== moveToken) return;
    hint.value =
      err?.response?.data?.error || err?.response?.data?.detail || "校验失败，请重试";
  } finally {
    if (token === moveToken) pending = false;
  }
}
```

**Step 4: 运行测试确认通过**

Run: `npx vitest run src/mobile/views/__tests__/MobileHomeView.test.js`
Expected: 全部 PASS

**Step 5: 提交**

```bash
git add frontend/src/mobile/views/MobileHomeView.vue frontend/src/mobile/views/__tests__/MobileHomeView.test.js
git commit -m "feat(mobile): 背谱走子校验与错误计数"
```

---

## Task 5: 看答案、完成提交与中途退出

**Files:**
- Modify: `frontend/src/mobile/views/MobileHomeView.vue`
- Test: `frontend/src/mobile/views/__tests__/MobileHomeView.test.js`

**Step 1: 写失败测试**

在 `MobileHomeView.test.js` 的 `describe` 内追加：

```js
  it("走完整条棋谱提交 SRS 且错误数为 0", async () => {
    api.checkMove.mockResolvedValue({ correct: true });
    const wrapper = makeWrapper();
    await openGame(wrapper);
    await wrapper.find("[data-test='ctrl-recite']").trigger("click");
    await wrapper.find("[data-test='recite-from-start']").trigger("click");
    const board = wrapper.findComponent({ name: "ChessBoard" });
    board.vm.$emit("cell-click", 0, 3);
    board.vm.$emit("cell-click", 0, 4);
    await flushPromises();
    board.vm.$emit("cell-click", 0, 6);
    board.vm.$emit("cell-click", 0, 5);
    await flushPromises();
    expect(api.submitReview).toHaveBeenCalledWith(1, {
      mistake_count: 0,
      duration_ms: expect.any(Number),
      revealed: false,
    });
    expect(wrapper.find("[data-test='ctrl-reveal']").exists()).toBe(false);
  });

  it("看答案标记 revealed 并推进至完成", async () => {
    const wrapper = makeWrapper();
    await openGame(wrapper);
    await wrapper.find("[data-test='ctrl-recite']").trigger("click");
    await wrapper.find("[data-test='recite-from-start']").trigger("click");
    await wrapper.find("[data-test='ctrl-reveal']").trigger("click");
    await flushPromises();
    await wrapper.find("[data-test='ctrl-reveal']").trigger("click");
    await flushPromises();
    expect(api.submitReview).toHaveBeenCalledWith(1, {
      mistake_count: 0,
      duration_ms: expect.any(Number),
      revealed: true,
    });
  });

  it("中途退出背谱不提交 SRS", async () => {
    const wrapper = makeWrapper();
    await openGame(wrapper);
    await wrapper.find("[data-test='ctrl-recite']").trigger("click");
    await wrapper.find("[data-test='recite-from-start']").trigger("click");
    await wrapper.find("[data-test='ctrl-exit-recite']").trigger("click");
    expect(api.submitReview).not.toHaveBeenCalled();
    expect(wrapper.find("[data-test='ctrl-reveal']").exists()).toBe(false);
    expect(wrapper.find("[data-test='ctrl-recite']").exists()).toBe(true);
  });
```

**Step 2: 运行测试确认失败**

Run: `npx vitest run src/mobile/views/__tests__/MobileHomeView.test.js`
Expected: 新增用例 FAIL

**Step 3: 实现**

`submitReciteMove` 推进后补完成判定：

```js
    ply.value += 1;
    selected.value = null;
    if (ply.value >= moves.value.length) finishRecite();
```

新增方法：

```js
function revealAnswer() {
  if (!reciteMode.value || ply.value >= moves.value.length) return;
  reciteRevealed.value = true;
  ply.value += 1;
  selected.value = null;
  hint.value = "已看答案";
  if (ply.value >= moves.value.length) finishRecite();
}

function finishRecite() {
  const game = currentGame.value;
  const duration = Math.max(0, Date.now() - reciteStartedAt.value);
  const mistakeCount = reciteMistakes.value;
  const revealed = reciteRevealed.value;
  reciteMode.value = false;
  hint.value = `背谱完成 · 错 ${mistakeCount} 次 · 用时 ${Math.round(duration / 1000)} 秒`;
  if (game) {
    api
      .submitReview(game.id, {
        mistake_count: mistakeCount,
        duration_ms: duration,
        revealed,
      })
      .catch(() => {});
  }
}

function exitRecite() {
  reciteMode.value = false;
  reciteMistakes.value = 0;
  reciteRevealed.value = false;
  selected.value = null;
  hint.value = "";
  moveToken += 1;
  pending = false;
}
```

`BoardControls` 增加事件绑定：

```html
      @reveal="revealAnswer"
      @exit-recite="exitRecite"
```

**Step 4: 运行测试确认通过**

Run: `npx vitest run src/mobile/views/__tests__/MobileHomeView.test.js`
Expected: 全部 PASS

**Step 5: 提交**

```bash
git add frontend/src/mobile/views/MobileHomeView.vue frontend/src/mobile/views/__tests__/MobileHomeView.test.js
git commit -m "feat(mobile): 看答案、完成提交 SRS 与中途退出"
```

---

## Task 6: 上一盘/下一盘导航与切换确认

**Files:**
- Modify: `frontend/src/mobile/views/MobileHomeView.vue`
- Test: `frontend/src/mobile/views/__tests__/MobileHomeView.test.js`

**Step 1: 写失败测试**

在 `MobileHomeView.test.js` 的 `describe` 内追加：

```js
  it("下一盘切换到来源列表的下一条", async () => {
    api.listGames.mockResolvedValue({
      items: [GAME, { ...GAME, id: 2, name: "第二谱" }],
      total: 2,
    });
    const wrapper = makeWrapper();
    await openGame(wrapper);
    await wrapper.find("[data-test='ctrl-next-game']").trigger("click");
    await flushPromises();
    expect(api.listGames).toHaveBeenCalledWith(
      expect.objectContaining({ scope: "collection", collection: "测试", page: 1 })
    );
    expect(api.openGame).toHaveBeenLastCalledWith(2);
  });

  it("已是最后一盘时提示", async () => {
    api.listGames.mockResolvedValue({ items: [GAME], total: 1 });
    const wrapper = makeWrapper();
    await openGame(wrapper);
    await wrapper.find("[data-test='ctrl-next-game']").trigger("click");
    await flushPromises();
    expect(wrapper.find("[data-test='hint']").text()).toContain("最后一盘");
  });

  it("背谱未完成时切换先弹确认，确认后不提交 SRS 并切换", async () => {
    api.listGames.mockResolvedValue({
      items: [GAME, { ...GAME, id: 2, name: "第二谱" }],
      total: 2,
    });
    const wrapper = makeWrapper();
    await openGame(wrapper);
    await wrapper.find("[data-test='ctrl-recite']").trigger("click");
    await wrapper.find("[data-test='recite-from-start']").trigger("click");
    await wrapper.find("[data-test='ctrl-next-game']").trigger("click");
    expect(wrapper.find("[data-test='nav-confirm']").exists()).toBe(true);
    await wrapper.find("[data-test='nav-confirm-ok']").trigger("click");
    await flushPromises();
    expect(api.submitReview).not.toHaveBeenCalled();
    expect(api.openGame).toHaveBeenLastCalledWith(2);
    expect(wrapper.find("[data-test='ctrl-reveal']").exists()).toBe(false);
  });
```

**Step 2: 运行测试确认失败**

Run: `npx vitest run src/mobile/views/__tests__/MobileHomeView.test.js`
Expected: 新增用例 FAIL

**Step 3: 实现**

新增状态：

```js
const navConfirmOpen = ref(false);
const navDirection = ref(1);
```

新增方法：

```js
async function collectSourceGames(source) {
  if (source.type === "review") {
    const data = await api.reviewQueue({ limit: 200 });
    return (data.items || []).map((entry) => entry.game);
  }
  const pageSize = 100;
  const all = [];
  let page = 1;
  for (;;) {
    const data = await api.listGames({
      scope: source.type,
      collection: source.collection || undefined,
      event: source.event || undefined,
      sort: "created_desc",
      page,
      page_size: pageSize,
    });
    const items = data.items || [];
    all.push(...items);
    if (!items.length || all.length >= (data.total || 0) || page >= 20) break;
    page += 1;
  }
  return all;
}

function requestNav(direction) {
  if (reciteMode.value) {
    navDirection.value = direction;
    navConfirmOpen.value = true;
    return;
  }
  runNav(direction);
}

async function confirmNav() {
  navConfirmOpen.value = false;
  exitRecite();
  await runNav(navDirection.value);
}

async function runNav(direction) {
  const source = navSource.value;
  if (!source || !currentGame.value) return;
  hint.value = "";
  try {
    const games = await collectSourceGames(source);
    const index = games.findIndex((item) => item.id === currentGame.value.id);
    const target = index === -1 ? null : games[index + direction];
    if (!target) {
      hint.value = direction < 0 ? "已是第一盘" : "已是最后一盘";
      return;
    }
    onOpenGame(target, source);
  } catch {
    hint.value = "切换失败，请重试";
  }
}
```

`BoardControls` 增加事件绑定：

```html
      @prev-game="requestNav(-1)"
      @next-game="requestNav(1)"
```

在模板背谱确认条之后插入切换确认框：

```html
    <div
      v-if="navConfirmOpen"
      class="settings-mask"
      data-test="nav-confirm"
      @click.self="navConfirmOpen = false"
    >
      <div class="settings-card">
        <h3 class="settings-title">放弃当前背谱？</h3>
        <p class="recite-meta">当前背谱尚未完成，切换将放弃本次进度且不记录。</p>
        <div class="settings-actions">
          <button type="button" data-test="nav-confirm-cancel" @click="navConfirmOpen = false">
            继续背谱
          </button>
          <button type="button" data-test="nav-confirm-ok" @click="confirmNav">
            放弃并切换
          </button>
        </div>
      </div>
    </div>
```

**Step 4: 运行测试确认通过**

Run: `npx vitest run src/mobile/views/__tests__/MobileHomeView.test.js`
Expected: 全部 PASS

**Step 5: 提交**

```bash
git add frontend/src/mobile/views/MobileHomeView.vue frontend/src/mobile/views/__tests__/MobileHomeView.test.js
git commit -m "feat(mobile): 上一盘/下一盘导航与切换确认"
```

---

## Task 7: 全量测试与构建

**Files:**
- Build: `frontend/dist/`

**Step 1: 前端测试全量通过**

Run: `npm test`
Expected: 全部 PASS

**Step 2: 构建产物**

Run: `npm run build`
Expected: 构建成功，`frontend/dist/` 更新

**Step 3: 提交构建产物（若 dist 被跟踪）**

```bash
git status --short frontend/dist
git add frontend/dist
git commit -m "chore(mobile): 构建背谱模式产物"
```

（若 `frontend/dist` 未被 git 跟踪，跳过提交，仅确认构建成功。）

---

## 验证清单

- [ ] 打开棋谱弹窗菜单有「复习」，点入列出待复习棋谱，空态正常
- [ ] 打开棋谱后出现「背谱」，确认条显示对手/赛事/结果/分类与步数范围
- [ ] 从头背或从当前步起背都能进入背谱态；背谱态只显示导航与背谱操作
- [ ] 双方都需自己走；走对推进，走错提示且不推进，错误数累计
- [ ] 看答案揭示并替走，完成后 `revealed=true` 提交
- [ ] 中途退出或切换棋谱不写 SRS
- [ ] 上一盘/下一盘按来源切换，边界提示正确
- [ ] 背谱未完成时切换弹出确认，确认后放弃且不记录
- [ ] 最近来源按所属棋谱集/赛事切换，两者都无则不显示导航
- [ ] 控制栏单行横向滚动，两端箭头按可滚动方向显隐
- [ ] `npm test` 与 `npm run build` 均通过
