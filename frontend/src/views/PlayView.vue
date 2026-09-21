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
        <p v-if="session.state.gameOver" class="result" data-test="game-over">{{ resultText }}</p>
        <div class="controls">
          <button data-test="undo" :disabled="!session.state.moves.length" @click="undo">悔棋</button>
          <button data-test="flip" @click="flipped = !flipped">翻转棋盘</button>
        </div>
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
  </section>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useRoute } from "vue-router";
import ChessBoard from "../components/ChessBoard.vue";
import { analyzeStream, api } from "../api";
import { createPlaySession } from "../stores/play";

const route = useRoute();
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
  if (await session.click(x, y)) startAnalysis();
}

function undo() {
  if (!session.state.moves.length) return;
  session.undo();
  startAnalysis();
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
  analysis.value = emptyAnalysis("idle");
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
      if (ply > 0 && ply === game.moves.length) {
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
  startAnalysis();
}

onMounted(load);
onUnmounted(() => {
  disposed = true;
  stopAnalysis();
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
