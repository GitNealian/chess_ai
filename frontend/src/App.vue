<template>
  <router-view />
  <div v-if="toast" class="toast">{{ toast }}</div>
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

@media (max-width: 767px) {
  input, select, textarea, button { font-size: 16px; }
}

.toast {
  position: fixed;
  bottom: calc(24px + env(safe-area-inset-bottom, 0px));
  left: 50%;
  transform: translateX(-50%);
  z-index: 200;
  background: #333;
  color: #fff;
  padding: 10px 20px;
  border-radius: 6px;
}
</style>
