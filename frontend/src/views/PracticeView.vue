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
        <ChessBoard :position="{ pieces }" />
        <div class="side">
          <p class="ply-info">当前第 {{ ply }} / {{ game.moves.length }} 步</p>
          <div class="controls">
            <button data-test="first" @click="go(0)">|&lt;</button>
            <button data-test="prev" @click="go(ply - 1)">&lt;</button>
            <button data-test="next" @click="go(ply + 1)">&gt;</button>
            <button data-test="last" @click="go(game.moves.length)">&gt;|</button>
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
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import ChessBoard from "../components/ChessBoard.vue";
import { api } from "../api";
import { applyMove, fenToPieces } from "../utils/chess";

const route = useRoute();
const game = ref(null);
const loading = ref(true);
const error = ref(false);
const ply = ref(0);

const pieces = computed(() => {
  if (!game.value) return [];
  let board = fenToPieces(game.value.initial_fen);
  for (const move of game.value.moves.slice(0, ply.value)) board = applyMove(board, move);
  return board;
});

function describe(move, index) {
  return `${index + 1}. (${move.x1},${move.y1})→(${move.x2},${move.y2})`;
}

function go(target) {
  if (!game.value) return;
  ply.value = Math.max(0, Math.min(target, game.value.moves.length));
}

async function load() {
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
}

onMounted(load);
</script>

<style scoped>
.layout {
  display: grid;
  grid-template-columns: 1fr;
  gap: 16px;
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
  font-size: 16px;
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

@media (min-width: 768px) {
  .layout {
    grid-template-columns: 528px 1fr;
    gap: 24px;
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
}
</style>
