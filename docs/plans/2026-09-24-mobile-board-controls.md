# 移动端棋盘控制栏 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在移动端 `/m` 首页棋盘下方新增一排控制按钮（开局/后退/前进/终局/翻转/编辑），本次仅「翻转」生效，其余禁用占位。

**Architecture:** 抽纯展示组件 `BoardControls.vue`（props/emits 驱动，无业务状态），由 `MobileHomeView.vue` 持有 `flipped` 状态并接线到 `ChessBoard` 的 `flipped` prop。测试用 Vitest + @vue/test-utils。

**Tech Stack:** Vue 3 `<script setup>`、Vue Test Utils、Vitest。

**设计文档:** `docs/plans/2026-09-24-mobile-board-controls-design.md`

---

### Task 1: 新增 BoardControls 展示组件

**Files:**
- Create: `frontend/src/mobile/components/BoardControls.vue`
- Test: `frontend/src/mobile/components/__tests__/BoardControls.test.js`

**Step 1: 写失败测试**

创建 `frontend/src/mobile/components/__tests__/BoardControls.test.js`：

```js
import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import BoardControls from "../BoardControls.vue";

describe("BoardControls", () => {
  it("渲染 6 个控制按钮", () => {
    const wrapper = mount(BoardControls);
    const buttons = wrapper.findAll("button");
    expect(buttons).toHaveLength(6);
    expect(buttons.map((b) => b.text())).toEqual([
      "开局",
      "后退",
      "前进",
      "终局",
      "翻转",
      "编辑",
    ]);
  });

  it("点击翻转发出 flip 事件", async () => {
    const wrapper = mount(BoardControls);
    await wrapper.find("[data-test='ctrl-flip']").trigger("click");
    expect(wrapper.emitted("flip")).toHaveLength(1);
  });

  it("canXxx 为 false 时对应按钮禁用", () => {
    const wrapper = mount(BoardControls);
    for (const key of ["start", "prev", "next", "end", "edit"]) {
      expect(wrapper.find(`[data-test='ctrl-${key}']`).attributes("disabled")).toBeDefined();
    }
  });

  it("canXxx 为 true 时点击发出对应事件", async () => {
    const wrapper = mount(BoardControls, {
      props: {
        canStart: true,
        canPrev: true,
        canNext: true,
        canEnd: true,
        canEdit: true,
      },
    });
    for (const key of ["start", "prev", "next", "end", "edit"]) {
      await wrapper.find(`[data-test='ctrl-${key}']`).trigger("click");
      expect(wrapper.emitted(key)).toHaveLength(1);
    }
  });

  it("flipped 为 true 时翻转按钮 aria-pressed 为 true", () => {
    const wrapper = mount(BoardControls, { props: { flipped: true } });
    expect(wrapper.find("[data-test='ctrl-flip']").attributes("aria-pressed")).toBe("true");
  });
});
```

**Step 2: 运行测试确认失败**

Run: `npm test -- src/mobile/components/__tests__/BoardControls.test.js`
Workdir: `frontend`
Expected: FAIL，报找不到 `../BoardControls.vue`。

**Step 3: 写最小实现**

创建 `frontend/src/mobile/components/BoardControls.vue`：

```vue
<template>
  <div class="board-controls">
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
    <button type="button" data-test="ctrl-edit" :disabled="!canEdit" @click="emit('edit')">
      编辑
    </button>
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
});

const emit = defineEmits(["start", "prev", "next", "end", "flip", "edit"]);
</script>

<style scoped>
.board-controls {
  display: flex;
  gap: 8px;
}

.board-controls button {
  flex: 1 1 0;
  min-height: 44px;
  padding: 8px 4px;
  font-size: 14px;
  white-space: nowrap;
  color: #7a3b2e;
  background: #fff;
  border: 1px solid #cbb89a;
  border-radius: 6px;
  cursor: pointer;
}

.board-controls button:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.board-controls button[aria-pressed="true"] {
  background: #f4e3c1;
  border-color: #7a3b2e;
}
</style>
```

