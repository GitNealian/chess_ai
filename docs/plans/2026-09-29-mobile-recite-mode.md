# 移动端背谱模式 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在移动端首页棋盘上原地新增背谱模式，支持从棋谱或复习队列进入，凭记忆走子、看答案、并统一提交 SRS。

**Architecture:** 复用后端已有 `check-move` / `review/queue` / `review/submit` 接口，后端零改动。前端在 `MobileHomeView` 增加 `reciteMode` 状态机，扩展 `BoardControls` 支持背谱按钮组，新增 `MobileReviewQueue` 弹窗，顶栏新增复习入口。

**Tech Stack:** Vue 3 `<script setup>`、Pinia、axios、Vitest + @vue/test-utils、Vite。

**设计文档:** `docs/plans/2026-09-29-mobile-recite-mode-design.md`

---

## 约定

- 所有前端命令在 `frontend/` 目录执行。
- 每个任务完成后提交一次。
- 不新增代码注释，遵循项目现有风格。

---

## Task 1: BoardControls 支持背谱模式

**Files:**
- Modify: `frontend/src/mobile/components/BoardControls.vue`
- Test: `frontend/src/mobile/components/__tests__/BoardControls.test.js`

**Step 1: 写失败测试**

在 `BoardControls.test.js` 的 `describe` 内追加：

```js
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

  it("mode 为 recite 时只渲染翻转/看答案/退出背谱", async () => {
    const wrapper = mount(BoardControls, { props: { mode: "recite" } });
    const buttons = wrapper.findAll("button");
    expect(buttons.map((b) => b.text())).toEqual(["翻转", "看答案", "退出背谱"]);
    await wrapper.find("[data-test='ctrl-reveal']").trigger("click");
    await wrapper.find("[data-test='ctrl-exit-recite']").trigger("click");
    expect(wrapper.emitted("reveal")).toHaveLength(1);
    expect(wrapper.emitted("exit-recite")).toHaveLength(1);
  });
```

**Step 2: 运行测试确认失败**

Run: `npx vitest run src/mobile/components/__tests__/BoardControls.test.js`
Expected: 新增用例 FAIL（`ctrl-recite` 不存在）

**Step 3: 实现**

将 `BoardControls.vue` 的 `<template>` 与 `<script setup>` 替换为：

```vue
<template>
  <div class="board-controls">
    <template v-if="mode === 'recite'">
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
</template>

<script setup>
defineProps({
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
  "recite",
  "reveal",
  "exit-recite",
]);
</script>
```

注意：`<style scoped>` 保持不变。

**Step 4: 运行测试确认通过**

Run: `npx vitest run src/mobile/components/__tests__/BoardControls.test.js`
Expected: 全部 PASS

**Step 5: 提交**

```bash
git add frontend/src/mobile/components/BoardControls.vue frontend/src/mobile/components/__tests__/BoardControls.test.js
git commit -m "feat(mobile): BoardControls 支持背谱模式按钮组"
```

---

## Task 2: 新增复习队列弹窗 MobileReviewQueue

**Files:**
- Create: `frontend/src/mobile/components/MobileReviewQueue.vue`
- Test: `frontend/src/mobile/components/__tests__/MobileReviewQueue.test.js`

**Step 1: 写失败测试**

创建 `MobileReviewQueue.test.js`：

```js
import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";

vi.mock("../../../api", () => ({
  api: { reviewQueue: vi.fn() },
}));

import { api } from "../../../api";
import MobileReviewQueue from "../MobileReviewQueue.vue";

describe("MobileReviewQueue", () => {
  beforeEach(() => {
    api.reviewQueue.mockReset();
  });

  it("加载并渲染队列条目", async () => {
    api.reviewQueue.mockResolvedValue({
      items: [
        {
          game: { id: 7, name: "桔中秘第一局", red_player: "红甲", black_player: "黑乙" },
          due_date: "2026-09-29",
          is_new: false,
        },
      ],
      count: 1,
    });
    const wrapper = mount(MobileReviewQueue);
    await flushPromises();
    expect(api.reviewQueue).toHaveBeenCalledTimes(1);
    const item = wrapper.find("[data-game='7']");
    expect(item.exists()).toBe(true);
    expect(item.text()).toContain("桔中秘第一局");
  });

  it("空队列显示空态", async () => {
    api.reviewQueue.mockResolvedValue({ items: [], count: 0 });
    const wrapper = mount(MobileReviewQueue);
    await flushPromises();
    expect(wrapper.find("[data-test='queue-empty']").exists()).toBe(true);
  });

  it("点选条目发出 select", async () => {
    api.reviewQueue.mockResolvedValue({
      items: [
        {
          game: { id: 3, name: "测试局", red_player: "", black_player: "" },
          due_date: "2026-09-29",
          is_new: true,
        },
      ],
      count: 1,
    });
    const wrapper = mount(MobileReviewQueue);
    await flushPromises();
    await wrapper.find("[data-game='3']").trigger("click");
    expect(wrapper.emitted("select")[0][0]).toMatchObject({ id: 3 });
  });

  it("点关闭发出 cancel", async () => {
    api.reviewQueue.mockResolvedValue({ items: [], count: 0 });
    const wrapper = mount(MobileReviewQueue);
    await flushPromises();
    await wrapper.find("[data-test='queue-cancel']").trigger("click");
    expect(wrapper.emitted("cancel")).toHaveLength(1);
  });
});
```

