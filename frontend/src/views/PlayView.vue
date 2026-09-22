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
        :position="{ pieces: session.state.pieces }"
        :selected="session.state.selected"
        :arrows="arrows"
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
          <button data-test="undo" :disabled="!session.state.moves.length" @click="undo">悔棋</button>
          <button data-test="flip" @click="flipped = !flipped">翻转棋盘</button>
          <button data-test="save" @click="openSave">保存到棋谱库</button>
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
import { analyzeStream, api, intentStream } from "../api";
import { createPlaySession } from "../stores/play";

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
      moves: session.state.moves.map(({ chinese, check, gameOver, ...rest }) => rest),
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
  stopIntent();
  const token = intentToken;
  intent.value = emptyIntent("running");
  intentController = new AbortController();
  intentStream(
    {
      initial_fen: session.state.initialFen,
      moves: session.state.moves.map(({ chinese, check, gameOver, ...rest }) => rest),
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

async function onCellClick(x, y) {
  if (await session.click(x, y)) startIntent();
}

function undo() {
  if (!session.state.moves.length) return;
  session.undo();
  startIntent();
}

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
