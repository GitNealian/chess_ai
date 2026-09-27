# 移动端棋谱推演 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 移动端区分「自由走子」与「棋谱只读」两种模式，并为棋谱只读模式提供独立弹窗推演（不影响棋谱、实时显示评分）。

**Architecture:** 以 `currentGame` 是否存在区分模式；棋盘走子仍全部经后端 `validate-move` 校验；推演弹窗是一个自持状态的新组件，复用 `ChessBoard` 与 `MobileAnalysis`，不改后端。

**Tech Stack:** Vue 3 `<script setup>`、Vitest + @vue/test-utils、Vite。

**设计依据：** `docs/plans/2026-09-27-mobile-inference-design.md`

---

## 约定

- 前端目录：`/home/nealian/chess/frontend`
- 单测命令（在 `frontend/` 下）：
  - 全量：`npm run test`
  - 单文件：`npx vitest run src/mobile/components/__tests__/BoardControls.test.js`
- 规则：不重写象棋规则；所有走子合法性走后端。
- 提交信息风格参考仓库历史（`feat: ...` / `test: ...`）。

---

### Task 1: BoardControls 新增「推演」按钮

**Files:**
- Modify: `frontend/src/mobile/components/BoardControls.vue`
- Test: `frontend/src/mobile/components/__tests__/BoardControls.test.js`

**Step 1: 写失败测试**

在 `BoardControls.test.js` 末尾 `describe` 内追加：

```js
  it("showInfer 为 true 时额外渲染推演按钮并发出 infer", async () => {
    const wrapper = mount(BoardControls, { props: { showInfer: true, canInfer: true } });
    const infer = wrapper.find("[data-test='ctrl-infer']");
    expect(infer.exists()).toBe(true);
    await infer.trigger("click");
    expect(wrapper.emitted("infer")).toHaveLength(1);
  });

  it("showInfer 缺省不渲染推演按钮", () => {
    const wrapper = mount(BoardControls);
    expect(wrapper.find("[data-test='ctrl-infer']").exists()).toBe(false);
  });
```

**Step 2: 运行测试确认失败**

Run: `npx vitest run src/mobile/components/__tests__/BoardControls.test.js`
Expected: FAIL（找不到 `[data-test='ctrl-infer']`）

**Step 3: 实现**

`BoardControls.vue` 模板：在「编辑」按钮后追加：

```html
    <button
      v-if="showInfer"
      type="button"
      data-test="ctrl-infer"
      :disabled="!canInfer"
      @click="emit('infer')"
    >
      推演
    </button>
```

`defineProps` 追加：

```js
  showInfer: { type: Boolean, default: false },
  canInfer: { type: Boolean, default: false },
```

`defineEmits` 追加 `"infer"`。

**Step 4: 运行测试确认通过**

Run: `npx vitest run src/mobile/components/__tests__/BoardControls.test.js`
Expected: PASS（含原有 6 按钮用例，因默认 `showInfer=false` 仍为 6 个）

**Step 5: 提交**

```bash
git add frontend/src/mobile/components/BoardControls.vue frontend/src/mobile/components/__tests__/BoardControls.test.js
git commit -m "feat(mobile): 棋盘控制栏新增推演按钮"
```

---

### Task 2: 新增推演弹窗组件 MobileInferenceDialog

**Files:**
- Create: `frontend/src/mobile/components/MobileInferenceDialog.vue`
- Test: `frontend/src/mobile/components/__tests__/MobileInferenceDialog.test.js`

**Step 1: 写失败测试**

新建 `MobileInferenceDialog.test.js`：

