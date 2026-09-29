<script setup>
import { ref, watch } from "vue";
import { api } from "../../api";
import MobilePager from "./MobilePager.vue";

const emit = defineEmits(["select", "cancel"]);
const PAGE_SIZE = 20;

const view = ref("menu");
const scope = ref("tournament");
const collection = ref("");
const event = ref("");
const page = ref(1);
const total = ref(0);
const items = ref([]);
const loading = ref(false);
const error = ref(false);

async function load() {
  loading.value = true;
  error.value = false;
  try {
    if (view.value === "collections") {
      const data = await api.listCollections({ page: page.value, page_size: PAGE_SIZE });
      items.value = data.items || [];
      total.value = data.total || 0;
    } else if (view.value === "events") {
      const data = await api.listEvents({ page: page.value, page_size: PAGE_SIZE });
      items.value = data.items || [];
      total.value = data.total || 0;
    } else if (view.value === "review") {
      const data = await api.reviewQueue({ limit: 200 });
      items.value = data.items || [];
      total.value = items.value.length;
    } else if (view.value === "games") {
      const data = await api.listGames({
        scope: scope.value,
        collection: collection.value || undefined,
        event: event.value || undefined,
        sort: "created_desc",
        page: page.value,
        page_size: PAGE_SIZE,
      });
      items.value = data.items || [];
      total.value = data.total || 0;
    }
  } catch {
    error.value = true;
  } finally {
    loading.value = false;
  }
}

watch([view, page], () => {
  if (view.value !== "menu") load();
});

function openCategory(name) {
  collection.value = "";
  event.value = "";
  page.value = 1;
  if (name === "collection") {
    scope.value = "collection";
    view.value = "collections";
  } else if (name === "tournament") {
    scope.value = "tournament";
    view.value = "events";
  } else if (name === "review") {
    scope.value = "review";
    view.value = "review";
  } else {
    scope.value = name;
    view.value = "games";
  }
}

function openCollection(name) {
  scope.value = "collection";
  collection.value = name;
  page.value = 1;
  view.value = "games";
}

function openEvent(name) {
  scope.value = "event";
  event.value = name;
  page.value = 1;
  view.value = "games";
}

function back() {
  if (view.value === "games" && scope.value === "collection") {
    view.value = "collections";
  } else if (view.value === "games" && scope.value === "event") {
    view.value = "events";
  } else {
    view.value = "menu";
  }
  page.value = 1;
}

function gamesSource() {
  return {
    type: scope.value,
    collection: collection.value || undefined,
    event: event.value || undefined,
  };
}

function selectGame(item) {
  emit("select", item, gamesSource());
}

function selectReview(entry) {
  emit("select", entry.game, { type: "review" });
}

function reviewMeta(entry) {
  return entry.is_new ? "新" : `到期 ${entry.due_date}`;
}

const title = () => {
  if (view.value === "collections") return "棋谱集";
  if (view.value === "events") return "赛事";
  if (view.value === "review") return "复习";
  if (view.value === "games") {
    if (scope.value === "collection") return collection.value;
    if (scope.value === "event") return event.value;
    if (scope.value === "tournament") return "赛事";
    if (scope.value === "recent") return "最近";
    if (scope.value === "favorite") return "收藏";
    return "其它";
  }
  return "打开棋谱";
};
</script>

