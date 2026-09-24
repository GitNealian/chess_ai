<template>
  <section class="mobile-home">
    <div class="mobile-home__board">
      <ChessBoard :position="position" />
    </div>
    <div class="mobile-home__body">
      <h1 class="mobile-home__title">移动端界面</h1>
      <p class="mobile-home__hint">骨架已就绪，后续在此实现移动端页面。</p>
    </div>
  </section>
</template>

<script setup>
import { computed } from "vue";
import ChessBoard from "../../components/ChessBoard.vue";
import { INITIAL_FEN, fenToPieces } from "../../utils/chess";

const position = computed(() => ({ pieces: fenToPieces(INITIAL_FEN) }));
</script>

<style scoped>
.mobile-home {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.mobile-home__board {
  width: 100%;
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 2px 8px rgba(90, 61, 36, 0.18);
}

.mobile-home__body {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  text-align: center;
}

.mobile-home__title {
  margin: 0;
  font-size: 20px;
  color: #7a3b2e;
}

.mobile-home__hint {
  margin: 0;
  color: #6b5a45;
}
</style>
