<template>
  <section class="play">
    <h2>人人对弈</h2>
    <p v-if="loading" class="hint">加载中…</p>
    <div v-else-if="error" class="hint">
      <p>加载失败</p>
      <button data-test="retry" @click="load">重试</button>
    </div>
    <div v-else class="layout">
      <ChessBoard
        :position="{ pieces: editing ? editPieces : session.state.pieces }"
        :selected="editing ? null : session.state.selected"
        :arrows="editing ? [] : arrows"
        :flipped="flipped"
        @cell-click="onCellClick"
      />
      <div class="side">
        <p v-if="!session.state.gameOver" class="turn" data-test="turn">{{ turnText }}</p>
        <p v-if="session.state.hint" class="warn" data-test="hint">{{ session.state.hint }}</p>
        <p v-if="session.state.gameOver" class="result" data-test="game-over">
          {{ resultText }}
          <span class="result-hint">如需续下可点悔棋</span>
        </p>
        <div class="controls">
          <button data-test="undo" :disabled="undoDisabled" @click="undo">悔棋</button>
          <button data-test="flip" :disabled="engineThinking" @click="flipped = !flipped">翻转棋盘</button>
          <button data-test="save" :disabled="engineThinking || editing" @click="openSave">保存到棋谱库</button>
        </div>
        <div class="ai-controls">
          <label class="level-label">
            难度
            <select v-model="level" data-test="level" :disabled="engineThinking || editing">
              <option v-for="l in LEVELS" :key="l.value" :value="l.value">{{ l.label }}</option>
            </select>
          </label>
          <button data-test="engine-red" :disabled="engineThinking" @click="enterAi('red')">引擎执红</button>
          <button data-test="engine-black" :disabled="engineThinking" @click="enterAi('black')">引擎执黑</button>
          <button data-test="edit" :disabled="engineThinking || editing" @click="enterEdit">编辑局面</button>
        </div>
        <p v-if="engineThinking" class="warn" data-test="engine-thinking">引擎思考中…</p>
        <div v-if="editing" class="editor-panel" data-test="editor-panel">
          <PiecePalette
            :selected="palette"
            @select="onPaletteSelect"
            @clear="editPieces = []"
            @initial="loadInitialEdit"
          />
          <label class="level-label">
            行棋方
            <select v-model="editSide" data-test="edit-side">
              <option value="red">红先</option>
              <option value="black">黑先</option>
            </select>
          </label>
          <p v-for="(err, i) in editError" :key="i" class="warn" data-test="edit-error">
            {{ err }}
          </p>
          <div class="modal-actions">
            <button data-test="edit-cancel" @click="cancelEdit">取消</button>
            <button data-test="edit-apply" :disabled="applying" @click="applyPosition">应用局面</button>
          </div>
        </div>
        <IntentPanel v-if="intent.status !== 'idle'" :intent="intent" />
        <div class="analysis" data-test="analysis">
          <div class="score-row">
            <span class="score-text" data-test="score">{{ scoreText }}</span>
            <div v-if="analysis.scoreRed !== null" class="score-bar">
              <div class="score-bar-fill" :style="{ width: barWidth + '%' }"></div>
            </div>
          </div>
          <p class="analysis-status" data-test="analysis-status">{{ statusText }}</p>
          <ol v-if="analysis.results.length" class="analysis-history">
            <li v-for="r in analysis.results" :key="r.depth" data-test="analysis-item">
              <span class="depth">第 {{ r.depth }} 层</span>
              <span class="score">{{ formatScore(r.score_red, r.mate) }}</span>
              <span class="line">{{ pvText(r) }}</span>
              <span class="time">{{ r.time_ms }}ms</span>
            </li>
          </ol>
        </div>
        <ol v-if="session.state.moves.length" class="moves" data-test="move-list">
          <li v-for="(move, index) in session.state.moves" :key="index">
            {{ describe(move, index) }}
          </li>
        </ol>
      </div>
    </div>
    <div v-if="showSave" class="modal" data-test="save-modal">
      <form class="save-form" @submit.prevent="save">
        <h3>保存到棋谱库</h3>
        <label>名称<input v-model="form.name" data-test="save-name" /></label>
        <label>红方<input v-model="form.red_player" /></label>
        <label>黑方<input v-model="form.black_player" /></label>
        <label>赛事<input v-model="form.event" /></label>
        <label>分类<input v-model="form.category" /></label>
        <label>
          结果
          <select v-model="form.result" data-test="save-result">
            <option value="*">未结束</option>
            <option value="1-0">红胜</option>
            <option value="0-1">黑胜</option>
            <option value="1/2-1/2">和棋</option>
          </select>
        </label>
        <p v-if="saveError" class="warn" data-test="save-error">{{ saveError }}</p>
        <div class="modal-actions">
          <button type="button" data-test="cancel" :disabled="saving" @click="showSave = false">取消</button>
          <button type="submit" data-test="save-submit" :disabled="saving">保存</button>
        </div>
      </form>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import ChessBoard from "../components/ChessBoard.vue";
