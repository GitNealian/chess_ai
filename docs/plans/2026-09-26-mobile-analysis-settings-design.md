# 移动端设置：评分与意图识别（设计）

日期：2026-09-26

## 目标

移动端 `/m` 首页「设置」弹窗新增两个开关：**开启评分**、**开启意图识别**。开启后，首页棋盘下方依次展示评分条与对手意图推演面板。开关默认关闭，并持久化到 `localStorage`。

## 现状

- 桌面端 `PlayView.vue` 已实现评分（`analyzeStream`）与意图推演（`intentStream`），展示评分条与 `IntentPanel`。
- 移动端 `MobileHomeView.vue` 目前只有棋盘、控制栏、编辑与「打开」弹窗；设置弹窗仅一个「关闭」按钮，且无持久化。
- 移动端编辑弹窗 `MobileBoardEditor.vue` 已调用 `api.validatePosition`（含行棋方 `red/black`），接口返回 `fen`，但 `apply` 只把棋子数组传出。

## 设计

### 1. 设置存储 `src/mobile/settings.js`（新增）

- `localStorage` key：`chess:mobile-settings`，值为 JSON `{ "score": false, "intent": false }`。
- `loadSettings()`：读取并合并默认值，非法 JSON／字段时回退默认（全 `false`）。
- `saveSettings(settings)`：写入 `{score, intent}` 布尔值，异常静默。
- 纯工具模块，便于单测。

### 2. 设置弹窗（`MobileHomeView.vue`）

- 在 `settings-card` 内新增两个原生 checkbox：`开启评分`、`开启意图识别`，`data-test` 分别为 `setting-score`、`setting-intent`。
- 变更即调用 `saveSettings`；弹窗打开时以 `loadSettings()` 初始化（页面加载时即初始化 `settings`）。
- 保留「关闭」。

### 3. `MobileAnalysis.vue`（新增组件）

- props：`initialFen`、`moves`（已按当前 `ply` 切片）、`score`、`intent`（均为布尔开关）。
- 内部沿用桌面端 token + `AbortController` 机制：
  - `intent` 开启：先 `intentStream`，完成后（含失败）再 `analyzeStream`。
  - 仅 `score` 开启：直接 `analyzeStream`。
  - 两者都关或 `initialFen` 为空：不请求、不渲染。
- 请求 payload：`{ initial_fen, moves: moves.map(({x1,y1,x2,y2})) }`。
- 展示：评分条（文本 + 进度条，样式对齐 `PlayView`，`data-test="mobile-score"`）+ 复用 `IntentPanel`（`intent.status !== 'idle'` 时）。
- `watch` 监听 `initialFen / score / intent / moves`，翻步、切谱、编辑后自动重算并 abort 旧请求；卸载时 abort。

### 4. `MobileHomeView` 集成

- `settings = reactive(loadSettings())`；新增 `initialFen` 状态，初值 `INITIAL_FEN`，打开棋谱时取 `game.initial_fen || INITIAL_FEN`。
- 在 `BoardControls` 下方插入 `<MobileAnalysis :initial-fen="initialFen" :moves="moves.slice(0, ply)" :score="settings.score" :intent="settings.intent" />`。
- `onOpenGame` 同步更新 `initialFen`。

### 5. 编辑局面

- `MobileBoardEditor.vue`：校验通过后 `emit("apply", pieces, res.fen)`（第一个参数仍为棋子数组，兼容现有调用与测试）。
- `MobileHomeView.vue`：`onApply(pieces, fen)` → `basePieces = fen ? fenToPieces(fen) : pieces`、`initialFen = fen || INITIAL_FEN`、`moves = []`、`ply = 0`、`currentGame = null`。
- 由此编辑后的自定义局面也具备 `initial_fen`，可正常评分／推演。

## 测试

- `settings.test.js`：默认值、保存／读取往返、非法 JSON 容错。
- `MobileAnalysis.test.js`：mock `analyzeStream/intentStream`，验证仅评分、仅意图、两者组合的调用与渲染，以及都关时不请求。
- `MobileBoardEditor.test.js`：`apply` 第二个参数透传 `fen`。
- `MobileHomeView.test.js`：开关切持久化；开启评分后出现 `mobile-score`。

## 边界

- 评分／意图依赖「`initial_fen` + 着法」，两者由棋谱或编辑校验后的 FEN 提供。
- 请求随翻步／切换棋谱／编辑／卸载自动 abort，失败只就地提示，不影响棋盘。