**Step 2: 运行测试确认失败**

Run: `npx vitest run src/mobile/components/__tests__/MobileReviewQueue.test.js`
Expected: FAIL（模块不存在）

**Step 3: 实现**

创建 `MobileReviewQueue.vue`：

```vue
<script setup>
import { onMounted, ref } from "vue";
import { api } from "../../api";

const emit = defineEmits(["select", "cancel"]);
const items = ref([]);
const loading = ref(true);
const error = ref(false);

async function load() {
  loading.value = true;
  error.value = false;
  try {
    const data = await api.reviewQueue();
    items.value = data.items || [];
  } catch {
    error.value = true;
  } finally {
    loading.value = false;
  }
}

onMounted(load);

function players(game) {
  const red = game.red_player || "红方";
  const black = game.black_player || "黑方";
  return `${red} vs ${black}`;
}

function meta(entry) {
  return entry.is_new ? "新" : `到期 ${entry.due_date}`;
}
</script>

<template>
  <div class="queue-mask" data-test="queue-mask" @click.self="emit('cancel')">
    <div class="queue-card" data-test="queue-card">
      <h3 class="queue-title">复习背谱</h3>
      <p v-if="loading" class="queue-hint">加载中…</p>
      <p v-else-if="error" class="queue-hint" data-test="queue-error">
        加载失败
        <button type="button" data-test="queue-retry" @click="load">重试</button>
      </p>
      <p v-else-if="items.length === 0" class="queue-hint" data-test="queue-empty">
        暂无待复习棋谱
      </p>
      <ul v-else class="queue-list">
        <li v-for="entry in items" :key="entry.game.id">
          <button
            type="button"
            class="queue-item"
            :data-game="entry.game.id"
            @click="emit('select', entry.game)"
          >
            <span class="queue-name">{{ entry.game.name }}</span>
            <span class="queue-sub">{{ players(entry.game) }} · {{ meta(entry) }}</span>
          </button>
        </li>
      </ul>
      <div class="queue-actions">
        <button type="button" data-test="queue-cancel" @click="emit('cancel')">关闭</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.queue-mask {
  position: fixed;
  inset: 0;
  z-index: 200;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding: 16px;
  overflow-y: auto;
}

.queue-card {
  width: 100%;
  max-width: 420px;
  height: min(520px, calc(100vh - 32px));
  margin: auto;
  background: #faf6ee;
  border-radius: 12px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.queue-title {
  margin: 0;
}

.queue-hint {
  margin: 0;
  color: #6b5a45;
}

.queue-list {
  list-style: none;
  margin: 0;
  padding: 0;
  flex: 1;
  min-height: 120px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.queue-item {
  width: 100%;
  min-height: 52px;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  padding: 8px 12px;
  border: 1px solid #cbb89a;
  border-radius: 8px;
  background: #fff;
  cursor: pointer;
  text-align: left;
}

.queue-name {
  color: #7a3b2e;
  font-size: 16px;
}

.queue-sub {
  color: #8a7a63;
  font-size: 12px;
}

.queue-actions {
  display: flex;
}

.queue-actions button {
  flex: 1;
  min-height: 44px;
  border: 1px solid #cbb89a;
  border-radius: 6px;
  background: #fff;
  color: #7a3b2e;
  cursor: pointer;
}
</style>
```

**Step 4: 运行测试确认通过**

Run: `npx vitest run src/mobile/components/__tests__/MobileReviewQueue.test.js`
Expected: 全部 PASS

**Step 5: 提交**

```bash
git add frontend/src/mobile/components/MobileReviewQueue.vue frontend/src/mobile/components/__tests__/MobileReviewQueue.test.js
git commit -m "feat(mobile): 新增复习队列弹窗组件"
```

