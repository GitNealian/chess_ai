# 人机对战与局面编辑设计

日期：2026-09-22

## 目标

在既有「人人对弈」页（`/play`）上新增两项能力：

1. **人机对战**：用户可指定引擎执红或执黑，并选择三档难度；引擎计算后直接走棋，用户与引擎轮流走子。
2. **局面编辑（摆子）**：用户可手动将任意棋子摆到棋盘上，摆出的局面必须符合摆子规则；摆好后选择行棋方，以该局面为初始局面开始对弈。

两者复用现有对弈页的分析 / 意图面板与走子校验链路；走子与摆子合法性全部由后端规则引擎判定，前端不重写规则。

## 现状

- `frontend/src/views/PlayView.vue`：人人对弈页，持有 `createPlaySession`（`frontend/src/stores/play.js`），走子经 `POST /api/engine/validate-move` 校验，走子后串行触发 `intentStream` → `analyzeStream`。
- `frontend/src/components/ChessBoard.vue`：坐标固定、支持 `selected` / `arrows` / `flipped`，点击发 `cell-click`。
- `frontend/src/utils/chess.js`：仅 FEN 解析与着法应用，无规则实现。
- `backend/routes/engine.py`：`/analyze`（流式）、`/intent`（流式）、`/validate-move`（无状态走子校验）；`_ANALYZE_LOCK` 串行化引擎重任务。
- `backend/engine/analysis.py`：`analyze(fen, start_depth, max_depth, time_limit_ms, ...)` 逐层迭代加深，`AnalysisResult.pv` 为主变（`PV_LIMIT=2`）。
- `backend/chess_engine/board.py`：完整走子规则（`is_legal` / `in_check` / `kings_facing` / `legal_moves`）；`fen.py` 只校验 FEN 格式，不校验摆子合法性。
- 现有设计约定：规则判定在后端（见 `docs/plans/2026-09-21-play-mode-design.md`「不在前端重写规则」）。

## 方案选择

**方案 A（采纳）：对弈页内扩展 + 两个新后端接口**

- 人机走子新增独立的一次性接口 `POST /api/engine/best-move`，与展示用的 `/analyze`、`/intent` 解耦，可独立测试，避免「用分析流当走子决策」的时序耦合。
- 摆子合法性新增 `POST /api/engine/validate-position`，规则实现在 `chess_engine`，前端只负责交互。
- 两项能力都挂在 `PlayView`，通过模式状态与编辑状态切换，不新增页面。

**方案 B（未采纳）：复用 `/analyze` 流式接口取 `pv[0]` 作为引擎着法**

- 优点：零后端改动。
- 缺点：需等待整条分析流；与面板分析共用同一条流、时序互相干扰；「决策」与「展示」职责混杂。

**方案 C（未采纳）：独立人机页 / 独立编辑页**

- 优点：页面职责单一。
- 缺点：与用户「在人人对战界面添加」的诉求不符，且重复大量对弈 UI。

## 后端接口设计

### 1. `POST /api/engine/best-move`（引擎走子）

加在 engine 蓝本。请求体：

```json
{
  "initial_fen": "可选，缺省初始局面",
  "moves": [{ "x1": 1, "y1": 2, "x2": 4, "y2": 2 }],
  "level": "easy | normal | hard"
}
```

- 局面定位复用 `_resolve_fen`（`fen`，或 `initial_fen + moves`），非法返回 400 `{error, detail}`。
- `level` 非法 / 缺省按 `normal` 处理。
- 持 `_ANALYZE_LOCK` 执行一次 `engine.analyze`，搜索到结束（非流式），取最后一层结果的 `pv[0]`。
- 难度映射（`analyze` 从 `ROOT_START_DEPTH=4` 起有产出，故 `start_depth=4`）：

| level | max_depth | time_limit_ms | 预期耗时 |
|-------|-----------|---------------|----------|
| easy | 5 | 300 | ~0.5s |
| normal | 7 | 1000 | ~1.5s |
| hard | 11 | 2500 | ~3s |

- 成功响应（200）：

```json
{
  "legal": true,
  "move": { "x1": 0, "y1": 3, "x2": 0, "y2": 4, "iccs": "a3a4", "chinese": "兵三进一" },
  "fen": "走后局面 FEN",
  "side_to_move": "red | black",
  "check": false,
  "game_over": null
}
```

  - `chinese` 以走子前局面为上下文经 `move_to_chinese` 生成，失败回退 ICCS；
  - `check`：走子后对方是否被将军；
  - `game_over`：走子后对方无合法着法时 `{ "winner", "reason": "checkmate" | "stalemate" }`，否则 `null`（复用 `/validate-move` 语义）。
- 局面本身已无合法着法（摆子可能摆出困毙等终局）：返回 200 `{ "legal": false, "reason": "当前局面无合法着法" }`，不触发前端全局 toast。
- 搜索无产出（异常兜底）：返回 200 `{ "legal": false, "reason": "引擎未给出着法" }`。
- 不判定长将、重复局面和棋（与既有约定一致）。

