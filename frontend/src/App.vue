<template>
  <div class="app">
    <header class="topbar">
      <router-link to="/library" class="brand">象棋记谱</router-link>
      <nav>
        <router-link to="/library">棋谱库</router-link>
        <router-link to="/editor">录入</router-link>
        <router-link to="/review">默写复习</router-link>
      </nav>
    </header>
    <main><router-view /></main>
    <div v-if="toast" class="toast">{{ toast }}</div>
  </div>
</template>

<script setup>
import { onMounted, ref } from "vue";

const toast = ref("");
onMounted(() => {
  window.addEventListener("app-toast", (event) => {
    toast.value = event.detail;
    setTimeout(() => (toast.value = ""), 3000);
  });
});
</script>

<style>
body { margin: 0; font-family: system-ui, "PingFang SC", sans-serif; background: #f5f2ea; }
.topbar { display: flex; align-items: center; gap: 24px; padding: 12px 24px; background: #7a3b2e; color: #fff; }
.topbar a { color: #f4e3c1; text-decoration: none; margin-right: 12px; }
.brand { font-weight: 700; font-size: 18px; color: #fff !important; }
main { max-width: 1080px; margin: 0 auto; padding: 24px; }
.toast { position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%); background: #333; color: #fff; padding: 10px 20px; border-radius: 6px; }
</style>
