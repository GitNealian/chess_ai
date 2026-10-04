# 背谱模式支持引擎执子 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 背谱模式下复用设置「执子」，轮到引擎方时延迟 0.5 秒自动走棋谱正着，用户只背另一方，校验、计错与 SRS 流程不变。

**Architecture:** 纯前端状态机推进，零后端改动。在 `MobileHomeView.vue` 新增 `maybeEngineReciteMove()`（定时器 + token 防竞态），在进入背谱、用户走对、看答案推进后触发；引擎方着法直接取本地 `moves[ply]` 推进 `ply`，不调用 `best-move`。

**Tech Stack:** Vue 3 `<script setup>` + Vitest 5 + @vue/test-utils 2（`vi.useFakeTimers` 推进 500ms）。

**设计文档:** `docs/plans/2026-10-04-recite-engine-side-design.md`

---

## Task 1: 确认条展示引擎执子提示

**Files:**
- Modify: `frontend/src/mobile/views/MobileHomeView.vue:86-88`（`recite-range` 段落之后）
- Test: `frontend/src/mobile/views/__tests__/MobileHomeView.test.js`（`RECITE_GAME` 之后新增 `ENGINE_GAME`，并在文件末尾 `移动端路由` describe 之前新增测试 describe）

**Step 1: 写失败测试**

在 `MobileHomeView.test.js` 的 `RECITE_GAME`（L487-501）之后新增常量：

```js
const ENGINE_GAME = {
  ...RECITE_GAME,
  moves: [
    { x1: 0, y1: 3, x2: 0, y2: 4 },
    { x1: 0, y1: 6, x2: 0, y2: 5 },
    { x1: 0, y1: 4, x2: 0, y2: 5 },
  ],
};
```

在文件顶部 vitest 导入中加入 `afterEach`：

```js
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
```

在 `describe("MobileHomeView 背谱", ...)` 结束（L851）之后、`describe("移动端路由", ...)` 之前新增：

```js
describe("MobileHomeView 背谱引擎执子", () => {
  beforeEach(() => {
    localStorage.clear();
    api.checkMove.mockReset();
    api.checkMove.mockResolvedValue({ correct: true });
    api.submitReview.mockReset();
    api.submitReview.mockResolvedValue({});
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  async function enterRecite(wrapper) {
    await wrapper.find("[data-test='ctrl-recite']").trigger("click");
    await wrapper.find("[data-test='recite-from-here']").trigger("click");
  }

  it("确认条显示引擎执子提示", async () => {
    const wrapper = mount(MobileHomeView);
    await openGameWithSource(wrapper);
    wrapper.vm.$.setupState.engineSide = "red";
    await wrapper.find("[data-test='ctrl-recite']").trigger("click");
    expect(wrapper.find("[data-test='recite-engine-side']").text()).toBe("引擎执红 · 你背黑方");
    wrapper.vm.$.setupState.engineSide = "black";
    await nextTick();
    expect(wrapper.find("[data-test='recite-engine-side']").text()).toBe("引擎执黑 · 你背红方");
  });

  it("执子不启用时确认条不显示引擎提示", async () => {
    const wrapper = mount(MobileHomeView);
    await openGameWithSource(wrapper);
    await wrapper.find("[data-test='ctrl-recite']").trigger("click");
    expect(wrapper.find("[data-test='recite-engine-side']").exists()).toBe(false);
  });
});
```

**Step 2: 运行测试确认失败**

Run（在 `frontend/` 目录）:
```bash
npx vitest run src/mobile/views/__tests__/MobileHomeView.test.js -t "引擎执子提示"
```
Expected: FAIL，`[data-test='recite-engine-side']` 不存在。

**Step 3: 实现模板提示**

在 `MobileHomeView.vue` 的 `recite-range` 段落（L86-88）之后插入：

```html
        <p
          v-if="engineSide !== 'none'"
          class="recite-meta"
          data-test="recite-engine-side"
        >
          {{ engineSide === "red" ? "引擎执红 · 你背黑方" : "引擎执黑 · 你背红方" }}
        </p>
```

