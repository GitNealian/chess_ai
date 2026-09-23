<script setup>
import { LABELS } from "../utils/chess";

defineProps({
  selected: { type: Object, default: null },
});
defineEmits(["select", "clear", "initial"]);

const kinds = ["K", "A", "B", "N", "R", "C", "P"];
const sides = ["red", "black"];
const label = (side, kind) => LABELS[`${side}-${kind}`];
</script>

<template>
  <div class="palette">
    <div v-for="side in sides" :key="side" class="palette-row">
      <button
        v-for="kind in kinds"
        :key="kind"
        type="button"
        :data-piece="`${side}-${kind}`"
        class="piece-btn"
        :class="{
          active: selected && selected.side === side && selected.kind === kind,
          red: side === 'red',
          black: side === 'black',
        }"
        @click="$emit('select', { side, kind })"
      >
        {{ label(side, kind) }}
      </button>
    </div>
    <div class="palette-actions">
      <button type="button" data-test="palette-clear" @click="$emit('clear')">清空棋盘</button>
      <button type="button" data-test="palette-initial" @click="$emit('initial')">标准开局</button>
    </div>
  </div>
</template>

<style scoped>
.palette {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.palette-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.piece-btn {
  min-width: 40px;
  min-height: 40px;
  border: 1px solid #cbb89a;
  border-radius: 50%;
  background: #fff4e0;
  font-size: 18px;
  cursor: pointer;
}

.piece-btn.black {
  background: #f7f7f2;
}

.piece-btn.red {
  color: #b32020;
}

.piece-btn.active {
  border-color: #d4a017;
  box-shadow: 0 0 0 2px rgba(212, 160, 23, 0.5);
}

.palette-actions {
  display: flex;
  gap: 8px;
}

.palette-actions button {
  min-height: 40px;
}
</style>
