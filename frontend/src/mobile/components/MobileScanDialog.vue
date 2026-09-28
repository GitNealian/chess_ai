<script setup>
import { computed, ref } from "vue";
import MobileBoardEditor from "./MobileBoardEditor.vue";
import { api } from "../../api";
import { LABELS } from "../../utils/chess";

const emit = defineEmits(["apply", "cancel"]);

const MAX_SIDE = 1600;

const stage = ref("pick");
const error = ref("");
const recognized = ref([]);
const warnings = ref([]);
let controller = null;

const noticeText = computed(() => {
  const base = "识别可能有误，请核对后确认";
  return warnings.value.length ? `${warnings.value.join("；")}；${base}` : base;
});

function buildPieces(pieces) {
  return (pieces || []).map((piece) => ({
    x: piece.x,
    y: piece.y,
    side: piece.side,
    kind: piece.kind,
    label: LABELS[`${piece.side}-${piece.kind}`] || "",
  }));
}

async function compress(file) {
  if (typeof createImageBitmap !== "function") return file;
  try {
    const bitmap = await createImageBitmap(file);
    const scale = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height));
    const width = Math.max(1, Math.round(bitmap.width * scale));
    const height = Math.max(1, Math.round(bitmap.height * scale));
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext("2d");
    if (!context) {
      bitmap.close?.();
      return file;
    }
    context.drawImage(bitmap, 0, 0, width, height);
    bitmap.close?.();
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.85));
    return blob || file;
  } catch {
    return file;
  }
}

async function onFile(event) {
  const input = event.target;
  const file = input.files?.[0];
  input.value = "";
  if (!file || stage.value === "loading") return;

  stage.value = "loading";
  error.value = "";
  const current = new AbortController();
  controller = current;
  try {
    const compressed = await compress(file);
    const form = new FormData();
    form.append("image", compressed, "board.jpg");
    const data = await api.recognize(form, { signal: current.signal, timeout: 60000 });
    recognized.value = buildPieces(data.pieces);
    warnings.value = data.warnings || [];
    stage.value = "edit";
  } catch (err) {
    if (current.signal.aborted) return;
    stage.value = "pick";
    error.value =
      err?.response?.data?.error ||
      err?.response?.data?.detail ||
      (err?.code === "ECONNABORTED" ? "识别超时，请重试" : "识别失败，请重试");
  } finally {
    if (controller === current) controller = null;
  }
}

function cancel() {
  if (controller) controller.abort();
  emit("cancel");
}
</script>

<template>
  <MobileBoardEditor
    v-if="stage === 'edit'"
    :pieces="recognized"
    title="识别结果"
    :notice="noticeText"
    @apply="(pieces, fen) => emit('apply', pieces, fen)"
    @cancel="emit('cancel')"
  />
  <div v-else class="scan-mask" data-test="scan-mask" @click.self="cancel">
    <div class="scan-card" data-test="scan-card">
      <h3 class="scan-title">扫描局面</h3>
      <p class="scan-tip">将屏幕上的棋盘完整放入画面，尽量正对拍摄，避免反光。</p>
      <p v-if="error" class="scan-error" data-test="scan-error">{{ error }}</p>
      <div v-if="stage === 'loading'" class="scan-loading" data-test="scan-loading">
        <span>识别中…</span>
        <button type="button" data-test="scan-abort" @click="cancel">取消</button>
      </div>
      <div v-else class="scan-actions">
        <label class="scan-button" data-test="scan-camera">
          拍照
          <input type="file" accept="image/*" capture="environment" hidden @change="onFile" />
        </label>
        <label class="scan-button" data-test="scan-album">
          相册
          <input type="file" accept="image/*" hidden @change="onFile" />
        </label>
      </div>
      <div class="scan-foot">
        <button type="button" data-test="scan-cancel" @click="cancel">关闭</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.scan-mask {
  position: fixed;
  inset: 0;
  z-index: 200;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
}

.scan-card {
  width: 100%;
  max-width: 420px;
  background: #faf6ee;
  border-radius: 12px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.scan-title {
  margin: 0;
}

.scan-tip {
  margin: 0;
  color: #7a5c3e;
  font-size: 13px;
  line-height: 1.5;
}

.scan-error {
  margin: 0;
  color: #b45309;
}

.scan-actions {
  display: flex;
  gap: 8px;
}

.scan-button {
  flex: 1;
  min-height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid #cbb89a;
  border-radius: 6px;
  background: #fff;
  color: #7a3b2e;
  cursor: pointer;
}

.scan-loading {
  display: flex;
  align-items: center;
  gap: 12px;
  color: #7a3b2e;
}

.scan-loading button {
  min-height: 40px;
  padding: 0 16px;
  border: 1px solid #cbb89a;
  border-radius: 6px;
  background: #fff;
  color: #7a3b2e;
  cursor: pointer;
}

.scan-foot {
  display: flex;
}

.scan-foot button {
  flex: 1;
  min-height: 44px;
  border: 1px solid #cbb89a;
  border-radius: 6px;
  background: #fff;
  color: #7a3b2e;
  cursor: pointer;
}
</style>