```js
import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { nextTick } from "vue";
import MobileInferenceDialog from "../MobileInferenceDialog.vue";

vi.mock("../../../api", () => ({
  api: { validateMove: vi.fn() },
  analyzeStream: vi.fn(),
  intentStream: vi.fn(),
}));

import { analyzeStream, api } from "../../../api";

const FEN = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1";
const baseMoves = [{ x1: 0, y1: 0, x2: 0, y2: 1, chinese: "车九进一" }];

function mountDialog(props = {}) {
  return mount(MobileInferenceDialog, {
    props: { initialFen: FEN, baseMoves, ...props },
  });
}

describe("MobileInferenceDialog", () => {
  beforeEach(() => {
    api.validateMove.mockReset();
    analyzeStream.mockReset();
  });

  it("以快照局面发起评分，moves 为 baseMoves", () => {
    mountDialog();
    expect(analyzeStream).toHaveBeenCalledTimes(1);
    const payload = analyzeStream.mock.calls[0][0];
    expect(payload.initial_fen).toBe(FEN);
    expect(payload.moves).toEqual([{ x1: 0, y1: 0, x2: 0, y2: 1 }]);
  });

  it("弹窗内走子经 validateMove 校验并追加着法", async () => {
    api.validateMove.mockResolvedValue({ legal: true, chinese: "马八进七", check: false });
    const wrapper = mountDialog();
    // 快照走完车九进一后，轮到黑方；用红方棋子需在红方回合。此处直接选当前行棋方棋子。
    const piece = wrapper.findComponent({ name: "ChessBoard" });
    // 简化：直接调用组件内部走子路径——点击一个可走目标
    await wrapper.find("[data-cell='0-9']").trigger("click"); // 选红车 (x=0,y=9)
    await wrapper.find("[data-cell='0-8']").trigger("click");
    await flushPromises();
    expect(api.validateMove).toHaveBeenCalledTimes(1);
    expect(api.validateMove.mock.calls[0][0].initial_fen).toBe(FEN);
  });

  it("悔棋撤销一步推演", async () => {
    api.validateMove.mockResolvedValue({ legal: true, chinese: "马八进七", check: false });
    const wrapper = mountDialog();
    await wrapper.find("[data-cell='0-9']").trigger("click");
    await wrapper.find("[data-cell='0-8']").trigger("click");
    await flushPromises();
    await wrapper.find("[data-test='infer-undo']").trigger("click");
    await nextTick();
    // 悔棋后再次发起评分时 moves 回到 baseMoves
    const last = analyzeStream.mock.calls.at(-1)[0];
    expect(last.moves).toEqual([{ x1: 0, y1: 0, x2: 0, y2: 1 }]);
  });

  it("关闭按钮发出 close", async () => {
    const wrapper = mountDialog();
    await wrapper.find("[data-test='infer-close']").trigger("click");
    expect(wrapper.emitted("close")).toHaveLength(1);
  });

  it("非法着法显示提示且不追加", async () => {
    api.validateMove.mockResolvedValue({ legal: false, reason: "着法不合法" });
    const wrapper = mountDialog();
    await wrapper.find("[data-cell='0-9']").trigger("click");
    await wrapper.find("[data-cell='1-9']").trigger("click");
    await flushPromises();
    expect(wrapper.find("[data-test='infer-hint']").text()).toContain("着法不合法");
  });
});
```

> 说明：走子测试用初始局面快照（`baseMoves` 仅用于评分起点，棋盘快照仍是 `initialFen`，见 Step 3 设计——为让棋盘与评分一致，本组件棋盘快照同样由 `fenToPieces(initialFen)` + `baseMoves` 计算，故红车在 `0,9`）。若实现后坐标不便，允许按实际快照调整测试中的坐标，但必须保持「校验参数含 initial_fen 与 baseMoves + 推演着法」的断言不变。

**Step 2: 运行测试确认失败**

Run: `npx vitest run src/mobile/components/__tests__/MobileInferenceDialog.test.js`
Expected: FAIL（组件不存在）

**Step 3: 实现组件**

新建 `frontend/src/mobile/components/MobileInferenceDialog.vue`：

