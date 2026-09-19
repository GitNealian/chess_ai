<script setup>
import { computed } from "vue";

const props = defineProps({
  position: { type: Object, required: true },
  selected: { type: Object, default: null },
  legalTargets: { type: Array, default: () => [] },
});

const emit = defineEmits(["cell-click"]);

const margin = 40;
const gap = 56;
const W = margin * 2 + 8 * gap;
const H = margin * 2 + 9 * gap;

const cellX = (x) => margin + x * gap;
const cellY = (y) => margin + (9 - y) * gap;

const pieces = computed(() => props.position?.pieces ?? []);

const files = [0, 1, 2, 3, 4, 5, 6, 7, 8];
const ranks = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9];

const cells = [];
for (let y = 0; y < 10; y += 1) {
  for (let x = 0; x < 9; x += 1) {
    cells.push({ x, y });
  }
}

function onSvgClick(event) {
  const target = event.target.closest?.("[data-cell]");
  if (!target) return;
  const [x, y] = target.getAttribute("data-cell").split("-").map(Number);
  emit("cell-click", x, y);
}
</script>

<template>
  <svg
    class="chess-board"
    :viewBox="`0 0 ${W} ${H}`"
    width="100%"
    @click="onSvgClick"
  >
    <rect :x="0" :y="0" :width="W" :height="H" fill="#f3dcb2" />

    <line
      v-for="r in ranks"
      :key="`h${r}`"
      :x1="cellX(0)"
      :y1="cellY(r)"
      :x2="cellX(8)"
      :y2="cellY(r)"
      stroke="#7a5c3e"
      stroke-width="1.5"
    />

    <template v-for="f in files" :key="`v${f}`">
      <line
        v-if="f === 0 || f === 8"
        :x1="cellX(f)"
        :y1="cellY(0)"
        :x2="cellX(f)"
        :y2="cellY(9)"
        stroke="#7a5c3e"
        stroke-width="1.5"
      />
      <template v-else>
        <line
          :x1="cellX(f)"
          :y1="cellY(9)"
          :x2="cellX(f)"
          :y2="cellY(5)"
          stroke="#7a5c3e"
          stroke-width="1.5"
        />
        <line
          :x1="cellX(f)"
          :y1="cellY(4)"
          :x2="cellX(f)"
          :y2="cellY(0)"
          stroke="#7a5c3e"
          stroke-width="1.5"
        />
      </template>
    </template>

    <rect
      :x="cellX(0) - 12"
      :y="cellY(9) - 12"
      :width="8 * gap + 24"
      :height="9 * gap + 24"
      fill="none"
      stroke="#5a3d24"
      stroke-width="3"
    />

    <line
      :x1="cellX(3)"
      :y1="cellY(0)"
      :x2="cellX(5)"
      :y2="cellY(2)"
      stroke="#7a5c3e"
      stroke-width="1.5"
    />
    <line
      :x1="cellX(5)"
      :y1="cellY(0)"
      :x2="cellX(3)"
      :y2="cellY(2)"
      stroke="#7a5c3e"
      stroke-width="1.5"
    />
    <line
      :x1="cellX(3)"
      :y1="cellY(9)"
      :x2="cellX(5)"
      :y2="cellY(7)"
      stroke="#7a5c3e"
      stroke-width="1.5"
    />
    <line
      :x1="cellX(5)"
      :y1="cellY(9)"
      :x2="cellX(3)"
      :y2="cellY(7)"
      stroke="#7a5c3e"
      stroke-width="1.5"
    />

    <text
      :x="cellX(1.5)"
      :y="(cellY(4) + cellY(5)) / 2 + 10"
      text-anchor="middle"
      font-size="26"
      fill="#7a5c3e"
    >
      楚 河
    </text>
    <text
      :x="cellX(6.5)"
      :y="(cellY(4) + cellY(5)) / 2 + 10"
      text-anchor="middle"
      font-size="26"
      fill="#7a5c3e"
    >
      汉 界
    </text>

    <rect
      v-if="selected"
      :x="cellX(selected.x) - gap / 2 + 3"
      :y="cellY(selected.y) - gap / 2 + 3"
      :width="gap - 6"
      :height="gap - 6"
      fill="rgba(212,160,23,0.25)"
      stroke="#d4a017"
      stroke-width="3"
    />

    <g v-for="piece in pieces" :key="`p${piece.x}-${piece.y}`">
      <circle
        :cx="cellX(piece.x)"
        :cy="cellY(piece.y)"
        r="20"
        :fill="piece.side === 'red' ? '#fff4e0' : '#f7f7f2'"
        stroke="#7a3b2e"
        stroke-width="2"
        :class="{ selected: selected && selected.x === piece.x && selected.y === piece.y }"
      />
      <text
        :x="cellX(piece.x)"
        :y="cellY(piece.y) + 8"
        text-anchor="middle"
        font-size="24"
        :fill="piece.side === 'red' ? '#b32020' : '#1a1a1a'"
      >
        {{ piece.label }}
      </text>
    </g>

    <circle
      v-for="spot in legalTargets"
      :key="`t${spot.x}-${spot.y}`"
      :cx="cellX(spot.x)"
      :cy="cellY(spot.y)"
      r="7"
      fill="rgba(40,140,60,0.55)"
    />

    <rect
      v-for="c in cells"
      :key="`c${c.x}-${c.y}`"
      :data-cell="`${c.x}-${c.y}`"
      :x="cellX(c.x) - gap / 2"
      :y="cellY(c.y) - gap / 2"
      :width="gap"
      :height="gap"
      fill="transparent"
      pointer-events="all"
    />
  </svg>
</template>

<style scoped>
.chess-board {
  display: block;
  width: 100%;
  max-width: 100%;
  height: auto;
  margin: 0 auto;
}

.chess-board .selected {
  stroke: #d4a017;
  stroke-width: 4;
}

@media (min-width: 768px) {
  .chess-board {
    max-width: 540px;
  }
}
</style>
