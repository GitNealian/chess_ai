<template>
  <div class="board-controls">
    <button type="button" data-test="ctrl-start" :disabled="!canStart" @click="emit('start')">
      开局
    </button>
    <button type="button" data-test="ctrl-prev" :disabled="!canPrev" @click="emit('prev')">
      后退
    </button>
    <button type="button" data-test="ctrl-next" :disabled="!canNext" @click="emit('next')">
      前进
    </button>
    <button type="button" data-test="ctrl-end" :disabled="!canEnd" @click="emit('end')">
      终局
    </button>
    <button
      type="button"
      data-test="ctrl-flip"
      :aria-pressed="flipped ? 'true' : 'false'"
      @click="emit('flip')"
    >
      翻转
    </button>
    <button
      v-if="showUndo"
      type="button"
      data-test="ctrl-undo"
      :disabled="!canUndo"
      @click="emit('undo')"
    >
      悔棋
    </button>
    <button type="button" data-test="ctrl-edit" :disabled="!canEdit" @click="emit('edit')">
      编辑
    </button>
    <button type="button" data-test="ctrl-scan" :disabled="!canScan" @click="emit('scan')">
      扫描
    </button>
    <button
      v-if="showInfer"
      type="button"
      data-test="ctrl-infer"
      :disabled="!canInfer"
      @click="emit('infer')"
    >
      推演
    </button>
  </div>
</template>

<script setup>
defineProps({
  flipped: { type: Boolean, default: false },
  canStart: { type: Boolean, default: false },
  canPrev: { type: Boolean, default: false },
  canNext: { type: Boolean, default: false },
  canEnd: { type: Boolean, default: false },
  canEdit: { type: Boolean, default: false },
  canScan: { type: Boolean, default: false },
  showInfer: { type: Boolean, default: false },
  canInfer: { type: Boolean, default: false },
  showUndo: { type: Boolean, default: false },
  canUndo: { type: Boolean, default: false },
});

const emit = defineEmits(["start", "prev", "next", "end", "flip", "edit", "scan", "undo", "infer"]);
</script>

<style scoped>
.board-controls {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.board-controls button {
  flex: 1 1 0;
  min-height: 44px;
  padding: 8px 4px;
  font-size: 14px;
  white-space: nowrap;
  color: #7a3b2e;
  background: #fff;
  border: 1px solid #cbb89a;
  border-radius: 6px;
  cursor: pointer;
}

.board-controls button:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.board-controls button[aria-pressed="true"] {
  background: #f4e3c1;
  border-color: #7a3b2e;
}
</style>
