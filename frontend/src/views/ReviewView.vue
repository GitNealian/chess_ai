<template>
  <section class="review">
    <p v-if="loading" class="hint">加载中…</p>
    <p v-else-if="!current" class="hint" data-test="empty">
      今日复习已全部完成 🎉
    </p>
    <template v-else>
      <h2>{{ current.game.name }}</h2>
      <p class="progress" data-test="progress">
        第 {{ index + 1 }} / {{ queue.length }} 个
      </p>
      <div class="layout">
        <ChessBoard :position="{ pieces }" :selected="selected" @cell-click="onCellClick" />
        <div class="side">
          <template v-if="!done">
            <p class="prompt" data-test="prompt">请走出{{ sideText }}的正确着法</p>
            <p v-if="revealed" class="revealed" data-test="revealed-hint">已看答案</p>
            <button data-test="reveal" @click="onReveal">看答案</button>
          </template>
          <template v-else>
            <p class="done" data-test="done">完成！共错 {{ mistakes }} 次</p>
            <p v-if="revealed" class="revealed" data-test="revealed-done">已看答案</p>
            <button data-test="submit" @click="onSubmit">提交并进入下一个</button>
          </template>
          <p class="stat">错误 {{ mistakes }} 次</p>
          <p class="stat">用时 {{ elapsed }} 秒</p>
        </div>
      </div>
    </template>
  </section>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useRoute } from "vue-router";
import ChessBoard from "../components/ChessBoard.vue";
import { api } from "../api";
import { createPracticeSession } from "../stores/practice";

const route = useRoute();
const queue = ref([]);
const index = ref(0);
const loading = ref(true);
const session = ref(null);
const selected = ref(null);
const elapsed = ref(0);
let timer = null;

const current = computed(() => queue.value[index.value] || null);
const pieces = computed(() => session.value?.state.pieces ?? []);
const mistakes = computed(() => session.value?.state.mistakes ?? 0);
const revealed = computed(() => session.value?.state.revealed ?? false);
const done = computed(() => (session.value ? session.value.isFinished() : false));

const sideText = computed(() => {
  const side = current.value?.game?.practice_side || "both";
  if (side === "red") return "红方";
  if (side === "black") return "黑方";
  return "轮到的一方";
});

function startCurrent() {
  selected.value = null;
  elapsed.value = 0;
  session.value = current.value ? createPracticeSession(current.value.game) : null;
}

function onCellClick(x, y) {
  if (!session.value || done.value) return;
  const board = pieces.value;
  if (!selected.value) {
    const piece = board.find((p) => p.x === x && p.y === y);
    const isRedTurn = session.value.state.ply % 2 === 0;
    const currentSide = isRedTurn ? "red" : "black";
    if (piece && piece.side === currentSide) selected.value = { x, y };
    return;
  }
  if (selected.value.x === x && selected.value.y === y) {
    selected.value = null;
    return;
  }
  const target = board.find((p) => p.x === x && p.y === y);
  const moving = board.find((p) => p.x === selected.value.x && p.y === selected.value.y);
  if (target && moving && target.side === moving.side) {
    selected.value = { x, y };
    return;
  }
  session.value.submitMove({ x1: selected.value.x, y1: selected.value.y, x2: x, y2: y });
  selected.value = null;
}

function onReveal() {
  if (!session.value || done.value) return;
  session.value.reveal();
  selected.value = null;
}

async function onSubmit() {
  if (!session.value) return;
  const s = session.value;
  try {
    await api.submitReview(current.value.game.id, {
      mistake_count: s.state.mistakes,
      revealed: s.state.revealed,
      duration_ms: elapsed.value * 1000,
    });
  } catch (error) {
    return;
  }
  index.value += 1;
  startCurrent();
}

onMounted(async () => {
  timer = setInterval(() => {
    if (done.value) return;
    elapsed.value += 1;
  }, 1000);
  try {
    const gameId = route.query.game;
    if (gameId) {
      const game = await api.getGame(gameId);
      const today = new Date().toISOString().slice(0, 10);
      queue.value = [{ game, due_date: today, is_new: !game.review }];
    } else {
      const data = await api.reviewQueue();
      queue.value = data.items || [];
    }
  } catch (error) {
    queue.value = [];
  } finally {
    loading.value = false;
  }
  startCurrent();
});

onUnmounted(() => {
  if (timer) clearInterval(timer);
});
</script>

<style scoped>
.review .hint {
  text-align: center;
}

.layout {
  display: grid;
  grid-template-columns: 1fr;
  gap: 16px;
}

.side {
  display: flex;
  flex-direction: column;
  gap: 10px;
  align-items: stretch;
}

.prompt {
  font-size: 18px;
  font-weight: 600;
}

.revealed {
  color: #b32020;
}

.side button {
  min-height: 48px;
  padding: 12px 20px;
  border: none;
  border-radius: 6px;
  background: #7a3b2e;
  color: #fff;
  cursor: pointer;
}

.done {
  font-size: 18px;
  font-weight: 600;
  color: #2f7d32;
}

@media (min-width: 768px) {
  .layout {
    grid-template-columns: 528px 1fr;
    gap: 24px;
  }

  .side {
    align-items: flex-start;
  }

  .side button {
    min-height: 0;
    padding: 8px 16px;
  }
}
</style>
