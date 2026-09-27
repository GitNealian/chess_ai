<script setup>
import { computed, ref } from "vue";
import ChessBoard from "../../components/ChessBoard.vue";
import MobileAnalysis from "./MobileAnalysis.vue";
import { applyMove, fenToPieces } from "../../utils/chess";
import { api } from "../../api";

const props = defineProps({
  initialFen: { type: String, required: true },
  baseMoves: { type: Array, default: () => [] },
});
const emit = defineEmits(["close"]);

const moves = ref([]);
const selected = ref(null);
const hint = ref("");
const flipped = ref(false);
const arrows = ref([]);
let pending = false;
let token = 0;

const firstSide = props.initialFen.split(" ")[1] === "b" ? "black" : "red";
const basePieces = (() => {
  let out = fenToPieces(props.initialFen);
  for (const m of props.baseMoves) out = applyMove(out, m);
  return out;
})();

const allMoves = computed(() =>
  props.baseMoves
    .concat(moves.value)
    .map(({ x1, y1, x2, y2 }) => ({ x1, y1, x2, y2 }))
);
const sideToMove = computed(() => {
  if (allMoves.value.length % 2 === 0) return firstSide;
  return firstSide === "red" ? "black" : "red";
});
const pieces = computed(() => {
  let out = basePieces;
  for (const m of moves.value) out = applyMove(out, m);
  return out;
});
const position = computed(() => ({ pieces: pieces.value }));

async function submit(move) {
  hint.value = "";
  pending = true;
  const t = ++token;
  try {
    const data = await api.validateMove({
      initial_fen: props.initialFen,
      moves: allMoves.value,
      move,
    });
    if (t !== token) return;
    if (!data.legal) {
      hint.value = data.reason || "着法不合法";
      return;
    }
    moves.value.push({
      ...move,
      chinese: data.chinese || "",
      check: Boolean(data.check),
      gameOver: data.game_over || null,
    });
    selected.value = null;
  } catch (err) {
    if (t !== token) return;
    hint.value =
      err?.response?.data?.detail || err?.response?.data?.error || "校验失败，请重试";
  } finally {
    if (t === token) pending = false;
  }
}

function onCellClick(x, y) {
  if (pending) return;
  const piece = pieces.value.find((p) => p.x === x && p.y === y);
  if (selected.value) {
    if (piece && piece.side === sideToMove.value) {
      const same = selected.value.x === x && selected.value.y === y;
      selected.value = same ? null : { x, y };
      return;
    }
    submit({ x1: selected.value.x, y1: selected.value.y, x2: x, y2: y });
    return;
  }
  if (piece && piece.side === sideToMove.value) selected.value = { x, y };
}

function undo() {
  token += 1;
  pending = false;
  selected.value = null;
  hint.value = "";
  moves.value.pop();
}
</script>

<template>
  <div class="infer-mask" data-test="infer-mask" @click.self="selected = null">
    <div class="infer-card" data-test="infer-card">
      <h3 class="infer-title">推演</h3>
      <ChessBoard
        :position="position"
        :selected="selected"
        :arrows="arrows"
        :flipped="flipped"
        @cell-click="onCellClick"
      />
      <p v-if="hint" class="infer-hint" data-test="infer-hint">{{ hint }}</p>
      <div class="infer-actions">
        <button type="button" data-test="infer-undo" :disabled="!moves.length" @click="undo">
          悔棋
        </button>
        <button type="button" data-test="infer-flip" @click="flipped = !flipped">翻转</button>
        <button type="button" data-test="infer-close" @click="emit('close')">关闭</button>
      </div>
      <MobileAnalysis
        :initial-fen="initialFen"
        :moves="allMoves"
        :score="true"
        :intent="false"
        @arrows="arrows = $event"
      />
    </div>
  </div>
</template>

<style scoped>
.infer-mask {
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

.infer-card {
  width: 100%;
  max-width: 420px;
  height: calc(100vh - 32px);
  height: calc(100dvh - 32px);
  margin: auto;
  background: #faf6ee;
  border-radius: 12px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow-y: auto;
}

.infer-title {
  margin: 0;
}

.infer-hint {
  margin: 0;
  color: #b45309;
}

.infer-actions {
  display: flex;
  gap: 8px;
}

.infer-actions button {
  flex: 1;
  min-height: 44px;
  border: 1px solid #cbb89a;
  border-radius: 6px;
  background: #fff;
  color: #7a3b2e;
  cursor: pointer;
}

.infer-actions button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