```vue
<script setup>
import { computed, ref } from "vue";
import ChessBoard from "../../components/ChessBoard.vue";
import MobileAnalysis from "./MobileAnalysis.vue";
import { applyMove, fenToPieces } from "../../utils/chess";
import { api } from "../../api";

const props = defineProps({
  initialFen: { type: String, required: true },
  baseMoves: { type: Array, default: () => [] },
});
const emit = defineEmits(["close"]);

const moves = ref([]);
const selected = ref(null);
const hint = ref("");
const flipped = ref(false);
const arrows = ref([]);
let pending = false;
let token = 0;

const firstSide = props.initialFen.split(" ")[1] === "b" ? "black" : "red";
const basePieces = (() => {
  let out = fenToPieces(props.initialFen);
  for (const m of props.baseMoves) out = applyMove(out, m);
  return out;
})();

const allMoves = computed(() =>
  props.baseMoves
    .concat(moves.value)
    .map(({ x1, y1, x2, y2 }) => ({ x1, y1, x2, y2 }))
);
const sideToMove = computed(() => {
  if (allMoves.value.length % 2 === 0) return firstSide;
  return firstSide === "red" ? "black" : "red";
});
const pieces = computed(() => {
  let out = basePieces;
  for (const m of moves.value) out = applyMove(out, m);
  return out;
});
const position = computed(() => ({ pieces: pieces.value }));

async function submit(move) {
  hint.value = "";
  pending = true;
  const t = ++token;
  try {
    const data = await api.validateMove({
      initial_fen: props.initialFen,
      moves: allMoves.value,
      move,
    });
    if (t !== token) return;
    if (!data.legal) {
      hint.value = data.reason || "着法不合法";
      return;
    }
    moves.value.push({
      ...move,
      chinese: data.chinese || "",
      check: Boolean(data.check),
      gameOver: data.game_over || null,
    });
    selected.value = null;
  } catch (err) {
    if (t !== token) return;
    hint.value =
      err?.response?.data?.detail || err?.response?.data?.error || "校验失败，请重试";
  } finally {
    if (t === token) pending = false;
  }
}

function onCellClick(x, y) {
  if (pending) return;
  const piece = pieces.value.find((p) => p.x === x && p.y === y);
  if (selected.value) {
    if (piece && piece.side === sideToMove.value) {
      const same = selected.value.x === x && selected.value.y === y;
      selected.value = same ? null : { x, y };
      return;
    }
    submit({ x1: selected.value.x, y1: selected.value.y, x2: x, y2: y });
    return;
  }
  if (piece && piece.side === sideToMove.value) selected.value = { x, y };
}

function undo() {
  token += 1;
  pending = false;
  selected.value = null;
  hint.value = "";
  moves.value.pop();
}
</script>

<template>
  <div class="infer-mask" data-test="infer-mask" @click.self="selected = null">
    <div class="infer-card" data-test="infer-card">
      <h3 class="infer-title">推演</h3>
      <ChessBoard
        :position="position"
        :selected="selected"
        :arrows="arrows"
        :flipped="flipped"
        @cell-click="onCellClick"
      />
      <p v-if="hint" class="infer-hint" data-test="infer-hint">{{ hint }}</p>
      <div class="infer-actions">
        <button type="button" data-test="infer-undo" :disabled="!moves.length" @click="undo">
          悔棋
        </button>
        <button type="button" data-test="infer-flip" @click="flipped = !flipped">翻转</button>
        <button type="button" data-test="infer-close" @click="emit('close')">关闭</button>
      </div>
      <MobileAnalysis
        :initial-fen="initialFen"
        :moves="allMoves"
        :score="true"
        :intent="false"
        @arrows="arrows = $event"
      />
    </div>
  </div>
</template>

<style scoped>
.infer-mask {
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

.infer-card {
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

.infer-title {
  margin: 0;
}

.infer-hint {
  margin: 0;
  color: #b45309;
}

.infer-actions {
  display: flex;
  gap: 8px;
}

.infer-actions button {
  flex: 1;
  min-height: 44px;
  border: 1px solid #cbb89a;
  border-radius: 6px;
  background: #fff;
  color: #7a3b2e;
  cursor: pointer;
}

.infer-actions button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
```

**Step 4: 运行测试确认通过**

Run: `npx vitest run src/mobile/components/__tests__/MobileInferenceDialog.test.js`
Expected: PASS

**Step 5: 提交**

```bash
git add frontend/src/mobile/components/MobileInferenceDialog.vue frontend/src/mobile/components/__tests__/MobileInferenceDialog.test.js
git commit -m "feat(mobile): 新增棋谱推演弹窗组件"
```

---

### Task 3: MobileHomeView 区分自由走子 / 棋谱只读并接入推演

**Files:**
- Modify: `frontend/src/mobile/views/MobileHomeView.vue`
- Test: `frontend/src/mobile/views/__tests__/MobileHomeView.test.js`

**Step 1: 写失败测试**

在 `MobileHomeView.test.js` 的 `describe("MobileHomeView")` 内追加（复用已有 `loadGame` 辅助）：

```js
  it("未打开棋谱时 engineSide 为 none 也可自定义走子", async () => {
    api.validateMove.mockResolvedValue({ legal: true, chinese: "车九进一", check: false });
    const wrapper = mount(MobileHomeView);
    await wrapper.find("[data-cell='0-9']").trigger("click");
    await wrapper.find("[data-cell='0-8']").trigger("click");
    await flushPromises();
    expect(api.validateMove).toHaveBeenCalledTimes(1);
  });

  it("打开棋谱后棋盘只读且显示推演按钮", async () => {
    api.validateMove.mockResolvedValue({ legal: true, chinese: "车九进一", check: false });
    const wrapper = mount(MobileHomeView);
    await loadGame(wrapper, { id: 9, name: "局", initial_fen: INITIAL_FEN, moves: [] });
    expect(wrapper.find("[data-test='ctrl-infer']").exists()).toBe(true);
    await wrapper.find("[data-cell='0-9']").trigger("click");
    await wrapper.find("[data-cell='0-8']").trigger("click");
    await flushPromises();
    expect(api.validateMove).not.toHaveBeenCalled();
  });

  it("棋谱模式下点推演打开推演弹窗", async () => {
    analyzeStream.mockClear();
    const wrapper = mount(MobileHomeView);
    await loadGame(wrapper, { id: 10, name: "局", initial_fen: INITIAL_FEN, moves: [] });
    await wrapper.find("[data-test='ctrl-infer']").trigger("click");
    expect(wrapper.find("[data-test='infer-card']").exists()).toBe(true);
  });
```

