<template>
  <div class="app">
    <header class="topbar">
      <router-link to="/library" class="brand">象棋记谱</router-link>
      <nav class="topnav">
        <router-link to="/library">棋谱库</router-link>
        <router-link to="/editor">录入</router-link>
        <router-link to="/review">默写复习</router-link>
      </nav>
    </header>
    <main><router-view /></main>
    <nav class="tabbar">
      <router-link to="/library" class="tab">棋谱库</router-link>
      <router-link to="/editor" class="tab">录入</router-link>
      <router-link to="/review" class="tab">复习</router-link>
    </nav>
    <div v-if="toast" class="toast">{{ toast }}</div>
  </div>
</template>

<script setup>
import { onMounted, onUnmounted, ref } from "vue";

const toast = ref("");
let timer = null;

function onToast(event) {
  toast.value = event.detail;
  if (timer) clearTimeout(timer);
  timer = setTimeout(() => (toast.value = ""), 3000);
}

onMounted(() => window.addEventListener("app-toast", onToast));
onUnmounted(() => {
  window.removeEventListener("app-toast", onToast);
  if (timer) clearTimeout(timer);
});
</script>

<style>
* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body {
  margin: 0;
  font-family: system-ui, "PingFang SC", sans-serif;
  background: #f5f2ea;
  font-size: 16px;
  -webkit-tap-highlight-color: transparent;
}
a, button, input, select, textarea { touch-action: manipulation; }

.topbar { display: flex; align-items: center; gap: 24px; padding: 12px 16px; background: #7a3b2e; color: #fff; }
.topbar a { color: #f4e3c1; text-decoration: none; margin-right: 12px; }
.brand { font-weight: 700; font-size: 18px; color: #fff !important; }
.topnav { display: none; }

main {
  max-width: 1080px;
  margin: 0 auto;
  padding: 16px;
  padding-bottom: calc(72px + env(safe-area-inset-bottom));
}

.tabbar {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 100;
  display: flex;
  background: #fff;
  border-top: 1px solid #e5dcc9;
  padding-bottom: env(safe-area-inset-bottom);
}
.tab {
  flex: 1;
  min-height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #6b5a45;
  text-decoration: none;
  font-size: 16px;
}
.tab.router-link-active { color: #7a3b2e; font-weight: 600; }

.toast {
  position: fixed;
  bottom: calc(72px + env(safe-area-inset-bottom));
  left: 50%;
  transform: translateX(-50%);
  z-index: 200;
  background: #333;
  color: #fff;
  padding: 10px 20px;
  border-radius: 6px;
}

@media (min-width: 768px) {
  .topbar { padding: 12px 24px; }
  .topnav { display: flex; align-items: center; }
  main { padding: 24px; }
  .tabbar { display: none; }
  .toast { bottom: 24px; }
}
</style>
