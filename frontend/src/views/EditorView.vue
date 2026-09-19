<template>
  <section class="editor">
    <div class="board-area">
      <ChessBoard :position="{ pieces }" :selected="selected" @cell-click="onCellClick" />
      <div class="board-tools">
        <button @click="undo">悔棋</button>
        <button @click="startFromInitial">标准开局</button>
      </div>
      <ol class="moves">
        <li v-for="(move, index) in moves" :key="index">{{ describe(move, index) }}</li>
      </ol>
    </div>

    <div class="form-area">
      <h2>{{ gameId ? "编辑棋谱" : "新建棋谱" }}</h2>
      <label>名称<input v-model="form.name" /></label>
      <label>分类<input v-model="form.category" /></label>
      <label>红方<input v-model="form.red_player" /></label>
      <label>黑方<input v-model="form.black_player" /></label>
      <label>赛事<input v-model="form.event" /></label>
      <label>结果<input v-model="form.result" /></label>
      <label>
        背谱阵营
        <select v-model="form.practice_side">
          <option value="both">双方</option>
          <option value="red">红方</option>
          <option value="black">黑方</option>
        </select>
      </label>

      <fieldset>
        <legend>文本解析</legend>
        <textarea
          v-model="textInput"
          rows="3"
          placeholder="炮二平五 炮8平5 或 h2e2 h7e7"
        ></textarea>
        <button @click="parseText">解析预览</button>
      </fieldset>

      <fieldset>
        <legend>PGN 导入</legend>
        <textarea v-model="pgnInput" rows="4" placeholder="粘贴 PGN 内容"></textarea>
        <button @click="importPgn">导入入库</button>
      </fieldset>

      <button class="save" @click="save">保存棋谱</button>
    </div>
  </section>
</template>

<script setup>
import { onMounted, reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import ChessBoard from "../components/ChessBoard.vue";
import { api } from "../api";
import { applyMove, fenToPieces } from "../utils/chess";

const INITIAL_FEN = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1";

const route = useRoute();
const router = useRouter();

const gameId = ref(route.params.id ? Number(route.params.id) : null);
const pieces = ref(fenToPieces(INITIAL_FEN));
const moves = ref([]);
const selected = ref(null);
const initialFen = ref(INITIAL_FEN);
const textInput = ref("");
const pgnInput = ref("");
const form = reactive({
  name: "",
  category: "",
  red_player: "",
  black_player: "",
  event: "",
  result: "",
  practice_side: "both",
});

function describe(move, index) {
  return `${index + 1}. (${move.x1},${move.y1})→(${move.x2},${move.y2})`;
}

function rebuildBoard() {
  let board = fenToPieces(initialFen.value);
  for (const move of moves.value) board = applyMove(board, move);
  pieces.value = board;
}

function onCellClick(x, y) {
  if (!selected.value) {
    if (pieces.value.some((p) => p.x === x && p.y === y)) selected.value = { x, y };
    return;
  }
  if (selected.value.x === x && selected.value.y === y) {
    selected.value = null;
    return;
  }
  const target = pieces.value.find((p) => p.x === x && p.y === y);
  const moving = pieces.value.find((p) => p.x === selected.value.x && p.y === selected.value.y);
  if (target && moving && target.side === moving.side) {
    selected.value = { x, y };
    return;
  }
  const move = { x1: selected.value.x, y1: selected.value.y, x2: x, y2: y };
  pieces.value = applyMove(pieces.value, move);
  moves.value.push(move);
  selected.value = null;
}

function undo() {
  if (moves.value.length === 0) return;
  moves.value.pop();
  selected.value = null;
  rebuildBoard();
}

function startFromInitial() {
  moves.value = [];
  selected.value = null;
  rebuildBoard();
}

async function parseText() {
  try {
    const data = await api.parse({ text: textInput.value, initial_fen: initialFen.value });
    moves.value = data.moves;
    selected.value = null;
    rebuildBoard();
  } catch (error) {
    // api 拦截器已 toast，无需额外处理
  }
}

async function importPgn() {
  try {
    await api.importPgn({
      pgn: pgnInput.value,
      category: form.category,
      practice_side: form.practice_side,
    });
    router.push("/library");
  } catch (error) {
    // api 拦截器已 toast，无需额外处理
  }
}

async function save() {
  if (!(form.name || "").trim()) {
    window.alert("请填写棋谱名称");
    return;
  }
  const payload = { ...form, moves: moves.value, initial_fen: initialFen.value };
  try {
    if (gameId.value) await api.updateGame(gameId.value, payload);
    else await api.createGame(payload);
    router.push("/library");
  } catch (error) {
    // api 拦截器已 toast，无需额外处理
  }
}

onMounted(async () => {
  if (!gameId.value) return;
  try {
    const game = await api.getGame(gameId.value);
    form.name = game.name || "";
    form.category = game.category || "";
    form.red_player = game.red_player || "";
    form.black_player = game.black_player || "";
    form.event = game.event || "";
    form.result = game.result || "";
    form.practice_side = game.practice_side || "both";
    moves.value = game.moves || [];
    initialFen.value = game.initial_fen || INITIAL_FEN;
    selected.value = null;
    rebuildBoard();
  } catch (error) {
    // api 拦截器已 toast，无需额外处理
  }
});
</script>

<style scoped>
.editor {
  display: flex;
  gap: 24px;
  align-items: flex-start;
}

.board-area {
  flex: 1 1 520px;
  max-width: 560px;
}

.board-tools {
  display: flex;
  gap: 12px;
  margin: 12px 0;
}

.moves {
  max-height: 220px;
  overflow-y: auto;
  background: #fff;
  border: 1px solid #e3d6c2;
  border-radius: 6px;
  padding: 8px;
  margin: 0;
  list-style: none;
  padding-left: 0;
}

.form-area {
  flex: 1 1 320px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.form-area label {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.form-area input,
.form-area select,
.form-area textarea {
  padding: 8px 10px;
  border: 1px solid #cbb89a;
  border-radius: 6px;
  font: inherit;
}

.form-area fieldset {
  display: flex;
  flex-direction: column;
  gap: 8px;
  border: 1px solid #e3d6c2;
  border-radius: 6px;
  padding: 10px;
}

.form-area button {
  align-self: flex-start;
  padding: 8px 16px;
  border: none;
  border-radius: 6px;
  background: #7a3b2e;
  color: #fff;
  cursor: pointer;
}

.form-area .save {
  align-self: stretch;
  background: #b32020;
}
</style>