### 2. `POST /api/engine/validate-position`（摆子规则校验）

请求体：

```json
{
  "pieces": [{ "x": 4, "y": 0, "side": "red", "kind": "K" }],
  "side_to_move": "red | black"
}
```

- `pieces` 中 `side ∈ {red, black}`、`kind ∈ {K,A,B,N,R,C,P}`；`x ∈ 0..8`、`y ∈ 0..9`；同一坐标不得重复，`pieces` 数量上限 32。
- 空棋盘（`pieces: []`）视为合法输入但校验不通过（缺帅将），返回 `errors`。
- 响应（200）：

```json
{ "valid": true, "fen": "生成的 FEN" }
```

或

```json
{ "valid": false, "errors": ["红方必须有且仅有一个帅", "红相不能在黑方半场"] }
```

- 参数结构错误（`pieces` 非数组、坐标/枚举非法、`side_to_move` 非法、坐标重复、数量超限）返回 400 `{error, detail}`。
- 通过基础规则后追加一次「行棋方是否有合法着法」判定：无着法（困毙）返回 `{ "valid": false, "errors": ["行棋方无合法着法"] }`，避免应用后进入无法继续也无法结算的死局。

### 3. 摆子规则（`chess_engine/rules.py` 新增）

新增函数 `validate_setup(board) -> list[str]`，返回错误文案列表（空列表表示合法）。规则：

1. 帅 / 将各恰好一个；
2. 各兵种数量不超初始配置：仕/士 ≤2、相/象 ≤2、马 ≤2、车 ≤2、炮 ≤2、兵/卒 ≤5；
3. 帅 / 将、仕 / 士必须在九宫内（红 `x∈3..5, y∈0..2`；黑 `x∈3..5, y∈7..9`）；
4. 相 / 象必须落在己方象位（红 / 黑各 7 个田字点）；
5. 兵 / 卒：红兵 `y≥3`、黑卒 `y≤6`；未过河时（红 `y∈{3,4}`、黑 `y∈{5,6}`）必须落在初始偶数列上；
6. 不得照面（`board.kings_facing()`）；
7. 任何一方不得处于被将军状态（`board.in_check(red)` 与 `board.in_check(black)` 均为 `false`；照面已被 `in_check` 覆盖，但单独给出更明确的文案）。

规则函数只做局面校验，不修改 `Board`；`validate-position` 视图负责把 `pieces` 构造成 `Board`（`Board.empty()` + `set_piece` + 设 `side_to_move`）并调用它。

## 前端设计

### 1. `PlayView` 状态扩展

新增状态：

- `mode`：`"human" | "ai"`（默认 `human`）。
- `engineSide`：`"red" | "black" | null`。
- `level`：`"easy" | "normal" | "hard"`（默认 `normal`）。
- `engineThinking`：引擎思考中标志（锁棋盘 + 文案）。
- `editing`：编辑模式标志。
- `editPieces`：编辑中的棋子数组。
- `palette`：当前选中的待落子棋子 `{ side, kind } | null`。
- `editError`：摆子校验错误列表。

### 2. 人机对战交互

- 控件区新增：难度下拉 + 「引擎执红」「引擎执黑」按钮。
- 点击入口按钮：
  - 若当前有对局（`moves.length > 0`）先确认清空；
  - 置 `mode="ai"`、`engineSide`、`flipped = engineSide === "red"`（引擎执红时黑方在下），重置对局为初始局面；
  - 若引擎执红（红先）→ 立即触发引擎走子。
- 用户走子成功后，若 `mode === "ai"` 且 `sideToMove === engineSide` 且未终局 → 触发引擎走子。
- 引擎走子流程：
  1. `engineThinking = true`，停止当前分析 / 意图流；
  2. 调 `bestMove({ initial_fen, moves, level })`；
  3. `legal: true` → `session.applyEngineMove(move)` 应用着法（后端已给出 `chinese` / `check` / `game_over`，不重复调 `/validate-move`）；
  4. `legal: false` → 内联提示 `reason`；
  5. 结束后 `engineThinking = false`，再触发 `intent + analyze`（引擎走子优先，避免与 `/analyze` 争 `_ANALYZE_LOCK`）。
- 引擎思考期间：棋盘点击忽略（`engineThinking` 时 `onCellClick` 直接返回），控件禁用，显示「引擎思考中…」。
- 保留分析 / 意图面板，行为与人人对弈一致；仅调整触发顺序（先走子、后分析）。
- 引擎回合（`mode="ai"` 且 `sideToMove === engineSide`）时棋盘点击忽略，玩家不能替引擎走子。
- AI 模式悔棋：连续撤销直到轮到玩家（通常连带撤销引擎刚走的一步），不自动触发引擎补走，避免「越悔越走」；引擎执红时至少保留引擎首着（即只剩引擎首着时悔棋禁用），避免撤到空局面后轮到引擎无法继续。
- 引擎走子失败（网络 / 引擎异常）后停在引擎回合，玩家点击棋盘即重试引擎走子。

### 3. 编辑摆子交互