---

## Task 3: 顶栏新增复习入口

**Files:**
- Modify: `frontend/src/mobile/layouts/MobileLayout.vue`
- Test: `frontend/src/mobile/layouts/__tests__/MobileLayout.test.js`

**Step 1: 写失败测试**

在 `MobileLayout.test.js` 的 `describe` 内追加：

```js
  it("复习图标点击派发 mobile-review 事件", async () => {
    await router.push("/m");
    await router.isReady();
    const review = vi.fn();
    window.addEventListener("mobile-review", review);
    const wrapper = mount(MobileLayout, { global: { plugins: [router] } });
    await flushPromises();
    await wrapper.find("[data-test='header-review']").trigger("click");
    window.removeEventListener("mobile-review", review);
    expect(review).toHaveBeenCalledTimes(1);
  });
```

**Step 2: 运行测试确认失败**

Run: `npx vitest run src/mobile/layouts/__tests__/MobileLayout.test.js`
Expected: 新用例 FAIL（`header-review` 不存在）

**Step 3: 实现**

在 `MobileLayout.vue` 顶部 `<div class="mobile-topbar-actions">` 内、`header-open` 按钮之前插入：

```html
        <button
          type="button"
          class="topbar-icon"
          data-test="header-review"
          aria-label="复习背谱"
          title="复习背谱"
          @click="publish('mobile-review')"
        >
          <svg
            viewBox="0 0 24 24"
            width="22"
            height="22"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <path d="M3 12a9 9 0 1 0 3-6.7L3 8" />
            <path d="M3 3v5h5" />
          </svg>
        </button>
```

**Step 4: 运行测试确认通过**

Run: `npx vitest run src/mobile/layouts/__tests__/MobileLayout.test.js`
Expected: 全部 PASS

**Step 5: 提交**

```bash
git add frontend/src/mobile/layouts/MobileLayout.vue frontend/src/mobile/layouts/__tests__/MobileLayout.test.js
git commit -m "feat(mobile): 顶栏新增复习入口"
```

---

## Task 4: MobileHomeView 背谱入口与确认条

**Files:**
- Modify: `frontend/src/mobile/views/MobileHomeView.vue`
- Test: `frontend/src/mobile/views/__tests__/MobileHomeView.test.js`（新建）

**Step 1: 写失败测试**

创建 `MobileHomeView.test.js`（后续任务继续在此文件追加用例）：

```js
import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { INITIAL_FEN } from "../../../utils/chess";

vi.mock("../../../api", () => ({
  api: {
    checkMove: vi.fn(),
    submitReview: vi.fn(() => Promise.resolve({ quality: 5 })),
    reviewQueue: vi.fn(() => Promise.resolve({ items: [], count: 0 })),
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
        MobileReviewQueue: {
          name: "MobileReviewQueue",
          emits: ["select", "cancel"],
          template: '<div data-test="review-queue"></div>',
        },
      },
    },
  });
}

async function openGame(wrapper, game = GAME) {
  window.dispatchEvent(new CustomEvent("mobile-open"));
  await flushPromises();
  wrapper.findComponent({ name: "MobileGamePicker" }).vm.$emit("select", game);
  await flushPromises();
}

describe("MobileHomeView 背谱", () => {
  beforeEach(() => {
    api.checkMove.mockReset();
    api.submitReview.mockClear();
    api.openGame.mockClear();
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
});
```

**Step 2: 运行测试确认失败**

Run: `npx vitest run src/mobile/views/__tests__/MobileHomeView.test.js`
Expected: FAIL（无 `ctrl-recite` / `recite-confirm`）

**Step 3: 实现**

在 `MobileHomeView.vue` `<script setup>` 中新增状态：

```js
const reciteMode = ref(false);
const reciteConfirmOpen = ref(false);
```

在 `onOpenGame` 与 `onApply` 末尾增加重置：

```js
  reciteMode.value = false;
  reciteConfirmOpen.value = false;
```

新增计算属性与方法：

```js
const reciteMeta = computed(() => {
  const game = currentGame.value || {};
  const players = [game.red_player, game.black_player].filter(Boolean).join(" vs ");
  return [players, game.event, game.result, game.category].filter(Boolean).join(" · ");
});

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

其中 `reciteStartPly`、`reciteMistakes`、`reciteRevealed`、`reciteStartedAt` 也一并声明：

```js
const reciteStartPly = ref(0);
const reciteMistakes = ref(0);
const reciteRevealed = ref(false);
const reciteStartedAt = ref(0);
```

模板中把 `BoardControls` 改为：

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

在模板 `settings-mask` 之前插入确认条：

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

在 `<style scoped>` 末尾补充：

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
git commit -m "feat(mobile): 背谱入口与起点确认条"
```