**Step 4: 运行测试确认通过**

Run:
```bash
npx vitest run src/mobile/views/__tests__/MobileHomeView.test.js -t "引擎执子提示"
```
Expected: 2 passed（另一条 `执子不启用时确认条不显示引擎提示` 也匹配关键字「引擎提示」？若未匹配则单独再跑一次 `-t "执子不启用时确认条"`）。

**Step 5: 提交**

```bash
git add frontend/src/mobile/views/MobileHomeView.vue frontend/src/mobile/views/__tests__/MobileHomeView.test.js
git commit -m "feat(mobile): 背谱确认条展示引擎执子提示"
```

---

## Task 2: 引擎自动走棋谱正着

**Files:**
- Modify: `frontend/src/mobile/views/MobileHomeView.vue`（变量区 L271-278、`runEngineMove` 之后、`advanceRecite` L431、`confirmRecite` L663、`finishRecite` L445）
- Test: `frontend/src/mobile/views/__tests__/MobileHomeView.test.js`（新增 describe 内）

**Step 1: 写失败测试**

在 `describe("MobileHomeView 背谱引擎执子", ...)` 内、确认条两个测试之后新增：

```js
  it("引擎执红时进入背谱自动走第一步且不计错", async () => {
    const wrapper = mount(MobileHomeView);
    await openGameWithSource(wrapper);
    wrapper.vm.$.setupState.engineSide = "red";
    await enterRecite(wrapper);
    expect(wrapper.vm.$.setupState.ply).toBe(0);
    vi.advanceTimersByTime(500);
    await nextTick();
    expect(wrapper.vm.$.setupState.ply).toBe(1);
    expect(wrapper.vm.$.setupState.reciteMistakes).toBe(0);
    expect(api.checkMove).not.toHaveBeenCalled();
    expect(wrapper.findComponent(ChessBoard).props("lastMove")).toMatchObject({ x2: 0, y2: 4 });
  });

  it("引擎执红时用户走对后引擎自动接走最后一步并提交 SRS", async () => {
    const wrapper = mount(MobileHomeView);
    await openGameWithSource(wrapper, ENGINE_GAME);
    wrapper.vm.$.setupState.engineSide = "red";
    await enterRecite(wrapper);
    vi.advanceTimersByTime(500);
    await nextTick();
    expect(wrapper.vm.$.setupState.ply).toBe(1);
    const board = wrapper.findComponent(ChessBoard);
    board.vm.$emit("cell-click", 0, 6);
    board.vm.$emit("cell-click", 0, 5);
    await flushPromises();
    expect(api.checkMove).toHaveBeenCalledWith(1, {
      ply: 1,
      move: { x1: 0, y1: 6, x2: 0, y2: 5 },
    });
    expect(wrapper.vm.$.setupState.ply).toBe(2);
    vi.advanceTimersByTime(500);
    await nextTick();
    expect(wrapper.vm.$.setupState.ply).toBe(3);
    expect(api.submitReview).toHaveBeenCalledWith(1, {
      mistake_count: 0,
      duration_ms: expect.any(Number),
      revealed: false,
    });
    expect(wrapper.vm.$.setupState.reciteMode).toBe(false);
  });

  it("引擎执黑时用户走完后引擎自动走完并提交 SRS", async () => {
    const wrapper = mount(MobileHomeView);
    await openGameWithSource(wrapper);
    wrapper.vm.$.setupState.engineSide = "black";
    await enterRecite(wrapper);
    const board = wrapper.findComponent(ChessBoard);
    board.vm.$emit("cell-click", 0, 3);
    board.vm.$emit("cell-click", 0, 4);
    await flushPromises();
    expect(wrapper.vm.$.setupState.ply).toBe(1);
    vi.advanceTimersByTime(500);
    await nextTick();
    expect(wrapper.vm.$.setupState.ply).toBe(2);
    expect(api.submitReview).toHaveBeenCalledWith(1, {
      mistake_count: 0,
      duration_ms: expect.any(Number),
      revealed: false,
    });
    expect(wrapper.vm.$.setupState.reciteMode).toBe(false);
  });
```

