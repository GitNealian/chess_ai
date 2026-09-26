<template>
  <div class="mobile-app">
    <header class="mobile-topbar">
      <span class="mobile-brand">象棋记谱</span>
      <span class="mobile-subtitle">移动版</span>
    </header>
    <main class="mobile-main">
      <router-view />
    </main>
  </div>
</template>

<script setup></script>

<style scoped>
.mobile-app {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.mobile-topbar {
  position: sticky;
  top: 0;
  z-index: 100;
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 12px 16px;
  padding-top: calc(12px + env(safe-area-inset-top, 0px));
  background: #7a3b2e;
  color: #fff;
}

.mobile-brand {
  font-weight: 700;
  font-size: 18px;
}

.mobile-subtitle {
  font-size: 12px;
  color: #f4e3c1;
}

.mobile-main {
  flex: 1;
  width: 100%;
  max-width: none;
  margin: 0;
  padding: 16px;
  padding-bottom: calc(16px + env(safe-area-inset-bottom, 0px));
}
</style>
