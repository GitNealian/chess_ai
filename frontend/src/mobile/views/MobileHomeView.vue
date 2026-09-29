<template>
  <section class="mobile-home">
    <div class="mobile-home__board">
      <ChessBoard
        :position="position"
        :selected="selected"
        :last-move="lastInfo"
        :arrows="reciteMode ? [] : analysisArrows"
        :flipped="flipped"
        @cell-click="onCellClick"
      />
    </div>
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
      @reveal="revealAnswer"
      @exit-recite="exitRecite"
    />
    <p v-if="hint" class="mobile-home__hint" data-test="hint">{{ hint }}</p>
    <MobileAnalysis
      v-if="!reciteMode"
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
    <MobileScanDialog
      v-if="scanOpen"
      @cancel="scanOpen = false"
      @apply="onApply"
    />
    <MobileInferenceDialog
      v-if="inferOpen"
      :initial-fen="initialFen"
      :base-moves="moveSlice"
      @close="inferOpen = false"
    />
    <MobileGamePicker v-if="pickerOpen" @select="onOpenGame" @cancel="pickerOpen = false" />
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
        <div class="settings-group">
          <span class="settings-label">执子</span>
          <label class="settings-radio">
            <input
              type="radio"
              name="engine-side"
              data-test="engine-none"
              :checked="engineSide === 'none'"
              @change="onEngineSide('none')"
            />
            不启用
          </label>
          <label class="settings-radio">
            <input
              type="radio"
              name="engine-side"
              data-test="engine-red"
              :checked="engineSide === 'red'"
              @change="onEngineSide('red')"
            />
            执红
          </label>
          <label class="settings-radio">
            <input
              type="radio"
              name="engine-side"
              data-test="engine-black"
              :checked="engineSide === 'black'"
              @change="onEngineSide('black')"
            />
            执黑
          </label>
        </div>
        <div class="settings-group">
          <span class="settings-label">思考程度</span>
          <label class="settings-radio">
            <input
              type="radio"
              name="level"
              data-test="level-easy"
              :checked="settings.level === 'easy'"
              @change="onLevel('easy')"
            />
            简单
          </label>
          <label class="settings-radio">
            <input
              type="radio"
              name="level"
              data-test="level-normal"
              :checked="settings.level === 'normal'"
              @change="onLevel('normal')"
            />
            普通
          </label>
          <label class="settings-radio">
            <input
              type="radio"
              name="level"
              data-test="level-hard"
              :checked="settings.level === 'hard'"
              @change="onLevel('hard')"
            />
            困难
          </label>
        </div>
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
import MobileScanDialog from "../components/MobileScanDialog.vue";
import MobileGamePicker from "../components/MobileGamePicker.vue";
import MobileAnalysis from "../components/MobileAnalysis.vue";
import MobileInferenceDialog from "../components/MobileInferenceDialog.vue";
import { api } from "../../api";
import { loadSettings, saveSettings } from "../settings";
import { INITIAL_FEN, applyMove, fenToPieces } from "../../utils/chess";

const flipped = ref(false);
const basePieces = ref(fenToPieces(INITIAL_FEN));
const moves = ref([]);
const ply = ref(0);
const editorOpen = ref(false);
const scanOpen = ref(false);
const pickerOpen = ref(false);
const settingsOpen = ref(false);
const currentGame = ref(null);
const favorited = ref(false);
const settings = reactive(loadSettings());
const initialFen = ref(INITIAL_FEN);
const analysisArrows = ref([]);
const inferOpen = ref(false);
const reciteMode = ref(false);
const reciteConfirmOpen = ref(false);
const reciteMistakes = ref(0);
const reciteRevealed = ref(false);
const reciteStartedAt = ref(0);
const navSource = ref(null);
const COLLECTION_PREFIX = "古谱 · ";

const engineSide = ref("none");
const selected = ref(null);
const engineThinking = ref(false);
const hint = ref("");
let pending = false;
let moveToken = 0;
let engineToken = 0;

function sideFromFen(fen) {
  return fen.split(" ")[1] === "b" ? "black" : "red";
}
const isReview = computed(() => !!currentGame.value);
const firstSide = computed(() => sideFromFen(initialFen.value));
function sideAt(n) {
  return n % 2 === 0 ? firstSide.value : firstSide.value === "red" ? "black" : "red";
}

const pieces = computed(() => {
  let out = basePieces.value;
  for (const move of moves.value.slice(0, ply.value)) out = applyMove(out, move);
  return out;
});
const position = computed(() => ({ pieces: pieces.value }));

const canBack = computed(() => ply.value > 0);
const canForward = computed(() => ply.value < moves.value.length);
const moveSlice = computed(() => moves.value.slice(0, ply.value));

const reciteMeta = computed(() => {
  const game = currentGame.value || {};
  const players = [game.red_player, game.black_player].filter(Boolean).join(" vs ");
  const event = game.event && game.event !== "NA" ? game.event : "";
  return [players, event, game.result, game.category].filter(Boolean).join(" · ");
});

const showNav = computed(() => !!currentGame.value && !!navSource.value);

const sideToMove = computed(() => sideAt(ply.value));
const lastInfo = computed(() => moves.value[ply.value - 1] || null);
const gameOver = computed(() => lastInfo.value?.gameOver || null);
const isEngineTurn = computed(
  () => engineSide.value !== "none" && sideToMove.value === engineSide.value
);

function movePayload() {
  return moves.value
    .slice(0, ply.value)
    .map(({ x1, y1, x2, y2 }) => ({ x1, y1, x2, y2 }));
}

function maybeEngineMove() {
  if (engineSide.value === "none") return;
  if (ply.value !== moves.value.length || gameOver.value || engineThinking.value) return;
  if (sideToMove.value === engineSide.value) runEngineMove();
}