**Step 2: 运行测试确认失败**

Run:
```bash
npx vitest run src/mobile/views/__tests__/MobileHomeView.test.js -t "引擎执红"
```
Expected: FAIL，`ply` 停留在 0（引擎未自动走子）。

**Step 3: 实现自动走子**

3a. 变量区（L275-278）改为：

```js
let pending = false;
let moveToken = 0;
let engineToken = 0;
let navToken = 0;
let reciteEngineTimer = null;
let reciteEngineToken = 0;
const RECITE_ENGINE_DELAY_MS = 500;
```

3b. 在 `runEngineMove` 函数结束后（L373 之后）新增：

```js
function clearReciteEngineTimer() {
  if (reciteEngineTimer !== null) {
    clearTimeout(reciteEngineTimer);
    reciteEngineTimer = null;
  }
  reciteEngineToken += 1;
}

function maybeEngineReciteMove() {
  if (!reciteMode.value || engineSide.value === "none") return;
  if (reciteEngineTimer !== null) return;
  if (gameOver.value || ply.value >= moves.value.length) return;
  if (sideToMove.value !== engineSide.value) return;
  const token = ++reciteEngineToken;
  reciteEngineTimer = setTimeout(() => {
    reciteEngineTimer = null;
    if (token !== reciteEngineToken) return;
    if (!reciteMode.value || engineSide.value === "none") return;
    if (gameOver.value || ply.value >= moves.value.length) return;
    if (sideToMove.value !== engineSide.value) return;
    advanceRecite();
    maybeEngineReciteMove();
  }, RECITE_ENGINE_DELAY_MS);
}
```

3c. `advanceRecite`（L431-435）改为：

```js
function advanceRecite() {
  ply.value += 1;
  selected.value = null;
  if (ply.value >= moves.value.length) {
    finishRecite();
    return;
  }
  maybeEngineReciteMove();
}
```

3d. `finishRecite`（L445）函数体第一行新增 `clearReciteEngineTimer();`：

```js
function finishRecite() {
  clearReciteEngineTimer();
  const game = currentGame.value;
  // ...以下不变
```

3e. `confirmRecite`（L663-678）末尾（`engineThinking.value = false;` 之后）新增：

```js
  maybeEngineReciteMove();
```

**Step 4: 运行测试确认通过**

Run:
```bash
npx vitest run src/mobile/views/__tests__/MobileHomeView.test.js -t "引擎执红"
npx vitest run src/mobile/views/__tests__/MobileHomeView.test.js -t "引擎执黑"
```
Expected: 2 passed / 1 passed。

**Step 5: 提交**

```bash
git add frontend/src/mobile/views/MobileHomeView.vue frontend/src/mobile/views/__tests__/MobileHomeView.test.js
git commit -m "feat(mobile): 背谱模式引擎自动走棋谱正着"
```

---

## Task 3: 竞态清理与引擎回合点击防护

**Files:**
- Modify: `frontend/src/mobile/views/MobileHomeView.vue`（`onCellClick` L477、`exitRecite` L466、`confirmRecite` L663、`onOpenGame` L680、`onApply` L796）
- Test: `frontend/src/mobile/views/__tests__/MobileHomeView.test.js`

**Step 1: 写失败测试**

在 `describe("MobileHomeView 背谱引擎执子", ...)` 内追加：