---

## Task 5: 背谱走子校验与错误计数

**Files:**
- Modify: `frontend/src/mobile/views/MobileHomeView.vue`
- Test: `frontend/src/mobile/views/__tests__/MobileHomeView.test.js`

**Step 1: 写失败测试**

在 `MobileHomeView.test.js` 的 `describe` 内追加：

```js
  it("背谱走对推进一步", async () => {
    api.checkMove.mockResolvedValue({ correct: true, expected: GAME.moves[0] });
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
    api.checkMove.mockResolvedValue({ correct: false, expected: GAME.moves[0] });
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

  it("背谱走子网络失败提示校验失败不计错", async () => {
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

## Task 6: 看答案、完成提交与中途退出

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

  it("看答案标记 revealed 并推进", async () => {
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

在 `submitReciteMove` 的 `ply.value += 1;` 之后补完成判定：

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
    api.submitReview(game.id, {
      mistake_count: mistakeCount,
      duration_ms: duration,
      revealed,
    }).catch(() => {});
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

在模板 `BoardControls` 上补事件绑定：

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

## Task 7: 复习队列入口接入首页

**Files:**
- Modify: `frontend/src/mobile/views/MobileHomeView.vue`
- Test: `frontend/src/mobile/views/__tests__/MobileHomeView.test.js`

**Step 1: 写失败测试**

在 `MobileHomeView.test.js` 的 `describe` 内追加：

```js
  it("顶栏复习事件打开队列并选中棋谱进入浏览态", async () => {
    const wrapper = makeWrapper();
    window.dispatchEvent(new CustomEvent("mobile-review"));
    await flushPromises();
    const queue = wrapper.findComponent({ name: "MobileReviewQueue" });
    expect(queue.exists()).toBe(true);
    queue.vm.$emit("select", GAME);
    await flushPromises();
    expect(wrapper.find("[data-test='review-queue']").exists()).toBe(false);
    expect(wrapper.find("[data-test='ctrl-recite']").exists()).toBe(true);
  });
```

**Step 2: 运行测试确认失败**

Run: `npx vitest run src/mobile/views/__tests__/MobileHomeView.test.js`
Expected: 新用例 FAIL

**Step 3: 实现**

在 `import` 区加入：

```js
import MobileReviewQueue from "../components/MobileReviewQueue.vue";
```

新增状态与方法：

```js
const queueOpen = ref(false);

function onQueueSelect(game) {
  queueOpen.value = false;
  onOpenGame(game);
}
```

在模板中 `MobileGamePicker` 之后插入：

```html
    <MobileReviewQueue
      v-if="queueOpen"
      @select="onQueueSelect"
      @cancel="queueOpen = false"
    />
```

新增事件监听函数并注册：

```js
function onReviewEvent() {
  queueOpen.value = true;
}
```

在 `onMounted` 中加 `window.addEventListener("mobile-review", onReviewEvent);`，在 `onUnmounted` 中加 `window.removeEventListener("mobile-review", onReviewEvent);`。

顺带给 `MobileAnalysis` 加背谱隐藏：

```html
    <MobileAnalysis
      v-if="!reciteMode"
      :initial-fen="initialFen"
      :moves="moveSlice"
      :score="settings.score"
      :intent="settings.intent"
      @arrows="analysisArrows = $event"
    />
```

**Step 4: 运行测试确认通过**

Run: `npx vitest run src/mobile/views/__tests__/MobileHomeView.test.js`
Expected: 全部 PASS

**Step 5: 提交**

```bash
git add frontend/src/mobile/views/MobileHomeView.vue frontend/src/mobile/views/__tests__/MobileHomeView.test.js
git commit -m "feat(mobile): 复习队列入口接入首页"
```

---

## Task 8: 全量测试与构建

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

- [ ] 打开棋谱后出现「背谱」，点击弹确认条显示对手/赛事/结果/分类与步数范围
- [ ] 从头背或从当前步起背都能进入背谱态，翻页/编辑/扫描/推演/悔棋隐藏
- [ ] 双方都需自己走；走对推进，走错提示且不推进，错误数累计
- [ ] 看答案揭示并替走，完成后 `revealed=true` 提交
- [ ] 中途退出不写 SRS
- [ ] 顶栏复习入口列出到期/新棋谱，选中后进入浏览态可先看再背
- [ ] `npm test` 与 `npm run build` 均通过