import IntentPanel from "../components/IntentPanel.vue";
import PiecePalette from "../components/PiecePalette.vue";
import { analyzeStream, api, intentStream } from "../api";
import { createPlaySession } from "../stores/play";
import { INITIAL_FEN, LABELS, fenToPieces } from "../utils/chess";

const route = useRoute();
const router = useRouter();
const loading = ref(true);
const error = ref(false);
const flipped = ref(false);
const session = createPlaySession({});
let disposed = false;

function emptyAnalysis(status) {
  return {
    status,
    results: [],
    scoreRed: null,
    mate: null,
    best: null,
    reply: null,
    error: "",
  };
}

const analysis = ref(emptyAnalysis("idle"));
let controller = null;
let requestToken = 0;

function emptyIntent(status) {
  return { status, rank: null, threat: null, baits: [], error: "" };
}

const intent = ref(emptyIntent("idle"));
let intentController = null;
let intentToken = 0;

const LEVELS = [
  { value: "easy", label: "简单" },
  { value: "normal", label: "普通" },
  { value: "hard", label: "困难" },
];

const mode = ref("human");
const engineSide = ref(null);
const level = ref("normal");
const engineThinking = ref(false);

const editing = ref(false);
const editPieces = ref([]);
const palette = ref(null);
const editSide = ref("red");
const editError = ref([]);
const applying = ref(false);
let editPrev = null;
let editToken = 0;

const arrows = computed(() => {
  const out = [];
  const a = analysis.value;
  if (a.best) out.push({ ...a.best, kind: "best" });
  if (a.reply) out.push({ ...a.reply, kind: "reply" });
  return out;
});

function formatScore(scoreRed, mate) {
  if (scoreRed === null || scoreRed === undefined) return "";
  if (mate !== null && mate !== undefined) {
    const side = scoreRed >= 0 ? "红方" : "黑方";
    return `${side} ${Math.abs(mate)} 步杀`;
  }
  if (Math.abs(scoreRed) < 1) return "均势";
  const value = Math.abs(scoreRed);
  return scoreRed > 0 ? `红优 +${value}` : `黑优 ${value}`;
}

const scoreText = computed(() => formatScore(analysis.value.scoreRed, analysis.value.mate));

const barWidth = computed(() => {
  const score = analysis.value.scoreRed;
  if (score === null) return 50;
  const clamped = Math.max(-1000, Math.min(1000, score));
  return 50 + clamped / 20;
});

const statusText = computed(() => {
  const a = analysis.value;
  if (a.status === "running") return "分析中…";
  if (a.status === "done") return "已完成";
  if (a.status === "error") return `分析失败：${a.error}`;
  return "";
});

function pvText(r) {
  return (r.pv || []).map((p) => p.chinese || p.iccs).join(" → ");
}

function stopAnalysis() {
  requestToken += 1;
  if (controller) {
    controller.abort();
    controller = null;
  }
}

function startAnalysis() {
  stopAnalysis();
  const token = requestToken;
  analysis.value = emptyAnalysis("running");
  controller = new AbortController();
  analyzeStream(
    {
      initial_fen: session.state.initialFen,
      moves: movePayload(),
    },
    {
      signal: controller.signal,
      onResult: (r) => {
        if (token !== requestToken) return;
        const current = analysis.value;
        current.results.unshift(r);
        current.scoreRed = r.score_red ?? null;
        current.mate = r.mate ?? null;
        current.best = r.pv?.[0] ?? null;
        current.reply = r.pv?.[1] ?? null;
      },
      onDone: () => {
        if (token === requestToken) analysis.value.status = "done";
      },
      onError: (e) => {
        if (token !== requestToken) return;
        analysis.value.status = "error";
        analysis.value.error = e?.message || "未知错误";
      },
    }
  );
}

function stopIntent() {
  intentToken += 1;
  if (intentController) {
    intentController.abort();
    intentController = null;
  }
}