```js
  it("引擎走子延迟期间退出背谱不再自动落子", async () => {
    const wrapper = mount(MobileHomeView);
    await openGameWithSource(wrapper);
    wrapper.vm.$.setupState.engineSide = "red";
    await enterRecite(wrapper);
    await wrapper.find("[data-test='ctrl-exit-recite']").trigger("click");
    vi.advanceTimersByTime(1000);
    await nextTick();
    expect(wrapper.vm.$.setupState.ply).toBe(0);
    expect(wrapper.vm.$.setupState.reciteMode).toBe(false);
  });

  it("引擎回合点击棋盘不选中也不走子", async () => {
    const wrapper = mount(MobileHomeView);
    await openGameWithSource(wrapper);
    wrapper.vm.$.setupState.engineSide = "red";
    await enterRecite(wrapper);
    const board = wrapper.findComponent(ChessBoard);
    board.vm.$emit("cell-click", 0, 3);
    board.vm.$emit("cell-click", 0, 4);
    expect(wrapper.vm.$.setupState.selected).toBe(null);
    expect(api.checkMove).not.toHaveBeenCalled();
  });
```

**Step 2: 运行测试确认失败**

Run:
```bash
npx vitest run src/mobile/views/__tests__/MobileHomeView.test.js -t "引擎回合点击棋盘不选中"
```
Expected: FAIL，`selected` 为 `{ x: 0, y: 3 }`（用户选中了引擎方的子）。

**Step 3: 实现防护与清理**

3a. `onCellClick`（L477-501）中，在背谱分支的 `if (!reciteMode.value) { ... }` 块之后、`const piece = ...` 之前插入：

```js
  if (engineSide.value !== "none" && sideToMove.value === engineSide.value) return;
```

改完后该函数片段为：

```js
function onCellClick(x, y) {
  if (isReview.value && !reciteMode.value) return;
  if (pending) return;
  if (!reciteMode.value) {
    // ...以下浏览态逻辑不变
  }
  if (engineSide.value !== "none" && sideToMove.value === engineSide.value) return;
  const piece = pieces.value.find((p) => p.x === x && p.y === y);
  // ...以下不变
}
```

3b. `exitRecite`（L466）函数体第一行新增 `clearReciteEngineTimer();`。

3c. `confirmRecite`（L663）函数体第一行新增 `clearReciteEngineTimer();`。

3d. `onOpenGame`（L680）中 `engineToken += 1;`（L698）之前新增 `clearReciteEngineTimer();`。

3e. `onApply`（L796）中 `engineToken += 1;`（L813）之前新增 `clearReciteEngineTimer();`。

**Step 4: 运行测试确认通过**

Run:
```bash
npx vitest run src/mobile/views/__tests__/MobileHomeView.test.js -t "引擎执子"
```
Expected: 全部通过（含 Task 1/2 的测试）。

**Step 5: 提交**

```bash
git add frontend/src/mobile/views/MobileHomeView.vue frontend/src/mobile/views/__tests__/MobileHomeView.test.js
git commit -m "fix(mobile): 引擎背谱走子竞态清理与回合点击防护"
```

---

## Task 4: 全量测试与构建

**Files:**
- Verify: 全部前端测试
- Build: `frontend/dist/`（已被 `frontend/.gitignore` 忽略，无需提交）

**Step 1: 全量测试**

Run（在 `frontend/` 目录）:
```bash
npm test
```
Expected: 全部通过，无回归。

**Step 2: 构建产物**

Run:
```bash
npm run build
```
Expected: 构建成功，`dist/` 更新。

**Step 3: 确认工作区干净**

Run:
```bash
git status --short
```
Expected: 无未提交改动（dist 被忽略）。

---

## 手动验收清单

- [ ] 设置「执红」后打开棋谱点「背谱」，确认条显示「引擎执红 · 你背黑方」。
- [ ] 进入背谱约 0.5 秒后红方自动落子，用户只需走黑方。
- [ ] 引擎执红且棋谱最后一步为红方时，用户走完最后一步黑方后引擎自动走完并提示「背谱完成」。
- [ ] 引擎回合点击棋盘无反应，不能替引擎走子。
- [ ] 引擎等待期间点「退出背谱」，棋盘不再自动落子，且不提交 SRS。
- [ ] 「执子」为不启用时，背谱行为与之前一致（双方都由用户走）。