**Step 4: 运行测试确认通过**

Run: `npm test -- src/mobile/components/__tests__/BoardControls.test.js`
Workdir: `frontend`
Expected: PASS，5 个用例全绿。

**Step 5: 提交**

```bash
git add frontend/src/mobile/components/BoardControls.vue frontend/src/mobile/components/__tests__/BoardControls.test.js
git commit -m "feat(frontend): 移动端棋盘控制栏组件"
```

---

### Task 2: 接入 MobileHomeView 并支持翻转

**Files:**
- Modify: `frontend/src/mobile/views/MobileHomeView.vue`
- Test: `frontend/src/mobile/views/__tests__/MobileHomeView.test.js`

**Step 1: 写失败测试**

在 `frontend/src/mobile/views/__tests__/MobileHomeView.test.js` 顶部补充 import：

```js
import ChessBoard from "../../../components/ChessBoard.vue";
```

在 `describe("MobileHomeView", ...)` 内追加两个用例：

```js
  it("棋盘下方渲染控制栏", () => {
    const wrapper = mount(MobileHomeView);
    expect(wrapper.findAll(".board-controls button")).toHaveLength(6);
  });

  it("点击翻转后棋盘翻转", async () => {
    const wrapper = mount(MobileHomeView);
    expect(wrapper.findComponent(ChessBoard).props("flipped")).toBe(false);
    await wrapper.find("[data-test='ctrl-flip']").trigger("click");
    expect(wrapper.findComponent(ChessBoard).props("flipped")).toBe(true);
  });
```

**Step 2: 运行测试确认失败**

Run: `npm test -- src/mobile/views/__tests__/MobileHomeView.test.js`
Workdir: `frontend`
Expected: FAIL，控制栏按钮数为 0 / 找不到 `[data-test='ctrl-flip']`。

**Step 3: 修改实现**

将 `frontend/src/mobile/views/MobileHomeView.vue` 改为：

```vue
<template>
  <section class="mobile-home">
    <div class="mobile-home__board">
      <ChessBoard :position="position" :flipped="flipped" />
    </div>
    <BoardControls :flipped="flipped" @flip="flipped = !flipped" />
    <div class="mobile-home__body">
      <h1 class="mobile-home__title">移动端界面</h1>
      <p class="mobile-home__hint">骨架已就绪，后续在此实现移动端页面。</p>
    </div>
  </section>
</template>

<script setup>
import { computed, ref } from "vue";
import ChessBoard from "../../components/ChessBoard.vue";
import BoardControls from "../components/BoardControls.vue";
import { INITIAL_FEN, fenToPieces } from "../../utils/chess";

const flipped = ref(false);
const position = computed(() => ({ pieces: fenToPieces(INITIAL_FEN) }));
</script>
```

（`<style scoped>` 保持不变，在末尾追加 `.mobile-home .board-controls { margin-top: 0; }` 无需；控制栏与棋盘间距由 `.mobile-home` 的 `gap: 16px` 提供。）

**Step 4: 运行测试确认通过**

Run: `npm test -- src/mobile/views/__tests__/MobileHomeView.test.js`
Workdir: `frontend`
Expected: PASS，全部用例绿。

**Step 5: 全量测试回归**

Run: `npm test`
Workdir: `frontend`
Expected: 全部通过。

**Step 6: 提交**

```bash
git add frontend/src/mobile/views/MobileHomeView.vue frontend/src/mobile/views/__tests__/MobileHomeView.test.js
git commit -m "feat(frontend): 移动端首页接入棋盘控制栏与翻转"
```

---

## 验证清单

- [ ] `npm test` 全量通过
- [ ] `/m` 首页棋盘下方出现 6 个文字按钮，等宽平铺
- [ ] 点击「翻转」棋盘上下左右镜像，河界文字随之旋转
- [ ] 开局/后退/前进/终局/编辑呈禁用态（半透明、不可点）
