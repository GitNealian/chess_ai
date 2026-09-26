<script setup>
import { computed, onUnmounted, ref, watch } from "vue";
import { analyzeStream, intentStream } from "../../api";
import IntentPanel from "../../components/IntentPanel.vue";

const props = defineProps({
  initialFen: { type: String, default: "" },
  moves: { type: Array, default: () => [] },
  score: { type: Boolean, default: false },
  intent: { type: Boolean, default: false },
});

const emit = defineEmits(["arrows"]);

const analysis = ref(emptyAnalysis("idle"));
const intent = ref(emptyIntent("idle"));

let analysisController = null;
let analysisToken = 0;
let intentController = null;
let intentToken = 0;

function emptyAnalysis(status) {
  return {
    status,
    results: [],
    scoreRed: null,
    mate: null,
    best: null,
    reply: null,
    error: "",
  };
}

function emptyIntent(status) {
  return { status, rank: null, threat: null, baits: [], error: "" };
}

const enabled = computed(() => props.score || props.intent);

const scoreText = computed(() => {
  const a = analysis.value;
  if (a.status === "running" && a.scoreRed === null) return "分析中…";
  if (a.status === "error") return "分析失败";
  return formatScore(a.scoreRed, a.mate) || "—";
});

const statusText = computed(() => {
  const a = analysis.value;
  if (a.status === "running") return "分析中…";
  if (a.status === "done") return "已完成";
  if (a.status === "error") return `分析失败：${a.error}`;
  return "";
});

const barWidth = computed(() => {
  const score = analysis.value.scoreRed;
  if (score === null) return 50;
  const clamped = Math.max(-1000, Math.min(1000, score));
  return 50 + clamped / 20;
});

const arrows = computed(() => {
  const out = [];
  const a = analysis.value;
  if (a.best) out.push({ ...a.best, kind: "best" });
  if (a.reply) out.push({ ...a.reply, kind: "reply" });
  return out;
});

watch(
  arrows,
  (value) => emit("arrows", value),
  { immediate: true }
);

function formatScore(scoreRed, mate) {
  if (scoreRed === null || scoreRed === undefined) return "";
  if (mate !== null && mate !== undefined) {
    const side = scoreRed >= 0 ? "红方" : "黑方";
    return `${side} ${Math.abs(mate)} 步杀`;
  }
  if (Math.abs(scoreRed) < 1) return "均势";
  const value = Math.abs(scoreRed);
  return scoreRed > 0 ? `红优 +${value}` : `黑优 ${value}`;
}

function pvText(result) {
  return (result.pv || []).map((p) => p.chinese || p.iccs).join(" → ");
}

function payload() {
  return {
    initial_fen: props.initialFen,
    moves: props.moves.map(({ x1, y1, x2, y2 }) => ({ x1, y1, x2, y2 })),
  };
}

function stopAnalysis() {
  analysisToken += 1;
  if (analysisController) {
    analysisController.abort();
    analysisController = null;
  }
}

function stopIntent() {
  intentToken += 1;
  if (intentController) {
    intentController.abort();
    intentController = null;
  }
}

function reset() {
  stopAnalysis();
  stopIntent();
  analysis.value = emptyAnalysis("idle");
  intent.value = emptyIntent("idle");
}

function startAnalysis() {
  stopAnalysis();
  const token = analysisToken;
  analysis.value = emptyAnalysis("running");
  analysisController = new AbortController();
  analyzeStream(payload(), {
    signal: analysisController.signal,
    onResult: (r) => {
      if (token !== analysisToken) return;
      const current = analysis.value;
      current.results.unshift(r);
      current.scoreRed = r.score_red ?? null;
      current.mate = r.mate ?? null;
      current.best = r.pv?.[0] ?? null;
      current.reply = r.pv?.[1] ?? null;
    },
    onDone: () => {
      if (token === analysisToken) analysis.value.status = "done";
    },
    onError: (e) => {
      if (token !== analysisToken) return;
      analysis.value.status = "error";
      analysis.value.error = e?.message || "未知错误";
    },
  });
}

