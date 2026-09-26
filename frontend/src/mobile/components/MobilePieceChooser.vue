<script setup>
import { LABELS, MAX_COUNTS } from "../../utils/chess";

const props = defineProps({
  pieces: { type: Array, default: () => [] },
  selected: { type: Object, default: null },
});
const emit = defineEmits(["select"]);

const KINDS = ["K", "A", "B", "N", "R", "C", "P"];
const ROWS = [
  { side: "black" },
  { side: "red" },
];

const countOf = (side, kind) =>
  props.pieces.filter((p) => p.side === side && p.kind === kind).length;
const isDisabled = (side, kind) => countOf(side, kind) >= MAX_COUNTS[kind];
const isActive = (side, kind) =>
  !!props.selected && props.selected.side === side && props.selected.kind === kind;
const label = (side, kind) => LABELS[`${side}-${kind}`];
</script>

<template>
  <div class="chooser">
    <div v-for="row in ROWS" :key="row.side" class="chooser-row" :data-row="row.side">
      <button
        v-for="kind in KINDS"
        :key="kind"
        type="button"
        :data-piece="`${row.side}-${kind}`"
        class="chooser-btn"
        :class="{ active: isActive(row.side, kind), red: row.side === 'red' }"
        :disabled="isDisabled(row.side, kind)"
        @click="emit('select', { side: row.side, kind })"
      >
        {{ label(row.side, kind) }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.chooser {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.chooser-row {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 6px;
}

.chooser-btn {
  aspect-ratio: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid #cbb89a;
  border-radius: 50%;
  background: #fff4e0;
  color: #1a1a1a;
  font-size: 18px;
  cursor: pointer;
}

.chooser-btn.red {
  color: #b32020;
}

.chooser-btn.active {
  border-color: #d4a017;
  box-shadow: 0 0 0 2px rgba(212, 160, 23, 0.5);
}

.chooser-btn:disabled {
  filter: grayscale(1);
  opacity: 0.35;
  cursor: not-allowed;
}
</style>
