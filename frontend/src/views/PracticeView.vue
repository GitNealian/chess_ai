<template>
  <section class="practice">
    <p v-if="loading" class="hint">加载中…</p>
    <div v-else-if="error" class="hint">
      <p>加载失败</p>
      <button data-test="retry" @click="load">重试</button>
    </div>
    <template v-else-if="game">
      <h2>{{ game.name }}</h2>
      <div class="layout">
        <ChessBoard :position="{ pieces }" :arrows="arrows" />
        <div class="side">
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
          <p class="ply-info">当前第 {{ ply }} / {{ game.moves.length }} 步</p>
          <div class="controls">
            <button data-test="first" @click="go(0)">|&lt;</button>
            <button data-test="prev" @click="go(ply - 1)">&lt;</button>
            <button data-test="next" @click="go(ply + 1)">&gt;</button>
            <button data-test="last" @click="go(game.moves.length)">&gt;|</button>
            <button data-test="start-play" @click="startPlay">从此处开始对弈</button>
          </div>
          <ol class="moves">
            <li
              v-for="(move, index) in game.moves"
              :key="index"
              :class="{ active: index === ply - 1 }"
              @click="go(index + 1)"
            >
              {{ describe(move, index) }}
            </li>
          </ol>
        </div>
      </div>
    </template>
  </section>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import ChessBoard from "../components/ChessBoard.vue";
import { analyzeStream, api } from "../api";
import { applyMove, fenToPieces } from "../utils/chess";

const route = useRoute();
const router = useRouter();
const game = ref(null);
const loading = ref(true);
const error = ref(false);
const ply = ref(0);

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

const pieces = computed(() => {
  if (!game.value) return [];
  let board = fenToPieces(game.value.initial_fen);
  for (const move of game.value.moves.slice(0, ply.value)) board = applyMove(board, move);
  return board;
});

function stopAnalysis() {
  requestToken += 1;
  if (controller) {
    controller.abort();
    controller = null;
  }
}

function startAnalysis() {
  stopAnalysis();
  if (!game.value) return;
  const token = requestToken;
  analysis.value = emptyAnalysis("running");
  controller = new AbortController();
  analyzeStream(
    { initial_fen: game.value.initial_fen, moves: game.value.moves, ply: ply.value },
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

function describe(move, index) {
  return `${index + 1}. (${move.x1},${move.y1})→(${move.x2},${move.y2})`;
}

function go(target) {
  if (!game.value) return;
  ply.value = Math.max(0, Math.min(target, game.value.moves.length));
}

function startPlay() {
  if (!game.value) return;
  router.push({ path: "/play", query: { game: game.value.id, ply: ply.value } });
}

async function load() {
  stopAnalysis();
  analysis.value = emptyAnalysis("idle");
  loading.value = true;
  error.value = false;
  try {
    game.value = await api.getGame(route.params.id);
  } catch (err) {
    game.value = null;
    error.value = true;
  } finally {
    loading.value = false;
  }
  if (game.value) startAnalysis();
}

watch(ply, startAnalysis);

onMounted(load);
onUnmounted(stopAnalysis);
</script>

<style scoped>
.layout {
  display: grid;
  grid-template-columns: 1fr;
  gap: 16px;
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

.controls {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 10px 0;
}

.controls button {
  flex: 1 1 0;
  min-height: 44px;
}

.moves {
  max-height: 320px;
  overflow: auto;
  -webkit-overflow-scrolling: touch;
  cursor: pointer;
  list-style: none;
  padding-left: 0;
}

.moves li {
  min-height: 40px;
  display: flex;
  align-items: center;
}

.moves .active {
  background: #f0d9a8;
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

  .analysis-history {
    max-height: 260px;
  }

  .analysis-history li {
    min-height: 0;
  }

  .controls {
    flex-wrap: nowrap;
  }

  .controls button {
    flex: 0 0 auto;
    min-height: 0;
  }

  .moves {
    max-height: 420px;
  }

  .moves li {
    min-height: 0;
    display: list-item;
  }

  .hint button {
    min-height: 0;
    padding: 1px 6px;
  }
}
</style>