function startIntent() {
  stopAnalysis();
  analysis.value = emptyAnalysis("idle");
  stopIntent();
  const token = intentToken;
  intent.value = emptyIntent("running");
  intentController = new AbortController();
  intentStream(
    {
      initial_fen: session.state.initialFen,
      moves: movePayload(),
    },
    {
      signal: intentController.signal,
      onRank: (r) => {
        if (token !== intentToken) return;
        intent.value.rank = r;
      },
      onThreat: (r) => {
        if (token !== intentToken) return;
        intent.value.threat = r;
      },
      onBait: (r) => {
        if (token !== intentToken) return;
        intent.value.baits.push(r);
      },
      onDone: () => {
        if (token !== intentToken) return;
        intent.value.status = "done";
        startAnalysis();
      },
      onError: (e) => {
        if (token !== intentToken) return;
        intent.value.status = "error";
        intent.value.error = e?.message || "";
        startAnalysis();
      },
    }
  );
}

const turnText = computed(() => {
  if (session.state.gameOver) return "";
  const side = session.state.sideToMove === "red" ? "红方" : "黑方";
  return session.state.check ? `${side}走棋（被将军）` : `${side}走棋`;
});

const RESULT_REASONS = { checkmate: "绝杀", stalemate: "困毙" };

const resultText = computed(() => {
  const over = session.state.gameOver;
  if (!over) return "";
  const winner = over.winner === "red" ? "红方" : "黑方";
  return `${winner}胜（${RESULT_REASONS[over.reason] || "终局"}）`;
});

function describe(move, index) {
  const text = move.chinese || `(${move.x1},${move.y1})→(${move.x2},${move.y2})`;
  return `${index + 1}. ${text}`;
}

function isEngineTurn() {
  return (
    mode.value === "ai" &&
    !session.state.gameOver &&
    session.state.sideToMove === engineSide.value
  );
}

async function onCellClick(x, y) {
  if (editing.value) return onEditClick(x, y);
  if (engineThinking.value) return;
  if (isEngineTurn()) {
    // 引擎回合未在思考（如上次请求失败）时，点棋盘即重试引擎走子
    await runEngineMove();
    return;
  }
  if (await session.click(x, y)) {
    if (isEngineTurn()) await runEngineMove();
    else startIntent();
  }
}

let engineController = null;
let engineToken = 0;

function stopEngine() {
  engineToken += 1;
  if (engineController) {
    engineController.abort();
    engineController = null;
  }
}

function isCancel(err) {
  return (
    err?.name === "CanceledError" ||
    err?.code === "ERR_CANCELED" ||
    err?.name === "AbortError"
  );
}

function movePayload() {
  return session.state.moves.map(({ chinese, check, gameOver, ...rest }) => rest);
}

async function runEngineMove() {
  if (engineThinking.value || session.state.gameOver) return;
  engineThinking.value = true;
  stopIntent();
  stopAnalysis();
  stopEngine();
  const token = engineToken;
  analysis.value = emptyAnalysis("idle");
  intent.value = emptyIntent("idle");
  engineController = new AbortController();
  try {
    const data = await api.bestMove(
      {
        initial_fen: session.state.initialFen,
        moves: movePayload(),
        level: level.value,
      },
      { signal: engineController.signal, timeout: 15000 }
    );
    if (disposed || token !== engineToken) return;
    if (data.legal) {
      session.applyEngineMove({
        ...data.move,
        check: data.check,
        game_over: data.game_over,
      });
    } else {
      session.state.hint = data.reason || "引擎未能走子";
    }
  } catch (err) {
    if (isCancel(err)) return;
    if (!disposed && token === engineToken) {
      session.state.hint =
        err?.code === "ECONNABORTED"
          ? "引擎思考超时，请重试"
          : err?.response?.data?.detail || "引擎走子失败";
    }
  } finally {
    if (token === engineToken) {
      engineController = null;
      engineThinking.value = false;
    }
  }
  if (disposed || token !== engineToken) return;
  if (!session.state.gameOver) startIntent();
}

async function enterAi(side) {
  if (
    (session.state.moves.length || editing.value) &&
    !window.confirm("将清空当前对局与编辑内容，确定开始人机对战？")
  ) {
    return;
  }
  stopIntent();
  stopAnalysis();
  stopEngine();
  editing.value = false;
  palette.value = null;
  editError.value = [];
  editPrev = null;
  engineThinking.value = false;
  mode.value = "ai";
  engineSide.value = side;
  flipped.value = side === "red";
  session.reset({});
  if (side === "red") await runEngineMove();
  else startIntent();
}

