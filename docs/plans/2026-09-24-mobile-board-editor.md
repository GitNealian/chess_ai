# 移动端棋盘编辑器 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在移动端首页点「编辑」弹出摆子窗口，支持选中/移动/删除/放置棋子，确认经后端校验后更新首页棋盘。

**Architecture:** 新增纯移动端组件 `MobilePieceChooser.vue`（候选区）与 `MobileBoardEditor.vue`（弹窗），复用 `ChessBoard.vue` 与 `api.validatePosition`；首页持有 `pieces` 状态并接线。测试用 Vitest + Vue Test Utils。

**Tech Stack:** Vue 3 `<script setup>`、Vue Test Utils、Vitest。

**设计文档:** `docs/plans/2026-09-24-mobile-board-editor-design.md`

---

### Task 1: 新增棋子数量上限常量

**Files:**
- Modify: `frontend/src/utils/chess.js`
- Test: `frontend/src/utils/__tests__/chess.test.js`

**Step 1: 写失败测试**

在 `frontend/src/utils/__tests__/chess.test.js` 顶部 import 增加 `MAX_COUNTS`，并追加：

```js
describe("MAX_COUNTS", () => {
  it("按象棋规则给出各兵种上限", () => {
    expect(MAX_COUNTS).toEqual({ K: 1, A: 2, B: 2, N: 2, R: 2, C: 2, P: 5 });
  });
});
```

**Step 2: 运行确认失败** — `npm test -- src/utils/__tests__/chess.test.js`（workdir `frontend`），期望 `MAX_COUNTS` 未导出。

**Step 3: 实现**

在 `frontend/src/utils/chess.js` 的 `LABELS` 后追加：

```js
export const MAX_COUNTS = { K: 1, A: 2, B: 2, N: 2, R: 2, C: 2, P: 5 };
```

**Step 4: 运行确认通过** — 同上命令。

---

### Task 2: MobilePieceChooser 候选区组件

**Files:**
- Create: `frontend/src/mobile/components/MobilePieceChooser.vue`
- Test: `frontend/src/mobile/components/__tests__/MobilePieceChooser.test.js`

**组件实现：**

```vue
<script setup>
import { LABELS, MAX_COUNTS } from "../../utils/chess";

const props = defineProps({
  pieces: { type: Array, default: () => [] },
  selected: { type: Object, default: null },
});
const emit = defineEmits(["select"]);

const KINDS = ["K", "A", "B", "N", "R", "C", "P"];
const ROWS = [
  { side: "black", name: "黑方" },
  { side: "red", name: "红方" },
];

const countOf = (side, kind) =>
  props.pieces.filter((p) => p.side === side && p.kind === kind).length;
const isDisabled = (side, kind) => countOf(side, kind) >= MAX_COUNTS[kind];
const isActive = (side, kind) =>
  !!props.selected && props.selected.side === side && props.selected.kind === kind;
const label = (side, kind) => LABELS[`${side}-${kind}`];
</script>

<template>
  <div class="chooser">
    <div v-for="row in ROWS" :key="row.side" class="chooser-row" :data-row="row.side">
      <button
        v-for="kind in KINDS"
        :key="kind"
        type="button"
        :data-piece="`${row.side}-${kind}`"
        class="chooser-btn"
        :class="{ active: isActive(row.side, kind), red: row.side === 'red' }"
        :disabled="isDisabled(row.side, kind)"
        @click="emit('select', { side: row.side, kind })"
      >
        {{ label(row.side, kind) }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.chooser {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.chooser-row {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 6px;
}

.chooser-btn {
  aspect-ratio: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid #cbb89a;
  border-radius: 50%;
  background: #fff4e0;
  color: #1a1a1a;
  font-size: 18px;
  cursor: pointer;
}

.chooser-btn.red {
  color: #b32020;
}

.chooser-btn.active {
  border-color: #d4a017;
  box-shadow: 0 0 0 2px rgba(212, 160, 23, 0.5);
}

.chooser-btn:disabled {
  filter: grayscale(1);
  opacity: 0.35;
  cursor: not-allowed;
}
</style>
```

**测试要点**（`data-row="black"` 第一行、`data-row="red"` 第二行；每行 7 个）：

- 空盘面时全部可点；点击 `[data-piece='black-R']` emit `select` 且 payload `{ side:"black", kind:"R" }`。
- 盘面含 2 个黑车时 `[data-piece='black-R']` 带 `disabled`。
- 盘面含 1 个黑车时仍可点。
- `selected` 命中时该按钮含 `active` 类。
- 第一行 `[data-row='black']` 文本顺序为 `将 士 象 马 车 炮 卒`，第二行为 `帅 仕 相 马 车 炮 兵`。