function startIntent() {
  stopAnalysis();
  stopIntent();
  const token = intentToken;
  intent.value = emptyIntent("running");
  intentController = new AbortController();
  intentStream(payload(), {
    signal: intentController.signal,
    onRank: (r) => {
      if (token === intentToken) intent.value.rank = r;
    },
    onThreat: (r) => {
      if (token === intentToken) intent.value.threat = r;
    },
    onBait: (r) => {
      if (token === intentToken) intent.value.baits.push(r);
    },
    onDone: () => {
      if (token !== intentToken) return;
      intent.value.status = "done";
      if (props.score) startAnalysis();
    },
    onError: (e) => {
      if (token !== intentToken) return;
      intent.value.status = "error";
      intent.value.error = e?.message || "";
      if (props.score) startAnalysis();
    },
  });
}

function run() {
  if (!enabled.value || !props.initialFen) {
    reset();
    return;
  }
  if (props.intent) startIntent();
  else startAnalysis();
}

watch(
  () => [
    props.initialFen,
    props.score,
    props.intent,
    props.moves.map((m) => `${m.x1},${m.y1},${m.x2},${m.y2}`).join(";"),
  ],
  run,
  { immediate: true }
);

onUnmounted(reset);
</script>

<template>
  <div v-if="enabled" class="mobile-analysis">
    <div v-if="score" class="analysis" data-test="mobile-score">
      <div class="score-row">
        <span class="score-text">{{ scoreText }}</span>
        <div v-if="analysis.scoreRed !== null" class="score-bar">
          <div class="score-bar-fill" :style="{ width: barWidth + '%' }"></div>
        </div>
      </div>
      <p class="analysis-status" data-test="mobile-analysis-status">{{ statusText }}</p>
      <ol v-if="analysis.results.length" class="analysis-history">
        <li v-for="r in analysis.results" :key="r.depth" data-test="mobile-analysis-item">
          <span class="depth">第 {{ r.depth }} 层</span>
          <span class="score">{{ formatScore(r.score_red, r.mate) }}</span>
          <span class="time">{{ r.time_ms }}ms</span>
          <span class="line">{{ pvText(r) }}</span>
        </li>
      </ol>
    </div>
    <IntentPanel v-if="intent && intent.status !== 'idle'" :intent="intent" />
  </div>
</template>

<style scoped>
.mobile-analysis {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.analysis {
  background: #faf6ee;
  border: 1px solid #e6ddcc;
  border-radius: 10px;
  padding: 12px;
}

.score-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.score-text {
  font-weight: 600;
  white-space: nowrap;
}

.score-bar {
  flex: 1;
  height: 8px;
  border-radius: 4px;
  background: #e05252;
  overflow: hidden;
}

.score-bar-fill {
  height: 100%;
  border-radius: 4px;
  background: linear-gradient(90deg, #7fb0ff, #2563eb);
  transition: width 0.2s ease;
}

.analysis-status {
  margin: 6px 0 0;
  font-size: 13px;
  color: #6b5b45;
}

.analysis-history {
  list-style: none;
  margin: 8px 0 0;
  padding: 0;
  max-height: 96px;
  overflow: auto;
  -webkit-overflow-scrolling: touch;
  font-size: 13px;
}

.analysis-history li {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 2px 8px;
  height: 48px;
  padding: 4px 0;
  overflow: hidden;
  border-top: 1px solid #e9dfcd;
}

.analysis-history li:first-child {
  border-top: 0;
}

.analysis-history .depth {
  font-weight: 600;
}

.analysis-history .line {
  flex: 1 1 100%;
  color: #4a3a28;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.analysis-history .time {
  margin-left: auto;
  color: #8a7a63;
}
</style>