function enterEdit() {
  if (
    session.state.moves.length &&
    !window.confirm("进入编辑后应用局面将替换当前对局，确定继续？")
  ) {
    return;
  }
  stopIntent();
  stopAnalysis();
  stopEngine();
  analysis.value = emptyAnalysis("idle");
  intent.value = emptyIntent("idle");
  editPrev = {
    mode: mode.value,
    engineSide: engineSide.value,
  };
  editToken += 1;
  mode.value = "human";
  engineSide.value = null;
  engineThinking.value = false;
  editPieces.value = session.state.pieces.map((p) => ({ ...p }));
  palette.value = null;
  editError.value = [];
  editSide.value = session.state.sideToMove;
  editing.value = true;
}

function cancelEdit() {
  editToken += 1;
  editing.value = false;
  applying.value = false;
  palette.value = null;
  editError.value = [];
  if (editPrev) {
    mode.value = editPrev.mode;
    engineSide.value = editPrev.engineSide;
    editPrev = null;
  }
  startIntent();
}

function onPaletteSelect(piece) {
  if (
    palette.value &&
    palette.value.side === piece.side &&
    palette.value.kind === piece.kind
  ) {
    palette.value = null;
  } else {
    palette.value = piece;
  }
}

function onEditClick(x, y) {
  const target = editPieces.value.find((p) => p.x === x && p.y === y);
  if (target) {
    editPieces.value = editPieces.value.filter((p) => !(p.x === x && p.y === y));
    return;
  }
  if (!palette.value) return;
  const { side, kind } = palette.value;
  editPieces.value = [
    ...editPieces.value,
    { x, y, side, kind, label: LABELS[`${side}-${kind}`] },
  ];
}

function loadInitialEdit() {
  editPieces.value = fenToPieces(INITIAL_FEN);
  palette.value = null;
}

async function applyPosition() {
  if (applying.value) return;
  applying.value = true;
  editError.value = [];
  const token = editToken;
  try {
    const data = await api.validatePosition(
      {
        pieces: editPieces.value.map(({ x, y, side, kind }) => ({ x, y, side, kind })),
        side_to_move: editSide.value,
      },
      { timeout: 15000 }
    );
    if (disposed || token !== editToken) return;
    if (!data.valid) {
      editError.value = data.errors || ["局面不合法"];
      return;
    }
    editing.value = false;
    palette.value = null;
    editPrev = null;
    flipped.value = false;
    session.reset({ initial_fen: data.fen });
    startIntent();
  } catch (err) {
    editError.value = [
      err?.response?.data?.detail || err?.response?.data?.error || "校验失败，请重试",
    ];
  } finally {
    applying.value = false;
  }
}

function undo() {
  if (!session.state.moves.length) return;
  stopEngine();
  engineThinking.value = false;
  session.undo();
  // AI 模式：撤销到玩家回合（连带撤销引擎刚走的一步），不自动补走
  while (session.state.moves.length && isEngineTurn()) session.undo();
  startIntent();
}

const undoDisabled = computed(() => {
  if (engineThinking.value || editing.value || !session.state.moves.length) return true;
  // 引擎执红时至少保留引擎首着，避免撤到空局面后轮到引擎无法继续
  return (
    mode.value === "ai" && engineSide.value === "red" && session.state.moves.length <= 1
  );
});

const showSave = ref(false);
const saving = ref(false);
const saveError = ref("");
const form = reactive({
  name: "红方 vs 黑方",
  red_player: "",
  black_player: "",
  event: "",
  category: "对弈",
  result: "*",
});

function openSave() {
  form.result = session.state.gameOver
    ? session.state.gameOver.winner === "red"
      ? "1-0"
      : "0-1"
    : "*";
  saveError.value = "";
  showSave.value = true;
}

async function save() {
  if (saving.value) return;
  saving.value = true;
  saveError.value = "";
  try {
    const name = form.name.trim();
    const created = await api.createGame({
      name: name || "红方 vs 黑方",
      red_player: form.red_player,
      black_player: form.black_player,
      event: form.event,
      category: form.category,
      result: form.result,
      initial_fen: session.state.initialFen,
      moves: session.state.moves.map(({ x1, y1, x2, y2 }) => ({ x1, y1, x2, y2 })),
      practice_side: "both",
    });
    if (disposed) return;
    showSave.value = false;
    router.push(`/practice/${created.id}`);
  } catch (err) {
    saveError.value = err?.response?.data?.error || "保存失败";
  } finally {
    saving.value = false;
  }
}

async function probePositionState(game, ply) {
  try {
    const data = await api.validateMove({
      initial_fen: game.initial_fen,
      moves: game.moves.slice(0, ply - 1),
      move: game.moves[ply - 1],
    });
    if (data.legal) {
      session.applyState({ check: data.check, gameOver: data.game_over || null });
    }
  } catch {
    // 探测失败不阻塞对局，保持未判定状态
  }
}