async function runEngineMove() {
  if (engineThinking.value || gameOver.value) return;
  engineThinking.value = true;
  hint.value = "";
  const token = ++engineToken;
  try {
    const data = await api.bestMove(
      { initial_fen: initialFen.value, moves: movePayload(), level: settings.level },
      { timeout: 15000 }
    );
    if (token !== engineToken) return;
    if (data.legal) {
      moves.value = moves.value.slice(0, ply.value);
      moves.value.push({
        ...data.move,
        check: Boolean(data.check),
        gameOver: data.game_over || null,
      });
      ply.value = moves.value.length;
    } else {
      hint.value = data.reason || "引擎未能走子";
    }
  } catch (err) {
    if (token !== engineToken) return;
    hint.value =
      err?.code === "ECONNABORTED"
        ? "引擎思考超时，请重试"
        : err?.response?.data?.detail || "引擎走子失败";
  } finally {
    if (token === engineToken) engineThinking.value = false;
  }
}

async function submitMove(move) {
  hint.value = "";
  pending = true;
  const token = ++moveToken;
  try {
    const data = await api.validateMove({
      initial_fen: initialFen.value,
      moves: movePayload(),
      move,
    });
    if (token !== moveToken) return;
    if (!data.legal) {
      hint.value = data.reason || "着法不合法";
      return;
    }
    moves.value = moves.value.slice(0, ply.value);
    moves.value.push({
      ...move,
      chinese: data.chinese || "",
      check: Boolean(data.check),
      gameOver: data.game_over || null,
    });
    ply.value = moves.value.length;
    selected.value = null;
  } catch (err) {
    if (token !== moveToken) return;
    hint.value =
      err?.response?.data?.detail || err?.response?.data?.error || "校验失败，请重试";
  } finally {
    if (token === moveToken) pending = false;
  }
  if (token === moveToken) maybeEngineMove();
}

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
    advanceRecite();
  } catch (err) {
    if (token !== moveToken) return;
    hint.value =
      err?.response?.data?.error || err?.response?.data?.detail || "校验失败，请重试";
  } finally {
    if (token === moveToken) pending = false;
  }
}

function advanceRecite() {
  ply.value += 1;
  selected.value = null;
  if (ply.value >= moves.value.length) finishRecite();
}

function revealAnswer() {
  if (!reciteMode.value || ply.value >= moves.value.length) return;
  if (pending) return;
  reciteRevealed.value = true;
  hint.value = "已看答案";
  advanceRecite();
}

function finishRecite() {
  const game = currentGame.value;
  const duration = Math.max(0, Date.now() - reciteStartedAt.value);
  const mistakeCount = reciteMistakes.value;
  const revealed = reciteRevealed.value;
  reciteMode.value = false;
  reciteMistakes.value = 0;
  reciteRevealed.value = 0;
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

function onEngineSide(value) {
  if (reciteMode.value) return;
  engineSide.value = value;
  engineToken += 1;
  moveToken += 1;
  engineThinking.value = false;
  pending = false;
  selected.value = null;
  hint.value = "";
  if (value !== "none") {
    moves.value = moves.value.slice(0, ply.value);
    maybeEngineMove();
  }
}

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
  const start = fromStart ? 0 : ply.value;
  ply.value = start;
  reciteMistakes.value = 0;
  reciteRevealed.value = false;
  reciteStartedAt.value = Date.now();
  reciteMode.value = true;
  reciteConfirmOpen.value = false;
  selected.value = null;
  hint.value = "";
  analysisArrows.value = [];
  pending = false;
  moveToken += 1;
  engineToken += 1;
  engineThinking.value = false;
}

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

function publishFavoriteState() {
  window.dispatchEvent(
    new CustomEvent("mobile-favorite-state", {
      detail: { shown: !!currentGame.value, filled: !!favorited.value },
    })
  );
}

async function toggleFavorite() {
  if (!currentGame.value) return;
  try {
    const res = await api.favoriteGame(currentGame.value.id);
    favorited.value = !!res.favorited;
    publishFavoriteState();
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
  scanOpen.value = false;
  currentGame.value = null;
  favorited.value = false;
  navSource.value = null;
  reciteMode.value = false;
  reciteConfirmOpen.value = false;
  reciteMistakes.value = 0;
  reciteRevealed.value = false;
  reciteStartedAt.value = 0;
  publishFavoriteState();
  engineToken += 1;
  moveToken += 1;
  engineThinking.value = false;
  selected.value = null;
  hint.value = "";
  maybeEngineMove();
}

function onToggle(key, value) {
  settings[key] = value;
  saveSettings(settings);
}

function onLevel(value) {
  settings.level = value;
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
  window.addEventListener("mobile-toggle-favorite", toggleFavorite);
});

onUnmounted(() => {
  window.removeEventListener("mobile-open", onOpenEvent);
  window.removeEventListener("mobile-settings", onSettingsEvent);
  window.removeEventListener("mobile-toggle-favorite", toggleFavorite);
});
</script>

<style scoped>
.mobile-home {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.mobile-home__board {
  width: 100%;
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 2px 8px rgba(90, 61, 36, 0.18);
}

.mobile-home__hint {
  margin: 0;
  color: #b45309;
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
  max-height: calc(100vh - 32px);
  margin: auto;
  background: #faf6ee;
  border-radius: 12px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow-y: auto;
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

.settings-group {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 16px;
  font-size: 15px;
}

.settings-label {
  width: 100%;
  color: #6b5a45;
  font-size: 13px;
}

.settings-radio {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.settings-radio input[type="radio"] {
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

.recite-meta {
  margin: 0;
  color: #6b5a45;
  font-size: 13px;
}

.recite-range {
  margin: 0;
  color: #7a3b2e;
}
</style>
