<script setup>
const props = defineProps({
  branches: { type: Array, default: () => [] },
  plies: { type: Object, default: null },
});

const emit = defineEmits(["select", "cancel"]);

function label(branch) {
  const move = branch.move || {};
  if (move.chinese) return move.chinese;
  return `${move.x1},${move.y1} → ${move.x2},${move.y2}`;
}

function gameNames(branch) {
  return (branch.games || []).map((g) => g.name).join("、");
}

function isEnd(branch) {
  return (branch.end_games || []).length > 0;
}

const range = () => {
  if (!props.plies) return "";
  return props.plies.min === props.plies.max
    ? `${props.plies.min} 着`
    : `${props.plies.min}~${props.plies.max} 着`;
};
</script>

<template>
  <div class="variation-mask" data-test="variation-mask" @click.self="emit('cancel')">
    <div class="variation-card" data-test="variation-card">
      <h3 class="variation-title">选择变着</h3>
      <p class="variation-hint" data-test="variation-plies">该局面在经过 {{ range() }}</p>
      <ul class="variation-list">
        <li v-for="(branch, index) in branches" :key="index">
          <button
            type="button"
            class="variation-item"
            :data-variation="index"
            @click="emit('select', branch)"
          >
            <span class="variation-name">
              {{ label(branch) }}
              <span v-if="isEnd(branch)" class="variation-end">（末步）</span>
            </span>
            <span class="variation-sub">{{ gameNames(branch) }}</span>
          </button>
        </li>
      </ul>
      <div class="variation-actions">
        <button type="button" data-test="variation-cancel" @click="emit('cancel')">取消</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.variation-mask {
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

.variation-card {
  width: 100%;
  max-width: 420px;
  max-height: calc(100vh - 32px);
  margin: auto;
  background: #faf6ee;
  border-radius: 12px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.variation-title {
  margin: 0;
}

.variation-hint {
  margin: 0;
  color: #6b5a45;
  font-size: 13px;
}

.variation-list {
  list-style: none;
  margin: 0;
  padding: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.variation-item {
  width: 100%;
  min-height: 52px;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  padding: 8px 12px;
  border: 1px solid #cbb89a;
  border-radius: 8px;
  background: #fff;
  cursor: pointer;
  text-align: left;
}

.variation-name {
  color: #7a3b2e;
  font-size: 16px;
}

.variation-end {
  color: #8a7a63;
  font-size: 12px;
}

.variation-sub {
  color: #8a7a63;
  font-size: 12px;
}

.variation-actions {
  display: flex;
}

.variation-actions button {
  flex: 1;
  min-height: 44px;
  border: 1px solid #cbb89a;
  border-radius: 6px;
  background: #fff;
  color: #7a3b2e;
  cursor: pointer;
}
</style>
