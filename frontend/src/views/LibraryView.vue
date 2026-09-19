<template>
  <section>
    <div class="toolbar">
      <input v-model="keyword" placeholder="搜索棋谱名" @input="reload" />
      <input v-model="category" placeholder="按分类筛选" @input="reload" />
      <router-link to="/editor" class="btn primary">新建棋谱</router-link>
    </div>
    <div v-if="store.stats" class="stats">
      <span>共 {{ store.stats.total }}</span>
      <span>待复习 {{ store.stats.due }}</span>
      <span>已掌握 {{ store.stats.mastered }}</span>
    </div>
    <p v-if="store.loading">加载中…</p>
    <p v-else-if="store.games.length === 0">暂无棋谱，点击「新建棋谱」开始。</p>
    <table v-else class="list">
      <thead>
        <tr><th>名称</th><th>分类</th><th>背谱阵营</th><th>掌握度</th><th>下次复习</th><th>操作</th></tr>
      </thead>
      <tbody>
        <tr v-for="game in store.games" :key="game.id">
          <td>{{ game.name }}</td>
          <td>{{ game.category }}</td>
          <td>{{ sideText(game.practice_side) }}</td>
          <td>{{ masteryText(game) }}</td>
          <td>{{ dueText(game) }}</td>
          <td class="actions">
            <router-link :to="`/practice/${game.id}`">打谱</router-link>
            <router-link :to="`/editor/${game.id}`">编辑</router-link>
            <router-link :to="`/review?game=${game.id}`">默写</router-link>
            <button @click="onRemove(game.id)">删除</button>
          </td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<script setup>
import { onMounted, ref } from "vue";
import { useLibraryStore } from "../stores/library";

const store = useLibraryStore();
const keyword = ref("");
const category = ref("");

function sideText(side) {
  return { red: "红方", black: "黑方", both: "双方" }[side] || side;
}

function masteryText(game) {
  if (!game.review) return "新";
  return game.review.repetitions >= 3 ? "已掌握" : "学习中";
}

function dueText(game) {
  return game.review ? game.review.due_date : "今日";
}

function reload() {
  store.fetchGames({ keyword: keyword.value || undefined, category: category.value || undefined });
}

async function onRemove(id) {
  if (!window.confirm("确定删除该棋谱？")) return;
  try {
    await store.remove(id);
    await store.fetchStats();
  } catch (error) {
    // api 拦截器已 toast，无需额外处理
  }
}

onMounted(async () => {
  reload();
  await store.fetchStats();
});
</script>

<style scoped>
.toolbar { display: flex; gap: 12px; margin-bottom: 16px; }
input { padding: 8px 10px; border: 1px solid #cbb89a; border-radius: 6px; }
.btn { padding: 8px 16px; border-radius: 6px; text-decoration: none; background: #7a3b2e; color: #fff; }
.stats { display: flex; gap: 20px; margin-bottom: 12px; color: #6b5a45; }
.list { width: 100%; border-collapse: collapse; background: #fff; }
.list th, .list td { padding: 10px; border-bottom: 1px solid #eee; text-align: left; }
.actions { display: flex; gap: 12px; }
.actions button { border: none; background: none; color: #b32020; cursor: pointer; }
</style>
