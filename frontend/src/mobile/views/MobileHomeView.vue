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
    <MobileGamePicker v-if="pickerOpen" @select="onOpenGame" @cancel="pickerOpen = false" />
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

<style scoped>
.mobile-home {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

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

.mobile-home__board {
  width: 100%;
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 2px 8px rgba(90, 61, 36, 0.18);
}

.mobile-home__body {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  text-align: center;
}

.mobile-home__title {
  margin: 0;
  font-size: 20px;
  color: #7a3b2e;
}

.mobile-home__hint {
  margin: 0;
  color: #6b5a45;
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
</style>
