<script setup>
import { ref, watch } from "vue";

const props = defineProps({
  page: { type: Number, required: true },
  pageSize: { type: Number, default: 20 },
  total: { type: Number, required: true },
});
const emit = defineEmits(["change"]);
const input = ref(String(props.page));

watch(
  () => props.page,
  (value) => {
    input.value = String(value);
  }
);

const totalPages = () => Math.max(1, Math.ceil(props.total / props.pageSize));

function jump() {
  const value = Number(input.value);
  if (!Number.isInteger(value)) {
    input.value = String(props.page);
    return;
  }
  const target = Math.min(Math.max(value, 1), totalPages());
  input.value = String(target);
  if (target !== props.page) emit("change", target);
}
</script>

<template>
  <div class="pager">
    <button
      type="button"
      class="pager-btn"
      data-test="pager-prev"
      :disabled="page <= 1"
      @click="emit('change', page - 1)"
    >
      上一页
    </button>
    <div class="pager-jump">
      <input
        v-model="input"
        class="pager-input"
        data-test="pager-input"
        inputmode="numeric"
        @keyup.enter="jump"
      />
      <span class="pager-total">/ {{ totalPages() }}</span>
      <button type="button" class="pager-go" data-test="pager-go" @click="jump">跳转</button>
    </div>
    <button
      type="button"
      class="pager-btn"
      data-test="pager-next"
      :disabled="page >= totalPages()"
      @click="emit('change', page + 1)"
    >
      下一页
    </button>
  </div>
</template>

<style scoped>
.pager {
  display: flex;
  align-items: center;
  gap: 6px;
}

.pager-btn {
  flex: 0 0 auto;
  min-height: 40px;
  padding: 0 10px;
  white-space: nowrap;
  border: 1px solid #cbb89a;
  border-radius: 6px;
  background: #fff;
  color: #7a3b2e;
  cursor: pointer;
}

.pager-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.pager-jump {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}

.pager-input {
  width: 48px;
  flex: 0 0 auto;
  min-height: 40px;
  text-align: center;
  border: 1px solid #cbb89a;
  border-radius: 6px;
  font: inherit;
}

.pager-total {
  white-space: nowrap;
  color: #6b5a45;
  font-size: 13px;
}

.pager-go {
  flex: 0 0 auto;
  min-height: 40px;
  padding: 0 10px;
  white-space: nowrap;
  border: 1px solid #cbb89a;
  border-radius: 6px;
  background: #fff;
  color: #7a3b2e;
  cursor: pointer;
}
</style>
