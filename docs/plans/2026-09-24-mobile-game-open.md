# 移动端打开棋谱与打谱 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 首页棋盘上方新增「打开」「设置」按钮；打开棋谱可载入并在控制栏前进/后退打谱；设置弹窗先空着。

**Architecture:** 新增 `MobileGamePicker.vue`（打开弹窗，复用 `api.listGames`），首页用 `basePieces/moves/ply` 统一自由局面与打谱局面，`pieces` 由着法计算；控制栏按 `ply` 启用。测试用 Vitest + Vue Test Utils。

**Tech Stack:** Vue 3 `<script setup>`、Vue Test Utils、Vitest。

**设计文档:** `docs/plans/2026-09-24-mobile-game-open-design.md`

---

### Task 1: MobileGamePicker 打开弹窗

**Files:**
- Create: `frontend/src/mobile/components/MobileGamePicker.vue`
- Test: `frontend/src/mobile/components/__tests__/MobileGamePicker.test.js`

**组件实现：**

```vue
<script setup>
import { onMounted, ref } from "vue";
import { api } from "../../api";

const emit = defineEmits(["select", "cancel"]);
const loading = ref(true);
const error = ref(false);
const games = ref([]);

async function load() {
  loading.value = true;
  error.value = false;
  try {
    const data = await api.listGames({ page_size: 50 });
    games.value = data.items || [];
  } catch {
    error.value = true;
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>

<template>
  <div class="picker-mask" data-test="picker-mask" @click.self="emit('cancel')">
    <div class="picker-card" data-test="picker-card">
      <h3 class="picker-title">打开棋谱</h3>
      <p v-if="loading" class="picker-hint">加载中…</p>
      <p v-else-if="error" class="picker-hint">
        加载失败
        <button type="button" data-test="picker-retry" @click="load">重试</button>
      </p>
      <p v-else-if="games.length === 0" class="picker-hint" data-test="picker-empty">
        暂无棋谱
      </p>
      <ul v-else class="picker-list">
        <li v-for="game in games" :key="game.id">
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
      <div class="picker-actions">
        <button type="button" data-test="picker-cancel" @click="emit('cancel')">取消</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.picker-mask {
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

.picker-card {
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

.picker-title {
  margin: 0;
}

.picker-hint {
  margin: 0;
  color: #6b5a45;
}

.picker-list {
  list-style: none;
  margin: 0;
  padding: 0;
  max-height: 60vh;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.picker-item {
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

.picker-name {
  color: #7a3b2e;
  font-size: 16px;
}

.picker-sub {
  color: #8a7a63;
  font-size: 12px;
}

.picker-actions {
  display: flex;
}

.picker-actions button {
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

**测试要点**（mock `../../../api` 的 `listGames`）：

- `items` 两项 → 渲染 2 个 `[data-game]`，文本含名称。
- 点击 `[data-game='7']` → emit `select`，payload `id=7`。
- `items: []` → `[data-test='picker-empty']` 存在。
- 点 `[data-test='picker-cancel']` → emit `cancel`。

---

### Task 2: MobileHomeView 接线

**Files:**
- Modify: `frontend/src/mobile/views/MobileHomeView.vue`
- Test: `frontend/src/mobile/views/__tests__/MobileHomeView.test.js`

**Step 1: 写失败测试** — 顶部 import 增加 `import { api } from "../../../api";` 与 `import { INITIAL_FEN } from "../../../utils/chess";`，追加：

```js
  it("点打开显示棋谱选择器", async () => {
    const wrapper = mount(MobileHomeView);
    await wrapper.find("[data-test='open']").trigger("click");
    await flushPromises();
    expect(wrapper.find("[data-test='picker-card']").exists()).toBe(true);
  });

  it("选中棋谱后可前进打谱", async () => {
    api.listGames.mockResolvedValueOnce({
      items: [
        {
          id: 1,
          name: "测试局",
          initial_fen: INITIAL_FEN,
          moves: [{ x1: 0, y1: 0, x2: 0, y2: 1 }],
        },
      ],
    });
    const wrapper = mount(MobileHomeView);
    await wrapper.find("[data-test='open']").trigger("click");
    await flushPromises();
    await wrapper.find("[data-game='1']").trigger("click");
    await flushPromises();
    expect(wrapper.find("[data-test='ctrl-next']").attributes("disabled")).toBeUndefined();
    await wrapper.find("[data-test='ctrl-next']").trigger("click");
    const pieces = wrapper.findComponent(ChessBoard).props("position").pieces;
    expect(pieces.find((p) => p.x === 0 && p.y === 1)).toBeTruthy();
  });

  it("点设置显示设置弹窗", async () => {
    const wrapper = mount(MobileHomeView);
    await wrapper.find("[data-test='settings']").trigger("click");
    expect(wrapper.find("[data-test='settings-card']").exists()).toBe(true);
  });

  it("打谱中应用编辑后退出打谱", async () => {
    api.listGames.mockResolvedValueOnce({
      items: [
        {
          id: 1,
          name: "测试局",
          initial_fen: INITIAL_FEN,
          moves: [{ x1: 0, y1: 0, x2: 0, y2: 1 }],
        },
      ],
    });
    const wrapper = mount(MobileHomeView);
    await wrapper.find("[data-test='open']").trigger("click");
    await flushPromises();
    await wrapper.find("[data-game='1']").trigger("click");
    await flushPromises();
    await wrapper.find("[data-test='ctrl-edit']").trigger("click");
    await wrapper.findComponent(MobileBoardEditor).vm.$emit("apply", []);
    await flushPromises();
    expect(wrapper.find("[data-test='ctrl-next']").attributes("disabled")).toBeDefined();
  });
