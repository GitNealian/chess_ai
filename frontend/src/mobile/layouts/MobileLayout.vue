<template>
  <div class="mobile-app">
    <header class="mobile-topbar">
      <span class="mobile-brand">象棋记谱</span>
      <span class="mobile-subtitle">移动版</span>
    </header>
    <main class="mobile-main">
      <router-view />
    </main>
    <nav class="mobile-tabbar">
      <router-link to="/m" class="mobile-tab">首页</router-link>
    </nav>
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
  padding-bottom: calc(72px + env(safe-area-inset-bottom, 0px));
}

.mobile-tabbar {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 100;
  display: flex;
  background: #fff;
  border-top: 1px solid #e5dcc9;
  padding-bottom: env(safe-area-inset-bottom, 0px);
}

.mobile-tab {
  flex: 1;
  min-height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #6b5a45;
  text-decoration: none;
  font-size: 16px;
}

.mobile-tab.router-link-active {
  color: #7a3b2e;
  font-weight: 600;
}
</style>
