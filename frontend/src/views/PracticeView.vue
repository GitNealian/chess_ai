<template>
  <section v-if="game" class="practice">
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

onMounted(async () => {
  try {
    game.value = await api.getGame(route.params.id);
  } catch (error) {
    // api 拦截器已 toast，无需额外处理
  }
});
</script>

<style scoped>
.layout {
  display: grid;
  grid-template-columns: 528px 1fr;
  gap: 24px;
}

.controls {
  display: flex;
  gap: 8px;
  margin: 10px 0;
}

.moves {
  max-height: 420px;
  overflow: auto;
  cursor: pointer;
}

.moves .active {
  background: #f0d9a8;
}
</style>