---

### Task 3: MobileBoardEditor 弹窗编辑器

**Files:**
- Create: `frontend/src/mobile/components/MobileBoardEditor.vue`
- Test: `frontend/src/mobile/components/__tests__/MobileBoardEditor.test.js`

**组件实现：**

```vue
<script setup>
import { ref } from "vue";
import ChessBoard from "../../components/ChessBoard.vue";
import MobilePieceChooser from "./MobilePieceChooser.vue";
import { LABELS } from "../../utils/chess";
import { api } from "../../api";

const props = defineProps({ pieces: { type: Array, default: () => [] } });
const emit = defineEmits(["cancel", "apply"]);

const draft = ref(props.pieces.map((p) => ({ ...p })));
const selected = ref(null);
const palette = ref(null);
const editSide = ref("red");
const errors = ref([]);
const applying = ref(false);

function clearSelection() {
  selected.value = null;
  palette.value = null;
}

function clearBoard() {
  if (applying.value) return;
  draft.value = [];
  selected.value = null;
  palette.value = null;
}

function onChooserSelect(piece) {
  if (palette.value && palette.value.side === piece.side && palette.value.kind === piece.kind) {
    palette.value = null;
    return;
  }
  palette.value = piece;
  selected.value = null;
}

function onCellClick(x, y) {
  if (applying.value) return;
  const target = draft.value.find((p) => p.x === x && p.y === y);

  if (palette.value) {
    const { side, kind } = palette.value;
    draft.value = [
      ...draft.value.filter((p) => !(p.x === x && p.y === y)),
      { x, y, side, kind, label: LABELS[`${side}-${kind}`] },
    ];
    palette.value = null;
    return;
  }

  if (selected.value) {
    if (selected.value.x === x && selected.value.y === y) {
      draft.value = draft.value.filter((p) => !(p.x === x && p.y === y));
      selected.value = null;
      return;
    }
    const moving = draft.value.find(
      (p) => p.x === selected.value.x && p.y === selected.value.y
    );
    draft.value = [
      ...draft.value.filter(
        (p) =>
          !(p.x === x && p.y === y) &&
          !(p.x === selected.value.x && p.y === selected.value.y)
      ),
      { ...moving, x, y },
    ];
    selected.value = null;
    return;
  }

  if (target) selected.value = { x, y };
}

async function apply() {
  if (applying.value) return;
  applying.value = true;
  errors.value = [];
  try {
    const res = await api.validatePosition({
      pieces: draft.value.map(({ x, y, side, kind }) => ({ x, y, side, kind })),
      side_to_move: editSide.value,
    });
    if (!res.valid) {
      errors.value = res.errors || ["局面不合法"];
      return;
    }
    emit("apply", draft.value.map((p) => ({ ...p })));
  } catch (err) {
    errors.value = [
      err?.response?.data?.detail || err?.response?.data?.error || "校验失败，请重试",
    ];
  } finally {
    applying.value = false;
  }
}
</script>

<template>
  <div class="editor-mask" data-test="editor-mask" @click.self="clearSelection">
    <div class="editor-card" data-test="editor-card">
      <h3 class="editor-title">编辑局面</h3>
      <ChessBoard :position="{ pieces: draft }" :selected="selected" @cell-click="onCellClick" />
      <MobilePieceChooser :pieces="draft" :selected="palette" @select="onChooserSelect" />
      <div class="editor-foot">
        <div class="editor-side">
          <span>行棋方</span>
          <label>
            <input
              v-model="editSide"
              type="radio"
              value="red"
              data-test="editor-side-red"
              :disabled="applying"
            />
            红先
          </label>
          <label>
            <input
              v-model="editSide"
              type="radio"
              value="black"
              data-test="editor-side-black"
              :disabled="applying"
            />
            黑先
          </label>
        </div>
        <button
          type="button"
          class="editor-clear"
          data-test="editor-clear"
          :disabled="applying"
          @click="clearBoard"
        >
          清空棋盘
        </button>
      </div>
      <p v-for="(err, i) in errors" :key="i" class="editor-error" data-test="editor-error">
        {{ err }}
      </p>
      <div class="editor-actions">
        <button type="button" data-test="editor-cancel" :disabled="applying" @click="emit('cancel')">
          取消
        </button>
        <button type="button" data-test="editor-apply" :disabled="applying" @click="apply">
          {{ applying ? "校验中…" : "确认" }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.editor-mask {
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

.editor-card {
  width: 100%;
  max-width: 420px;
  margin: auto;
  background: #faf6ee;
  border-radius: 12px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.editor-title {
  margin: 0;
}

.editor-clear {
  flex: 0 0 auto;
  min-height: 40px;
  padding: 0 16px;
  border: 1px solid #cbb89a;
  border-radius: 6px;
  background: #fff;
  color: #7a3b2e;
  cursor: pointer;
}

.editor-clear:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.editor-foot {
  display: flex;
  align-items: center;
  gap: 12px;
}

.editor-side {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
}

.editor-side label {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.editor-side input[type="radio"] {
  width: 18px;
  height: 18px;
}

.editor-error {
  margin: 0;
  color: #b45309;
}

.editor-actions {
  display: flex;
  gap: 8px;
}

.editor-actions button {
  flex: 1;
  min-height: 44px;
  border: 1px solid #cbb89a;
  border-radius: 6px;
  background: #fff;
  color: #7a3b2e;
  cursor: pointer;
}

.editor-actions button[data-test="editor-apply"] {
  background: #7a3b2e;
  border-color: #7a3b2e;
  color: #fff;
}

.editor-actions button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
```

