<template>
  <div class="board-controls">
    <button
      v-if="canLeft"
      type="button"
      class="board-controls__arrow board-controls__arrow--left"
      data-test="ctrl-scroll-left"
      aria-label="向左滚动"
      @click="scrollBy(-1)"
    >
      ‹
    </button>
    <div ref="scroller" class="board-controls__scroller">
      <div class="board-controls__track">
        <template v-if="mode === 'recite'">
          <button
            v-if="showNav"
            type="button"
            data-test="ctrl-prev-game"
            @click="emit('prev-game')"
          >
            上一盘
          </button>
          <button
            v-if="showNav"
            type="button"
            data-test="ctrl-next-game"
            @click="emit('next-game')"
          >
            下一盘
          </button>
          <button
            type="button"
            data-test="ctrl-flip"
            :aria-pressed="flipped ? 'true' : 'false'"
            @click="emit('flip')"
          >
            翻转
          </button>
          <button type="button" data-test="ctrl-reveal" @click="emit('reveal')">看答案</button>
          <button type="button" data-test="ctrl-exit-recite" @click="emit('exit-recite')">
            退出背谱
          </button>
        </template>
        <template v-else>
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
            v-if="showNav"
            type="button"
            data-test="ctrl-prev-game"
            @click="emit('prev-game')"
          >
            上一盘
          </button>
          <button
            v-if="showNav"
            type="button"
            data-test="ctrl-next-game"
            @click="emit('next-game')"
          >
            下一盘
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
          <button
            v-if="showRecite"
            type="button"
            data-test="ctrl-recite"
            @click="emit('recite')"
          >
            背谱
          </button>
        </template>
      </div>
    </div>
    <button
      v-if="canRight"
      type="button"
      class="board-controls__arrow board-controls__arrow--right"
      data-test="ctrl-scroll-right"
      aria-label="向右滚动"
      @click="scrollBy(1)"
    >
      ›
    </button>
  </div>
</template>

<script setup>
import { nextTick, onMounted, onUnmounted, ref, watch } from "vue";

const props = defineProps({
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
  mode: { type: String, default: "browse" },
  showNav: { type: Boolean, default: false },
  showRecite: { type: Boolean, default: false },
});

const emit = defineEmits([
  "start",
  "prev",
  "next",
  "end",
  "flip",
  "edit",
  "scan",
  "undo",
  "infer",
  "prev-game",
  "next-game",
  "recite",
  "reveal",
  "exit-recite",
]);

const scroller = ref(null);
const canLeft = ref(false);
const canRight = ref(false);
let resizeObserver = null;

function updateArrows() {
  const el = scroller.value;
  if (!el) return;
  canLeft.value = el.scrollLeft > 1;
  canRight.value = Math.ceil(el.scrollLeft + el.clientWidth) < el.scrollWidth - 1;
}

function scrollBy(direction) {
  const el = scroller.value;
  if (!el) return;
  el.scrollBy({ left: direction * Math.round(el.clientWidth * 0.8), behavior: "smooth" });
}

onMounted(() => {
  updateArrows();
  const el = scroller.value;
  el?.addEventListener("scroll", updateArrows, { passive: true });
  if (typeof ResizeObserver !== "undefined" && el) {
    resizeObserver = new ResizeObserver(updateArrows);
    resizeObserver.observe(el);
    const track = el.firstElementChild;
    if (track) resizeObserver.observe(track);
  }
});

onUnmounted(() => {
  scroller.value?.removeEventListener("scroll", updateArrows);
  resizeObserver?.disconnect();
});

watch(
  () => [props.mode, props.showNav, props.showRecite, props.showUndo, props.showInfer],
  () => nextTick(updateArrows)
);
</script>

<style scoped>
.board-controls {
  position: relative;
  display: flex;
  align-items: stretch;
}

.board-controls__scroller {
  flex: 1;
  min-width: 0;
  overflow-x: auto;
  scrollbar-width: none;
  -ms-overflow-style: none;
}

.board-controls__scroller::-webkit-scrollbar {
  display: none;
}

.board-controls__track {
  display: flex;
  gap: 8px;
  width: max-content;
  padding: 2px;
}

.board-controls__track button {
  flex: 0 0 auto;
  min-height: 44px;
  padding: 8px 14px;
  font-size: 14px;
  white-space: nowrap;
  color: #7a3b2e;
  background: #fff;
  border: 1px solid #cbb89a;
  border-radius: 6px;
  cursor: pointer;
}

.board-controls__track button:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.board-controls__track button[aria-pressed="true"] {
  background: #f4e3c1;
  border-color: #7a3b2e;
}

.board-controls__arrow {
  flex: 0 0 auto;
  width: 28px;
  padding: 0;
  border: none;
  background: rgba(250, 246, 238, 0.95);
  color: #7a3b2e;
  font-size: 22px;
  line-height: 1;
  cursor: pointer;
}

.board-controls__arrow--left {
  border-radius: 6px 0 0 6px;
}

.board-controls__arrow--right {
  border-radius: 0 6px 6px 0;
}
</style>
