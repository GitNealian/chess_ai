<script setup>
import { ref } from "vue";
import ChessBoard from "../../components/ChessBoard.vue";
import MobilePieceChooser from "./MobilePieceChooser.vue";
import { LABELS } from "../../utils/chess";
import { api } from "../../api";

const props = defineProps({ pieces: { type: Array, default: () => [] } });
const emit = defineEmits(["cancel", "apply"]);

const draft = ref(props.pieces.map((p) => ({ ...p })));
const selected = ref(null);
const palette = ref(null);
const editSide = ref("red");
const errors = ref([]);
const applying = ref(false);

function clearSelection() {
  selected.value = null;
  palette.value = null;
}

function clearBoard() {
  if (applying.value) return;
  draft.value = [];
  selected.value = null;
  palette.value = null;
}

function onChooserSelect(piece) {
  if (palette.value && palette.value.side === piece.side && palette.value.kind === piece.kind) {
    palette.value = null;
    return;
  }
  palette.value = piece;
  selected.value = null;
}

function onCellClick(x, y) {
  if (applying.value) return;
  const target = draft.value.find((p) => p.x === x && p.y === y);

  if (palette.value) {
    const { side, kind } = palette.value;
    draft.value = [
      ...draft.value.filter((p) => !(p.x === x && p.y === y)),
      { x, y, side, kind, label: LABELS[`${side}-${kind}`] },
    ];
    palette.value = null;
    return;
  }

  if (selected.value) {
    if (selected.value.x === x && selected.value.y === y) {
      draft.value = draft.value.filter((p) => !(p.x === x && p.y === y));
      selected.value = null;
      return;
    }
    const moving = draft.value.find(
      (p) => p.x === selected.value.x && p.y === selected.value.y
    );
    draft.value = [
      ...draft.value.filter(
        (p) =>
          !(p.x === x && p.y === y) &&
          !(p.x === selected.value.x && p.y === selected.value.y)
      ),
      { ...moving, x, y },
    ];
    selected.value = null;
    return;
  }

  if (target) selected.value = { x, y };
}

async function apply() {
  if (applying.value) return;
  applying.value = true;
  errors.value = [];
  try {
    const res = await api.validatePosition({
      pieces: draft.value.map(({ x, y, side, kind }) => ({ x, y, side, kind })),
      side_to_move: editSide.value,
    });
    if (!res.valid) {
      errors.value = res.errors || ["局面不合法"];
      return;
    }
    emit("apply", draft.value.map((p) => ({ ...p })));
  } catch (err) {
    errors.value = [
      err?.response?.data?.detail || err?.response?.data?.error || "校验失败，请重试",
    ];
  } finally {
    applying.value = false;
  }
}
</script>

<template>
  <div class="editor-mask" data-test="editor-mask" @click.self="clearSelection">
    <div class="editor-card" data-test="editor-card">
      <h3 class="editor-title">编辑局面</h3>
      <ChessBoard :position="{ pieces: draft }" :selected="selected" @cell-click="onCellClick" />
      <MobilePieceChooser :pieces="draft" :selected="palette" @select="onChooserSelect" />
      <div class="editor-foot">
        <div class="editor-side">
          <span>行棋方</span>
          <label>
            <input
              v-model="editSide"
              type="radio"
              value="red"
              data-test="editor-side-red"
              :disabled="applying"
            />
            红先
          </label>
          <label>
            <input
              v-model="editSide"
              type="radio"
              value="black"
              data-test="editor-side-black"
              :disabled="applying"
            />
            黑先
          </label>
        </div>
        <button
          type="button"
          class="editor-clear"
          data-test="editor-clear"
          :disabled="applying"
          @click="clearBoard"
        >
          清空棋盘
        </button>
      </div>
      <p v-for="(err, i) in errors" :key="i" class="editor-error" data-test="editor-error">
        {{ err }}
      </p>
      <div class="editor-actions">
        <button
          type="button"
          data-test="editor-cancel"
          :disabled="applying"
          @click="emit('cancel')"
        >
          取消
        </button>
        <button type="button" data-test="editor-apply" :disabled="applying" @click="apply">
          {{ applying ? "校验中…" : "确认" }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.editor-mask {
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

.editor-card {
  width: 100%;
  max-width: 420px;
  margin: auto;
  background: #faf6ee;
  border-radius: 12px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.editor-title {
  margin: 0;
}

.editor-clear {
  flex: 0 0 auto;
  min-height: 40px;
  padding: 0 16px;
  border: 1px solid #cbb89a;
  border-radius: 6px;
  background: #fff;
  color: #7a3b2e;
  cursor: pointer;
}

.editor-clear:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.editor-foot {
  display: flex;
  align-items: center;
  gap: 12px;
}

.editor-side {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
}

.editor-side label {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.editor-side input[type="radio"] {
  width: 18px;
  height: 18px;
}

.editor-error {
  margin: 0;
  color: #b45309;
}

.editor-actions {
  display: flex;
  gap: 8px;
}

.editor-actions button {
  flex: 1;
  min-height: 44px;
  border: 1px solid #cbb89a;
  border-radius: 6px;
  background: #fff;
  color: #7a3b2e;
  cursor: pointer;
}

.editor-actions button[data-test="editor-apply"] {
  background: #7a3b2e;
  border-color: #7a3b2e;
  color: #fff;
}

.editor-actions button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