```

**Step 2: 运行确认失败。**

**Step 3: 实现** — 重写 `MobileHomeView.vue`：

```vue
<template>
  <section class="mobile-home">
    <div class="mobile-home__bar">
      <button type="button" data-test="open" @click="pickerOpen = true">打开</button>
      <button type="button" data-test="settings" @click="settingsOpen = true">设置</button>
    </div>
    <div class="mobile-home__board">
      <ChessBoard :position="position" :flipped="flipped" />
    </div>
    <BoardControls
      :flipped="flipped"
      :can-start="canBack"
      :can-prev="canBack"
      :can-next="canForward"
      :can-end="canForward"
      :can-edit="true"
      @start="ply = 0"
      @prev="ply -= 1"
      @next="ply += 1"
      @end="ply = moves.length"
      @flip="flipped = !flipped"
      @edit="editorOpen = true"
    />
    <div class="mobile-home__body">
      <h1 class="mobile-home__title">移动端界面</h1>
      <p class="mobile-home__hint">骨架已就绪，后续在此实现移动端页面。</p>
    </div>
    <MobileBoardEditor
      v-if="editorOpen"
      :pieces="pieces"
      @cancel="editorOpen = false"
      @apply="onApply"
    />
    <MobileGamePicker
      v-if="pickerOpen"
      @select="onOpenGame"
      @cancel="pickerOpen = false"
    />
    <div
      v-if="settingsOpen"
      class="settings-mask"
      data-test="settings-mask"
      @click.self="settingsOpen = false"
    >
      <div class="settings-card" data-test="settings-card">
        <h3 class="settings-title">设置</h3>
        <div class="settings-actions">
          <button type="button" data-test="settings-close" @click="settingsOpen = false">
            关闭
          </button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, ref } from "vue";
import ChessBoard from "../../components/ChessBoard.vue";
import BoardControls from "../components/BoardControls.vue";
import MobileBoardEditor from "../components/MobileBoardEditor.vue";
import MobileGamePicker from "../components/MobileGamePicker.vue";
import { INITIAL_FEN, applyMove, fenToPieces } from "../../utils/chess";

const flipped = ref(false);
const basePieces = ref(fenToPieces(INITIAL_FEN));
const moves = ref([]);
const ply = ref(0);
const editorOpen = ref(false);
const pickerOpen = ref(false);
const settingsOpen = ref(false);

const pieces = computed(() => {
  let out = basePieces.value;
  for (const move of moves.value.slice(0, ply.value)) out = applyMove(out, move);
  return out;
});
const position = computed(() => ({ pieces: pieces.value }));

const canBack = computed(() => ply.value > 0);
const canForward = computed(() => ply.value < moves.value.length);

function onOpenGame(game) {
  basePieces.value = fenToPieces(game.initial_fen || INITIAL_FEN);
  moves.value = game.moves || [];
  ply.value = 0;
  pickerOpen.value = false;
}

function onApply(next) {
  basePieces.value = next;
  moves.value = [];
  ply.value = 0;
  editorOpen.value = false;
}
</script>
```

样式在原有基础上追加：

```css
.mobile-home__bar {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.mobile-home__bar button {
  min-height: 36px;
  padding: 6px 16px;
  border: 1px solid #cbb89a;
  border-radius: 6px;
  background: #fff;
  color: #7a3b2e;
  cursor: pointer;
}

.settings-mask {
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

.settings-card {
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

.settings-title {
  margin: 0;
}

.settings-actions {
  display: flex;
}

.settings-actions button {
  flex: 1;
  min-height: 44px;
  border: 1px solid #cbb89a;
  border-radius: 6px;
  background: #fff;
  color: #7a3b2e;
  cursor: pointer;
}
```

**Step 4: 运行确认通过。**

---

### Task 3: 全量回归 + 构建

Run: `npm test`（workdir `frontend`）→ 全部通过；`npm run build` → 成功。
