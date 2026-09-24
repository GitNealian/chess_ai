<template>
  <section class="login">
    <h1>象棋记谱</h1>
    <form @submit.prevent="onSubmit">
      <input
        v-model="password"
        type="password"
        placeholder="密码"
        autocomplete="current-password"
        autofocus
        data-test="password"
      />
      <button type="submit" :disabled="auth.loading || !password" data-test="submit">登录</button>
      <p v-if="error" class="error" data-test="error">{{ error }}</p>
    </form>
  </section>
</template>

<script setup>
import { ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();
const router = useRouter();
const route = useRoute();
const password = ref("");
const error = ref("");

async function onSubmit() {
  error.value = "";
  try {
    await auth.login(password.value);
    const raw = route.query.redirect;
    const redirect =
      typeof raw === "string" && raw.startsWith("/") && !raw.startsWith("//")
        ? raw
        : "/library";
    router.replace(redirect);
  } catch (err) {
    error.value = err?.response?.data?.detail || err?.response?.data?.error || "登录失败";
  }
}
</script>

<style scoped>
.login { min-height: 70vh; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 16px; }
h1 { color: #7a3b2e; }
form { display: flex; flex-direction: column; gap: 12px; width: min(320px, 90vw); }
input { padding: 10px 12px; border: 1px solid #e5dcc9; border-radius: 6px; font-size: 16px; }
button { padding: 10px; background: #7a3b2e; color: #fff; border: 0; border-radius: 6px; font-size: 16px; cursor: pointer; }
button:disabled { opacity: 0.5; }
.error { color: #b00020; margin: 0; }
</style>
