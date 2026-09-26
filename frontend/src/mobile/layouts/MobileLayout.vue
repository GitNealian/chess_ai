<template>
  <div class="mobile-app">
    <header class="mobile-topbar">
      <span class="mobile-brand">象棋记谱</span>
      <span class="mobile-subtitle">移动版</span>
      <div class="mobile-topbar-actions">
        <button
          type="button"
          class="topbar-icon"
          data-test="header-open"
          aria-label="打开棋谱"
          title="打开棋谱"
          @click="publish('mobile-open')"
        >
          <svg
            viewBox="0 0 24 24"
            width="22"
            height="22"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
          </svg>
        </button>
        <button
          type="button"
          class="topbar-icon"
          data-test="header-settings"
          aria-label="设置"
          title="设置"
          @click="publish('mobile-settings')"
        >
          <svg
            viewBox="0 0 24 24"
            width="22"
            height="22"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <circle cx="12" cy="12" r="3.2" />
            <path
              d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09a1.65 1.65 0 0 0-1.08-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"
            />
          </svg>
        </button>
      </div>
    </header>
    <main class="mobile-main">
      <router-view />
    </main>
  </div>
</template>

<script setup>
function publish(name) {
  window.dispatchEvent(new CustomEvent(name));
}
</script>

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
  align-items: center;
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

.mobile-topbar-actions {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 4px;
}

.topbar-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  padding: 0;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: #f4e3c1;
  cursor: pointer;
}

.topbar-icon:active {
  color: #fff;
  background: rgba(255, 255, 255, 0.12);
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