**Step 2: 运行测试确认失败**

Run: `npx vitest run src/mobile/views/__tests__/MobileHomeView.test.js`
Expected: FAIL（自由模式不走子 / 无推演按钮）

**Step 3: 实现**

`MobileHomeView.vue` 修改：

1）import 推演弹窗：

```js
import MobileInferenceDialog from "../components/MobileInferenceDialog.vue";
```

2）新增状态与判定：

```js
const inferOpen = ref(false);
const isReview = computed(() => !!currentGame.value);
```

3）模板 `BoardControls` 调整：

```html
      :show-undo="!isReview || engineSide !== 'none'"
      :can-undo="(!isReview || engineSide !== 'none') && moves.length > 0"
      :show-infer="isReview"
      :can-infer="isReview"
      @infer="inferOpen = true"
```

4）模板追加推演弹窗（在 `MobileBoardEditor` 附近）：

```html
    <MobileInferenceDialog
      v-if="inferOpen"
      :initial-fen="initialFen"
      :base-moves="moveSlice"
      @close="inferOpen = false"
    />
```

5）`onCellClick` 改为：

```js
function onCellClick(x, y) {
  if (isReview.value || pending) return;
  if (engineSide.value !== "none" && ply.value !== moves.value.length) return;
  if (gameOver.value || engineThinking.value) return;
  if (isEngineTurn.value) {
    runEngineMove();
    return;
  }
  const piece = pieces.value.find((p) => p.x === x && p.y === y);
  if (selected.value) {
    if (piece && piece.side === sideToMove.value) {
      const same = selected.value.x === x && selected.value.y === y;
      selected.value = same ? null : { x, y };
      return;
    }
    submitMove({ x1: selected.value.x, y1: selected.value.y, x2: x, y2: y });
    return;
  }
  if (piece && piece.side === sideToMove.value) selected.value = { x, y };
}
```

6）`undo` 改为（棋谱模式不进这里）：

```js
function undo() {
  if (isReview.value || !moves.value.length) return;
  engineToken += 1;
  moveToken += 1;
  engineThinking.value = false;
  pending = false;
  selected.value = null;
  hint.value = "";
  moves.value.pop();
  while (moves.value.length && sideAt(moves.value.length) === engineSide.value) {
    moves.value.pop();
  }
  ply.value = moves.value.length;
}
```

7）`statusText` 首行由 `if (engineSide.value === "none") return "";` 改为：

```js
  if (isReview.value) return "";
```

8）`onOpenGame` 内追加 `inferOpen.value = false;`（与其它重置同处）。

**Step 4: 运行测试确认通过**

Run: `npx vitest run src/mobile/views/__tests__/MobileHomeView.test.js`
Expected: PASS（原有引擎对弈/打谱用例不回归）

**Step 5: 提交**

```bash
git add frontend/src/mobile/views/MobileHomeView.vue frontend/src/mobile/views/__tests__/MobileHomeView.test.js
git commit -m "feat(mobile): 区分自由走子与棋谱只读并接入推演"
```

---

### Task 4: 构建与全量回归

**Files:**
- Modify: `frontend/dist/**`（构建产物）

**Step 1: 运行前端全量测试**

Run: `npm run test`
Expected: 全部 PASS（原 301 + 新增用例）

**Step 2: 构建产物**

Run: `npm run build`
Expected: `✓ built`，`dist/` 更新

**Step 3: 提交**

```bash
git add frontend/dist
git commit -m "build(mobile): 更新移动端推演功能产物"
```

---

## 备注

- 若 Task 2 测试坐标与实际快照不符，按实际调整坐标，但保留参数断言。
- 不改后端；`validate-move` 与 `analyze` 复用现有接口。
- 完成后在浏览器/真机验证：打开棋谱只能前进后退、推演弹窗可走子且评分刷新、关闭后棋谱不变。
