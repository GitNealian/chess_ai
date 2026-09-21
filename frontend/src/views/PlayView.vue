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
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import ChessBoard from "../components/ChessBoard.vue";
import { api } from "../api";
import { createPlaySession } from "../stores/play";

const route = useRoute();
const loading = ref(true);
const error = ref(false);
const flipped = ref(false);
const session = createPlaySession({});

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
  await session.click(x, y);
}

function undo() {
  session.undo();
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
  loading.value = true;
  error.value = false;
  try {
    if (route.query.game) {
      const game = await api.getGame(route.query.game);
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
  loading.value = false;
}

onMounted(load);
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

  .moves {
    max-height: 420px;
  }

  .moves li {
    min-height: 0;
  }
}
</style>