async function load() {
  stopAnalysis();
  stopIntent();
  analysis.value = emptyAnalysis("idle");
  intent.value = emptyIntent("idle");
  loading.value = true;
  error.value = false;
  try {
    if (route.query.game) {
      const game = await api.getGame(route.query.game);
      if (disposed) return;
      const ply = Math.max(
        0,
        Math.min(Number(route.query.ply) || 0, game.moves.length)
      );
      session.reset({ initial_fen: game.initial_fen, moves: game.moves.slice(0, ply) });
      if (ply > 0) {
        await probePositionState(game, ply);
      }
    } else {
      session.reset({});
    }
  } catch {
    error.value = true;
    loading.value = false;
    return;
  }
  if (disposed) return;
  loading.value = false;
  startIntent();
}

onMounted(load);
onUnmounted(() => {
  disposed = true;
  stopAnalysis();
  stopIntent();
  stopEngine();
});
</script>

<style scoped>
.layout {
  display: grid;
  grid-template-columns: 1fr;
  gap: 16px;
}

.side {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.turn {
  margin: 0;
  font-weight: 600;
}

.warn {
  margin: 0;
  color: #b45309;
}

.result {
  margin: 0;
  font-weight: 600;
  color: #b91c1c;
}

.result-hint {
  margin-left: 6px;
  font-weight: 400;
  font-size: 13px;
  color: #6b5b45;
}

.controls {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.controls button {
  flex: 1 1 0;
  min-height: 44px;
}

.ai-controls {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.ai-controls button {
  flex: 1 1 0;
  min-height: 44px;
}

.level-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
}

.level-label select {
  min-height: 40px;
}

.editor-panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
  background: #faf6ee;
  border: 1px solid #e6ddcc;
  border-radius: 10px;
  padding: 12px;
}

.analysis {
  background: #faf6ee;
  border: 1px solid #e6ddcc;
  border-radius: 10px;
  padding: 12px;
}

.score-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.score-text {
  font-weight: 600;
  white-space: nowrap;
}

.score-bar {
  flex: 1;
  height: 8px;
  border-radius: 4px;
  background: #e05252;
  overflow: hidden;
}

.score-bar-fill {
  height: 100%;
  border-radius: 4px;
  background: linear-gradient(90deg, #7fb0ff, #2563eb);
  transition: width 0.2s ease;
}

.analysis-status {
  margin: 6px 0 0;
  font-size: 13px;
  color: #6b5b45;
}

.analysis-history {
  list-style: none;
  margin: 8px 0 0;
  padding: 0;
  max-height: 200px;
  overflow: auto;
  -webkit-overflow-scrolling: touch;
  font-size: 13px;
}

.analysis-history li {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 8px;
  min-height: 40px;
  padding: 4px 0;
  border-top: 1px solid #e9dfcd;
}

.analysis-history li:first-child {
  border-top: 0;
}

.analysis-history .depth {
  font-weight: 600;
}

.analysis-history .line {
  flex: 1 1 100%;
  color: #4a3a28;
  word-break: break-all;
}

.analysis-history .time {
  margin-left: auto;
  color: #8a7a63;
}

.moves {
  max-height: 320px;
  overflow: auto;
  -webkit-overflow-scrolling: touch;
  list-style: none;
  padding-left: 0;
  margin: 0;
}

.moves li {
  min-height: 40px;
  display: flex;
  align-items: center;
}

.hint {
  text-align: center;
}

.hint button {
  min-height: 44px;
  padding: 10px 16px;
}

.modal {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding: 16px;
  overflow-y: auto;
}

.save-form {
  width: 100%;
  max-width: 360px;
  margin: auto;
  background: #fff;
  border-radius: 12px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.save-form h3 {
  margin: 0;
}

.save-form label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 14px;
}

.save-form input,
.save-form select {
  min-height: 40px;
  padding: 6px 10px;
  border: 1px solid #cbb89a;
  border-radius: 6px;
  font: inherit;
}

.modal-actions {
  display: flex;
  gap: 8px;
  margin-top: 4px;
}

.modal-actions button {
  flex: 1;
  min-height: 44px;
}

@media (min-width: 768px) {
  .layout {
    grid-template-columns: 528px 1fr;
    gap: 24px;
  }

  .controls button {
    flex: 0 0 auto;
    min-height: 0;
  }

  .analysis-history {
    max-height: 260px;
  }

  .analysis-history li {
    min-height: 0;
  }

  .moves {
    max-height: 420px;
  }

  .moves li {
    min-height: 0;
  }
}
</style>
