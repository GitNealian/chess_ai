<template>
  <section>
    <div class="toolbar">
      <input v-model="keyword" placeholder="搜索棋谱名" @input="reload(true)" />
      <input v-model="category" placeholder="按分类筛选" @input="reload(true)" />
      <router-link to="/editor" class="btn primary">新建棋谱</router-link>
      <router-link to="/play" class="btn">新对局</router-link>
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
          <td data-label="名称">{{ game.name }}</td>
          <td data-label="分类">{{ game.category }}</td>
          <td data-label="背谱阵营">{{ sideText(game.practice_side) }}</td>
          <td data-label="掌握度">{{ masteryText(game) }}</td>
          <td data-label="下次复习">{{ dueText(game) }}</td>
          <td class="actions" data-label="操作">
            <router-link :to="`/practice/${game.id}`">打谱</router-link>
            <router-link :to="`/editor/${game.id}`">编辑</router-link>
            <router-link :to="`/review?game=${game.id}`">默写</router-link>
            <button @click="onRemove(game.id)">删除</button>
          </td>
        </tr>
      </tbody>
    </table>
    <div v-if="store.total > store.pageSize" class="pager">
      <button data-test="prev-page" :disabled="page <= 1" @click="changePage(page - 1)">上一页</button>
      <span data-test="page-info">第 {{ page }} / {{ totalPages }} 页 · 共 {{ store.total }} 条</span>
      <button data-test="next-page" :disabled="page >= totalPages" @click="changePage(page + 1)">下一页</button>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { useLibraryStore } from "../stores/library";

const store = useLibraryStore();
const keyword = ref("");
const category = ref("");
const page = ref(1);
const totalPages = computed(() => Math.max(1, Math.ceil(store.total / store.pageSize)));

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

function reload(resetPage = false) {
  if (resetPage) page.value = 1;
  store.page = page.value;
  store.fetchGames({ keyword: keyword.value || undefined, category: category.value || undefined });
}

function changePage(next) {
  if (next < 1 || next > totalPages.value) return;
  page.value = next;
  reload();
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
.toolbar { display: flex; flex-direction: column; gap: 12px; margin-bottom: 16px; }
input {
  width: 100%;
  min-height: 44px;
  padding: 10px 12px;
  border: 1px solid #cbb89a;
  border-radius: 6px;
  font: inherit;
}
.btn {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 44px;
  padding: 10px 16px;
  border-radius: 6px;
  text-decoration: none;
  background: #7a3b2e;
  color: #fff;
}
.stats { display: flex; flex-wrap: wrap; gap: 8px 20px; margin-bottom: 12px; color: #6b5a45; }

/* 移动端默认：表格卡片化 */
.list { width: 100%; border-collapse: collapse; background: #fff; }
.list, .list tbody { display: block; }
.list thead { display: none; }
.list tr {
  display: block;
  margin-bottom: 12px;
  border: 1px solid #e5dcc9;
  border-radius: 8px;
  padding: 8px;
  background: #fff;
}
.list td {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  border: none;
  padding: 8px;
  text-align: right;
  overflow-wrap: anywhere;
}
.list td::before {
  content: attr(data-label);
  color: #6b5a45;
  font-weight: 600;
  text-align: left;
}
.list td.actions { justify-content: flex-end; }
.list td.actions::before { margin-right: auto; }
.actions { display: flex; gap: 12px; flex-wrap: wrap; }
.actions button { border: none; background: none; color: #b32020; cursor: pointer; }
.actions a, .actions button {
  display: inline-flex;
  align-items: center;
  min-height: 44px;
  padding: 8px 12px;
}
.pager {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  margin-top: 16px;
  color: #6b5a45;
}
.pager button {
  min-height: 44px;
  padding: 8px 16px;
  border: 1px solid #cbb89a;
  border-radius: 6px;
  background: #fff;
  font: inherit;
  cursor: pointer;
}
.pager button:disabled { opacity: 0.45; cursor: default; }

/* 桌面端：恢复适配前的横向工具栏与表格布局 */
@media (min-width: 768px) {
  .toolbar { flex-direction: row; }
  input { width: auto; min-height: 0; padding: 8px 10px; font-size: 13.3333px; }
  .btn { display: inline-block; min-height: 0; padding: 8px 16px; }
  .stats { gap: 20px; }

  .list { display: table; }
  .list tbody { display: table-row-group; }
  .list thead { display: table-header-group; }
  .list tr { display: table-row; margin: 0; border: 0; border-radius: 0; padding: 0; }
  .list th, .list td { display: table-cell; padding: 10px; border-bottom: 1px solid #eee; text-align: left; }
  .list td::before { content: none; }
  .list td.actions { display: flex; }
  .actions { flex-wrap: nowrap; }
  .actions a, .actions button { display: inline; min-height: 0; padding: 0; }
}
</style>