**测试要点**（mock `../../../api`；初始 props 用 `fenToPieces(INITIAL_FEN)`）：

- 渲染弹窗与 32 子。
- 点 `[data-cell='4-0']`（红帅）→ `ChessBoard` 的 `selected` 为 `{x:4,y:0}`。
- 再点 `[data-cell='4-0']` → 棋子数变 31。
- 点 `[data-cell='4-0']` 后点 `[data-cell='4-1']` → 帅移到 (4,1)。
- 选中黑车候选后点空位 → 新位置出现黑方棋子。
- 点 `[data-test='editor-cancel']` → emit `cancel`。
- 点 `[data-test='editor-clear']` → 棋盘棋子数变 0。
- 行棋方为单选，默认红先；切黑先后提交的 `side_to_move` 为 `black`。
- `validatePosition` 返回 `{valid:false, errors:["红方必须有且仅有一个帅"]}` → 点确认后显示该文案且不 emit `apply`。
- `validatePosition` 返回 `{valid:true}` → 点确认后 emit `apply`，payload 含当前草稿棋子。

---

### Task 4: MobileHomeView 接入编辑弹窗

**Files:**
- Modify: `frontend/src/mobile/views/MobileHomeView.vue`
- Test: `frontend/src/mobile/views/__tests__/MobileHomeView.test.js`

**Step 1: 写失败测试** — 在 `MobileHomeView.test.js` 追加：

```js
  it("点编辑打开弹窗", async () => {
    const wrapper = mount(MobileHomeView);
    expect(wrapper.find("[data-test='editor-card']").exists()).toBe(false);
    await wrapper.find("[data-test='ctrl-edit']").trigger("click");
    expect(wrapper.find("[data-test='editor-card']").exists()).toBe(true);
  });

  it("应用编辑后首页棋盘更新", async () => {
    const wrapper = mount(MobileHomeView);
    await wrapper.find("[data-test='ctrl-edit']").trigger("click");
    await wrapper.findComponent(MobileBoardEditor).vm.$emit("apply", []);
    expect(wrapper.findComponent(ChessBoard).props("position").pieces).toHaveLength(0);
    expect(wrapper.find("[data-test='editor-card']").exists()).toBe(false);
  });
```

并在测试顶部 import `MobileBoardEditor`。

**Step 2: 运行确认失败。**

**Step 3: 实现** — `MobileHomeView.vue` 的 `<script setup>` 改为：

```js
import { computed, ref } from "vue";
import ChessBoard from "../../components/ChessBoard.vue";
import BoardControls from "../components/BoardControls.vue";
import MobileBoardEditor from "../components/MobileBoardEditor.vue";
import { INITIAL_FEN, fenToPieces } from "../../utils/chess";

const flipped = ref(false);
const pieces = ref(fenToPieces(INITIAL_FEN));
const editorOpen = ref(false);
const position = computed(() => ({ pieces: pieces.value }));

function onApply(next) {
  pieces.value = next;
  editorOpen.value = false;
}
```

模板中：

```vue
<ChessBoard :position="position" :flipped="flipped" />
<BoardControls
  :flipped="flipped"
  :can-edit="true"
  @flip="flipped = !flipped"
  @edit="editorOpen = true"
/>
<MobileBoardEditor
  v-if="editorOpen"
  :pieces="pieces"
  @cancel="editorOpen = false"
  @apply="onApply"
/>
```

**Step 4: 运行确认通过。**

---

### Task 5: 全量回归

Run: `npm test`（workdir `frontend`），期望全部通过。