- 控件区新增「编辑局面」按钮：任何时刻可点；若已有对局历史先确认「将清空当前对局」。
- 进入编辑模式：
  - 停止分析 / 意图，退出人机模式（`mode="human"`、`engineSide=null`、`engineThinking=false`）；
  - `editPieces` 以当前局面棋子初始化（保留现场），`palette=null`，`editError=[]`；
  - 棋盘渲染 `editPieces`，隐藏箭头与选中态。
- 新增组件 `frontend/src/components/PiecePalette.vue`：
  - props：`selected`（当前选中棋子）；
  - emits：`select`（选中某兵种）、`clear`、`initial`；
  - 内容：红方 7 种 + 黑方 7 种棋子按钮（用 `LABELS` 文案）、「清空棋盘」「标准开局」。
- 编辑模式下的棋盘点击（复用 `cell-click`，由 `PlayView` 分派）：
  - 已选 `palette`：落子（覆盖该格原有棋子）；再次点击已放置的同类棋子 → 移除该格棋子（便于修正）。
  - 未选 `palette`：点击已有棋子 → 选中该棋子进入「移动」态（便于挪动），或直接移除？——采用**选中该格棋子后再点空格为移动、点自身为移除**，与棋子面板选中语义统一。
  - 简化交互（最终实现口径）：点击已有棋子将其移除；有 `palette` 时点击空格落子。挪动通过「移除 + 重新落子」完成。
- 「应用局面」按钮 → 调 `validatePosition({ pieces: editPieces, side_to_move })`：
  - 行棋方由编辑模式内的下拉选择（红先 / 黑先）；
  - `valid: true` → 退出编辑模式，`session.reset({ initial_fen: fen })`（`play.js` 的 `reset` 已按 FEN 第二段确定先行方），随后触发 `intent + analyze`（进入编辑时已退出人机模式，应用后为同屏人人对弈，用户可再点人机入口）；
  - `valid: false` → `editError = errors`，停留在编辑模式。
- 「取消编辑」按钮：放弃改动，恢复进入编辑前的局面（含 `mode` / `engineSide`）；编辑会话用递增 token 标记，取消 / 重新进入编辑后，旧 `validate-position` 迟到响应一律丢弃，避免覆盖新编辑。

### 4. `play.js` 新增方法

- `applyEngineMove(move)`：直接把引擎返回的着法（含 `chinese` / `check` / `game_over`）追加到 `state.moves` 并 `rebuild()`，跳过后端走子校验（着法由后端 `best-move` 保证合法）。
- 复用 `reset({ initial_fen })` 支持摆子后开局（`firstSide` 已按 FEN 解析）。
- `play.js` 的 `reset` 递增 generation，`submit` 响应比对 generation：走子提交进行中若重置对局（如开始人机 / 进入编辑），旧响应不写入新对局。

### 5. `api/index.js` 新增

- `bestMove(payload)`：`POST /engine/best-move`。
- `validatePosition(payload)`：`POST /engine/validate-position`。

## 错误处理

- `best-move` 网络失败 / 400：内联提示（复用 `app-toast` 或页面 `hint`），`engineThinking` 复位，允许用户重试（点棋盘即重试或悔棋）。
- `best-move` 客户端超时（15s，`ECONNABORTED`）：不弹全局 toast，页面提示「引擎思考超时，请重试」。
- `best-move` 返回 `legal: false`：内联提示 `reason`，不改变局面。
- `validate-position` 返回 `valid: false`：编辑模式内联列出 `errors`。
- 摆子参数 400：内联提示 `detail`。
- 引擎思考中用户点击棋盘：忽略，不改变局面。

## 测试

- 后端：
  - `tests/test_position_rules.py`：帅将数量、九宫、过河、兵卒位置、数量上限、照面、被将军各分支；
  - `tests/test_engine_validate_position_api.py`：合法 / 非法 / 空棋盘 / 参数错误；
  - `tests/test_engine_best_move_api.py`：初始局面红先返回合法着法且 `fen` 推进；`level` 缺省与非法回退 `normal`；引擎执黑（`side_to_move=b`）返回黑方着法；无合法着法局面 `legal:false`；参数错误 400。
- 前端：
  - `stores/__tests__/play.test.js`：`applyEngineMove` 追加着法并重建、终局快照；
  - `components/__tests__/PiecePalette.test.js`：选中 / 清空 / 标准开局事件；
  - `views/__tests__/PlayView.test.js`：引擎执红立即走子、用户走子后引擎自动应着、思考中锁棋盘、难度参数传递、进入编辑确认清空、落子 / 移除、应用局面成功重置、校验失败展示错误。
- 运行：后端 `pytest`（backend 目录）、前端 `npm test`（frontend 目录）。

## 不做（YAGNI）

- 难度自定义（时限 / 深度手动输入）；
- 引擎走子过程流式展示（思考进度 / 候选着法）；
- 编辑局面的保存 / 分享 / 导出 FEN；
- 摆子时对「行棋方是否已被将军」之外的残局题特殊规则（如长将、重复局面）；
- 联网对战。
