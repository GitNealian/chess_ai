<template>
  <section class="mobile-home">
    <div v-if="currentGame" class="mobile-home__bar">
      <button
        type="button"
        class="mobile-home__fav"
        data-test="favorite"
        :aria-pressed="favorited ? 'true' : 'false'"
        @click="toggleFavorite"
      >
        {{ favorited ? "★" : "☆" }}
      </button>
    </div>
    <div class="mobile-home__board">
      <ChessBoard :position="position" :arrows="analysisArrows" :flipped="flipped" />
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
    <MobileAnalysis
      :initial-fen="initialFen"
      :moves="moveSlice"
      :score="settings.score"
      :intent="settings.intent"
      @arrows="analysisArrows = $event"
    />
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
        <label class="settings-toggle">
          <input
            type="checkbox"
            data-test="setting-score"
            :checked="settings.score"
            @change="onToggle('score', $event.target.checked)"
          />
          开启评分
        </label>
        <label class="settings-toggle">
          <input
            type="checkbox"
            data-test="setting-intent"
            :checked="settings.intent"
            @change="onToggle('intent', $event.target.checked)"
          />
          开启意图识别
        </label>
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
import { computed, onMounted, onUnmounted, reactive, ref } from "vue";
import ChessBoard from "../../components/ChessBoard.vue";
import BoardControls from "../components/BoardControls.vue";
import MobileBoardEditor from "../components/MobileBoardEditor.vue";
import MobileGamePicker from "../components/MobileGamePicker.vue";
import MobileAnalysis from "../components/MobileAnalysis.vue";
import { api } from "../../api";
import { loadSettings, saveSettings } from "../settings";
import { INITIAL_FEN, applyMove, fenToPieces } from "../../utils/chess";

const flipped = ref(false);
const basePieces = ref(fenToPieces(INITIAL_FEN));
const moves = ref([]);
const ply = ref(0);
const editorOpen = ref(false);
const pickerOpen = ref(false);
const settingsOpen = ref(false);
const currentGame = ref(null);
const favorited = ref(false);
const settings = reactive(loadSettings());
const initialFen = ref(INITIAL_FEN);
const analysisArrows = ref([]);

const pieces = computed(() => {
  let out = basePieces.value;
  for (const move of moves.value.slice(0, ply.value)) out = applyMove(out, move);
  return out;
});
const position = computed(() => ({ pieces: pieces.value }));

const canBack = computed(() => ply.value > 0);
const canForward = computed(() => ply.value < moves.value.length);
const moveSlice = computed(() => moves.value.slice(0, ply.value));

function onOpenGame(game) {
  const fen = game.initial_fen || INITIAL_FEN;
  basePieces.value = fenToPieces(fen);
  initialFen.value = fen;
  moves.value = game.moves || [];
  ply.value = 0;
  pickerOpen.value = false;
  currentGame.value = game;
  favorited.value = !!game.favorited;
  api
    .openGame(game.id)
    .then((res) => {
      favorited.value = !!res.favorited;
    })
    .catch(() => {});
}

async function toggleFavorite() {
  if (!currentGame.value) return;
  try {
    const res = await api.favoriteGame(currentGame.value.id);
    favorited.value = !!res.favorited;
  } catch {
    // 收藏失败静默，保持原状态
  }
}

function onApply(next, fen) {
  basePieces.value = fen ? fenToPieces(fen) : next;
  initialFen.value = fen || INITIAL_FEN;
  moves.value = [];
  ply.value = 0;
  editorOpen.value = false;
  currentGame.value = null;
  favorited.value = false;
}

function onToggle(key, value) {
  settings[key] = value;
  saveSettings(settings);
}

function onOpenEvent() {
  pickerOpen.value = true;
}

function onSettingsEvent() {
  settingsOpen.value = true;
}

onMounted(() => {
  window.addEventListener("mobile-open", onOpenEvent);
  window.addEventListener("mobile-settings", onSettingsEvent);
});

onUnmounted(() => {
  window.removeEventListener("mobile-open", onOpenEvent);
  window.removeEventListener("mobile-settings", onSettingsEvent);
});
</script>

<style scoped>
.mobile-home {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.mobile-home__bar {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
}

.mobile-home__fav {
  margin-right: auto;
  border: none;
  background: transparent;
  color: #d4a017;
  font-size: 24px;
  line-height: 1;
  padding: 4px 8px;
  cursor: pointer;
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

.settings-toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 40px;
  font-size: 15px;
}

.settings-toggle input[type="checkbox"] {
  width: 20px;
  height: 20px;
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
