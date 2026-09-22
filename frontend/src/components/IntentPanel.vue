<script setup>
import { computed } from "vue";

const props = defineProps({
  intent: { type: Object, required: true },
});

const lineText = (line) => (line || []).map((m) => m.chinese || m.iccs).join(" → ");

function outcomeText(outcome) {
  if (!outcome) return "";
  if (outcome.mate !== null && outcome.mate !== undefined) {
    return `绝杀（${outcome.mate} 步内）`;
  }
  if (outcome.loss_piece) return `白丢${outcome.loss_piece}`;
  const score = outcome.score_red;
  if (score === null || score === undefined) return "";
  if (Math.abs(score) < 1) return "均势";
  const value = Math.abs(score);
  return score > 0 ? `红优 +${value}` : `黑优 ${value}`;
}

const threat = computed(() => props.intent?.threat ?? null);

const hintText = computed(() => {
  if (props.intent?.status !== "done") return "";
  return threat.value?.hint || "";
});

const threatText = computed(() => {
  if (props.intent?.status !== "done") return "";
  if (threat.value?.hint) return "";
  const line = threat.value?.line || [];
  if (!line.length) return "";
  return `若不理会：${lineText(line)}`;
});

const threatOutcome = computed(() => {
  if (!threatText.value) return "";
  return outcomeText(threat.value?.outcome);
});

const baitItems = computed(() => {
  if (props.intent?.status !== "done") return [];
  return (props.intent?.baits || []).map((b) => ({
    text: `若你走 ${b.bait?.chinese}（${b.bait?.reason}）：${lineText(b.line)}`,
    outcome: outcomeText(b.outcome),
  }));
});

const bestText = computed(() => {
  if (props.intent?.status !== "done") return "";
  const best = props.intent?.rank?.best;
  return best ? `正着参考：${best.chinese || best.iccs}` : "";
});
</script>

<template>
  <div class="intent-panel" data-test="intent-panel">
    <p v-if="intent.status === 'running'" class="intent-status" data-test="intent-status">
      推演中…
    </p>
    <p v-else-if="intent.status === 'error'" class="intent-status" data-test="intent-error">
      推演失败：{{ intent.error || "请稍后重试" }}
    </p>
    <template v-else-if="intent.status === 'done'">
      <p v-if="hintText" class="intent-item intent-hint" data-test="intent-hint">{{ hintText }}</p>
      <p
        v-else-if="!hintText && !threatText && !baitItems.length && !bestText"
        class="intent-status"
        data-test="intent-empty"
      >
        本次推演无结果
      </p>
      <p v-if="threatText" class="intent-item" data-test="intent-threat">
        {{ threatText }}
        <span v-if="threatOutcome" class="outcome">{{ threatOutcome }}</span>
      </p>
      <p v-for="(b, i) in baitItems" :key="i" class="intent-item" data-test="intent-bait">
        {{ b.text }}
        <span v-if="b.outcome" class="outcome">{{ b.outcome }}</span>
      </p>
      <p v-if="bestText" class="intent-item intent-best" data-test="intent-best">{{ bestText }}</p>
    </template>
  </div>
</template>

<style scoped>
.intent-panel {
  background: #faf6ee;
  border: 1px solid #e6ddcc;
  border-radius: 10px;
  padding: 12px;
}

.intent-status {
  margin: 0;
  font-size: 13px;
  color: #6b5b45;
}

.intent-item {
  margin: 6px 0 0;
  font-size: 13px;
  color: #4a3a28;
  word-break: break-all;
}

.intent-item:first-child {
  margin-top: 0;
}

.intent-hint {
  color: #b45309;
}

.intent-best {
  font-weight: 600;
}

.outcome {
  color: #b45309;
}
</style>