<template>
  <div class="picker-mask" data-test="picker-mask" @click.self="emit('cancel')">
    <div class="picker-card" data-test="picker-card">
      <div class="picker-head">
        <button
          v-if="view !== 'menu'"
          type="button"
          class="picker-back"
          data-test="picker-back"
          @click="back"
        >
          返回
        </button>
        <h3 class="picker-title">{{ title() }}</h3>
      </div>

      <div v-if="view === 'menu'" class="picker-menu">
        <button type="button" class="picker-menu-btn" data-test="menu-collection" @click="openCategory('collection')">
          棋谱
        </button>
        <button type="button" class="picker-menu-btn" data-test="menu-tournament" @click="openCategory('tournament')">
          赛事
        </button>
        <button type="button" class="picker-menu-btn" data-test="menu-review" @click="openCategory('review')">
          复习
        </button>
        <button type="button" class="picker-menu-btn" data-test="menu-other" @click="openCategory('other')">
          其它
        </button>
        <button type="button" class="picker-menu-btn" data-test="menu-recent" @click="openCategory('recent')">
          最近
        </button>
        <button type="button" class="picker-menu-btn" data-test="menu-favorite" @click="openCategory('favorite')">
          收藏
        </button>
        <button type="button" class="picker-menu-btn" data-test="picker-cancel" @click="emit('cancel')">
          返回
        </button>
      </div>

      <template v-else>
        <p v-if="loading" class="picker-hint">加载中…</p>
        <p v-else-if="error" class="picker-hint">
          加载失败
          <button type="button" data-test="picker-retry" @click="load">重试</button>
        </p>
        <p v-else-if="items.length === 0" class="picker-hint" data-test="picker-empty">
          暂无棋谱
        </p>
        <ul v-else class="picker-list">
          <template v-if="view === 'collections'">
            <li v-for="item in items" :key="item.name">
              <button
                type="button"
                class="picker-item"
                :data-collection="item.name"
                @click="openCollection(item.name)"
              >
                <span class="picker-name">{{ item.name }}</span>
                <span class="picker-sub">{{ item.count }} 局</span>
              </button>
            </li>
          </template>
          <template v-else-if="view === 'events'">
            <li v-for="item in items" :key="item.name">
              <button
                type="button"
                class="picker-item"
                :data-event="item.name"
                @click="openEvent(item.name)"
              >
                <span class="picker-name">{{ item.name }}</span>
                <span class="picker-sub">{{ item.count }} 局</span>
              </button>
            </li>
          </template>
          <template v-else-if="view === 'review'">
            <li v-for="entry in items" :key="entry.game.id">
              <button
                type="button"
                class="picker-item"
                :data-review="entry.game.id"
                @click="selectReview(entry)"
              >
                <span class="picker-name">{{ entry.game.name }}</span>
                <span class="picker-sub">
                  {{ entry.game.red_player || "红方" }} vs {{ entry.game.black_player || "黑方" }} ·
                  {{ reviewMeta(entry) }}
                </span>
              </button>
            </li>
          </template>
          <template v-else>
            <li v-for="item in items" :key="item.id">
              <button
                type="button"
                class="picker-item"
                :data-game="item.id"
                @click="selectGame(item)"
              >
                <span class="picker-name">{{ item.name }}</span>
                <span class="picker-sub">
                  {{ item.red_player || "红方" }} vs {{ item.black_player || "黑方" }}
                </span>
              </button>
            </li>
          </template>
        </ul>
      </template>

      <MobilePager
        v-if="view !== 'menu' && !error"
        :page="page"
        :page-size="PAGE_SIZE"
        :total="total"
        @change="page = $event"
      />
    </div>
  </div>
</template>

<style scoped>
.picker-mask {
  position: fixed;
  inset: 0;
  z-index: 200;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding: 16px;
  overflow-y: auto;
}

.picker-card {
  width: 100%;
  max-width: 420px;
  height: min(520px, calc(100vh - 32px));
  margin: auto;
  background: #faf6ee;
  border-radius: 12px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.picker-head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.picker-back {
  flex: 0 0 auto;
  min-height: 36px;
  padding: 4px 12px;
  white-space: nowrap;
  border: 1px solid #cbb89a;
  border-radius: 6px;
  background: #fff;
  color: #7a3b2e;
  cursor: pointer;
}

.picker-title {
  flex: 1;
  min-width: 0;
  margin: 0;
}

.picker-menu {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  gap: 10px;
  padding: 16px 0;
}

.picker-menu-btn {
  width: 70%;
  min-height: 52px;
  border: 1px solid #cbb89a;
  border-radius: 8px;
  background: #fff;
  color: #7a3b2e;
  font-size: 18px;
  cursor: pointer;
}

.picker-hint {
  margin: 0;
  color: #6b5a45;
}

.picker-list {
  list-style: none;
  margin: 0;
  padding: 0;
  flex: 1;
  min-height: 120px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.picker-item {
  width: 100%;
  min-height: 52px;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  padding: 8px 12px;
  border: 1px solid #cbb89a;
  border-radius: 8px;
  background: #fff;
  cursor: pointer;
  text-align: left;
}

.picker-name {
  color: #7a3b2e;
  font-size: 16px;
}

.picker-sub {
  color: #8a7a63;
  font-size: 12px;
}
</style>
