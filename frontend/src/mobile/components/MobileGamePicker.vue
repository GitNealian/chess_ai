<script setup>
import { onMounted, ref } from "vue";
import { api } from "../../api";

const emit = defineEmits(["select", "cancel"]);
const loading = ref(true);
const error = ref(false);
const games = ref([]);

async function load() {
  loading.value = true;
  error.value = false;
  try {
    const data = await api.listGames({ page_size: 50 });
    games.value = data.items || [];
  } catch {
    error.value = true;
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>

<template>
  <div class="picker-mask" data-test="picker-mask" @click.self="emit('cancel')">
    <div class="picker-card" data-test="picker-card">
      <h3 class="picker-title">打开棋谱</h3>
      <p v-if="loading" class="picker-hint">加载中…</p>
      <p v-else-if="error" class="picker-hint">
        加载失败
        <button type="button" data-test="picker-retry" @click="load">重试</button>
      </p>
      <p v-else-if="games.length === 0" class="picker-hint" data-test="picker-empty">
        暂无棋谱
      </p>
      <ul v-else class="picker-list">
        <li v-for="game in games" :key="game.id">
          <button
            type="button"
            class="picker-item"
            :data-game="game.id"
            @click="emit('select', game)"
          >
            <span class="picker-name">{{ game.name }}</span>
            <span class="picker-sub">
              {{ game.red_player || "红方" }} vs {{ game.black_player || "黑方" }}
            </span>
          </button>
        </li>
      </ul>
      <div class="picker-actions">
        <button type="button" data-test="picker-cancel" @click="emit('cancel')">取消</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.picker-mask {
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

.picker-card {
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

.picker-title {
  margin: 0;
}

.picker-hint {
  margin: 0;
  color: #6b5a45;
}

.picker-list {
  list-style: none;
  margin: 0;
  padding: 0;
  max-height: 60vh;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.picker-item {
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

.picker-name {
  color: #7a3b2e;
  font-size: 16px;
}

.picker-sub {
  color: #8a7a63;
  font-size: 12px;
}

.picker-actions {
  display: flex;
}

.picker-actions button {
  flex: 1;
  min-height: 44px;
  border: 1px solid #cbb89a;
  border-radius: 6px;
  background: #fff;
  color: #7a3b2e;
  cursor: pointer;
}
</style>
