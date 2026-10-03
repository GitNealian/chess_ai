# 棋谱变着树浏览 实现计划

日期：2026-09-30
设计文档：`2026-09-30-variation-tree-design.md`

## 1. 改动清单

### 后端

| 文件 | 改动 |
|---|---|
| `backend/models.py` | 新增 `GameStep` 模型（`game_steps` 表） |
| `backend/app.py` | `_ensure_schema` 补建 `game_steps` 索引（新库由 `db.create_all()` 建表） |
| `backend/chess_engine/variation.py`（新增） | 局面 key、`build_steps`、`rebuild_for_game`、`children` 纯逻辑 |
| `backend/routes/games.py` | 新增 `POST /api/games/collections/children`；在 create / update / import / delete 后同步索引 |
| `backend/scripts/rebuild_game_steps.py`（新增） | 全量重建索引 |
| `backend/tests/test_variation_api.py`（新增） | 接口与判定规则测试 |

### 前端

| 文件 | 改动 |
|---|---|
| `frontend/src/utils/chess.js` | 新增 `piecesToFen(pieces, sideToMove)`（当前仅有 `fenToPieces`/`applyMove`） |
| `frontend/src/api/index.js` | 新增 `variationChildren(data)` |
| `frontend/src/mobile/components/MobileVariationPicker.vue`（新增） | 变着选择弹层 |
| `frontend/src/mobile/views/MobileHomeView.vue` | 路径栈、children 查询与缓存、变着入口与选择 |
| `frontend/src/mobile/components/__tests__/MobileVariationPicker.test.js`（新增） | 组件测试 |
| `frontend/src/mobile/views/__tests__/MobileHomeView.test.js` | 增补路径/变着用例 |

## 2. 后端实现

### 2.1 数据表 `game_steps`

```python
class GameStep(db.Model):
    __tablename__ = "game_steps"

    id = db.Column(db.Integer, primary_key=True)
    collection = db.Column(db.String(100), nullable=False)
    game_id = db.Column(db.Integer, db.ForeignKey("games.id", ondelete="CASCADE"), nullable=False)
    ply = db.Column(db.Integer, nullable=False)          # 走该步之前
    fen_key = db.Column(db.String(150), nullable=False)
    move = db.Column(db.String(20), default="")          # x1,y1,x2,y2
    next_fen = db.Column(db.String(150), nullable=False)

    __table_args__ = (
        db.Index("ix_game_steps_collection_fen", "collection", "fen_key"),
        db.Index("ix_game_steps_collection_next", "collection", "next_fen"),
        db.Index("ix_game_steps_game", "game_id"),
    )
```

`app.py::_ensure_schema` 追加 `CREATE INDEX IF NOT EXISTS ...`（旧库安全；新库已由 `create_all` 建）。

### 2.2 `chess_engine/variation.py`

```python
COLLECTION_PREFIX = "古谱 · "

def fen_key(fen: str) -> str:
    parts = fen.split()
    return f"{parts[0]} {parts[1]}"

def collection_of(category: str) -> str | None:
    if category and category.startswith(COLLECTION_PREFIX):
        return category[len(COLLECTION_PREFIX):]
    return None

def build_steps(game) -> list[dict]:
    board = Board(); board.load_fen(game.initial_fen)
    rows = []
    for ply, raw in enumerate(game.moves):
        from_key = fen_key(board.to_fen())
        move = Move.from_dict(raw)
        board.apply_move(move)
        rows.append({
            "ply": ply, "fen_key": from_key,
            "move": f"{move.x1},{move.y1},{move.x2},{move.y2}",
            "next_fen": fen_key(board.to_fen()),
        })
    return rows

def rebuild_for_game(session, GameStep, game) -> None:
    session.query(GameStep).filter_by(game_id=game.id).delete()
    collection = collection_of(game.category)
    if collection is None:
        return
    for row in build_steps(game):
        session.add(GameStep(game_id=game.id, collection=collection, **row))
```

`children(collection, fen, threshold=4, session=..., Game=..., GameStep=...)` 逻辑：

1. `key = fen_key(fen)`。
2. `rows = GameStep.query.filter_by(collection=collection, fen_key=key).all()`；按 `move` 文本分组得 `branches`，每组拆分回坐标并生成中文（`notation` 的中文记谱生成，缺失回退坐标文本），`to_fen` 应一致；组内收集 `games`，若 `ply + 1 == len(game.moves)` 归入 `end_games`。
3. 经过该节点的各谱步数：`plies_by_game[game_id] = min(ply)`（一谱多次经过取最小）。
4. **根谱检查**：查询本集内 `initial_fen` 的 key 等于 `key` 的谱（`Game.initial_fen.like(f"{key}%")` 粗筛后精确 `fen_key(...) == key` 校验），这些谱以 `ply = 0` 经过 → 加入 `plies_by_game` 取 0。
5. `branchable = len(distinct move) >= 2 and all(p > threshold for p in plies_by_game.values()) and bool(plies_by_game)`。
6. 返回 `{fen, branchable, plies: {min, max}, branches}`。

注意：`plies_by_game` 为空说明该局面不属于该集任何谱 → `branches` 空、`branchable=false`。

### 2.3 路由 `routes/games.py`

```python
@games_bp.post("/collections/children")
def collection_children():
    data = request.get_json(silent=True) or {}
    collection = data.get("collection")
    fen = data.get("fen")
    if not isinstance(collection, str) or not collection:
        return _error("collection 不能为空")
    if not isinstance(fen, str) or not fen:
        return _error("fen 不能为空")
    board = Board()
    try:
        board.load_fen(fen)
    except ValueError as exc:
        return _error("fen 无效", detail=str(exc))
    return jsonify(variation.children(collection, board.to_fen()))
```

同步索引。注意顺序：

- `create` / `import`：先 commit 得到 `game.id`，再 `rebuild_for_game`，再 commit。
- `update`：若 `"moves" in data or "initial_fen" in data or "category" in data`，`rebuild_for_game` 后 commit。
- `delete`：先 `GameStep.query.filter_by(game_id=game_id).delete()`，再删 `Game`。

### 2.4 `scripts/rebuild_game_steps.py`

清空 `game_steps` 后遍历全部 `Game`（仅 `category` 为 `古谱 · ` 前缀者）重建。复用 `variation.rebuild_for_game`。

## 3. 前端实现

### 3.1 `utils/chess.js::piecesToFen`

当前文件仅有 `fenToPieces`/`applyMove`，需新增：按 `y=9..0` 行、`x=0..8` 拼接棋子字母（红大写、黑小写）、空位累计数字，末尾 ` w|b - - 0 1`，与后端 `fen.py` 对齐；行棋方由当前步数奇偶推导。

### 3.2 `api/index.js`

```js
variationChildren: (data) => http.post("/games/collections/children", data).then((r) => r.data),
```

### 3.3 `MobileVariationPicker.vue`

- props：`branches`、`plies`。
- 列表项：`branch.move.chinese`（缺失回退坐标）、`branch.games` 谱名、「末步」标记。
- emit：`select(branch)`、`cancel`。
- 样式复用 `MobileGamePicker` 的 `.picker-mask` / `.picker-card` / `.picker-item`。

### 3.4 `MobileHomeView.vue`

- 新增 `branchInfo = ref(null)`、`childrenCache = new Map()`（key 为 `fen`）、`variationOpen = ref(false)`。
- 当前局面 FEN：由 `initialFen` + `moves.slice(0, ply)` 重放得到（用 `applyMove` + `piecesToFen`），或维护 `currentFen` computed。
- `watch(() => [ply, currentGame, initialFen], queryChildren)`：取当前 `fen`，命中缓存直接用，否则 `api.variationChildren({collection, fen})`。`collection` 由 `currentGame.category` 去掉 `"古谱 · "` 前缀得到；不是棋谱集则不查询。
- `branchable && branches.length > 1` 时，`BoardControls` 显示「变着 {{ branches.length }}」按钮（需给 `BoardControls` 加一个可选 prop/slot）。
- 选择分支：
  ```js
  function onSelectVariation(branch) {
    moves.value = moves.value.slice(0, ply.value);
    moves.value.push({ ...branch.move, check: false, gameOver: null });
    ply.value += 1;
    variationOpen.value = false;
    // 若新节点唯一出边，可继续自动前进（可选）
  }
  ```
- `currentGame` 切换：选择分支后，若 `branch.games.length`，可将 `currentGame` 更新为该分支代表谱（如 `end_games[0]` 或后续最长者），保证背谱入口可用。
- 路径条（可选）：在棋盘上方渲染 `moves.slice(0, ply)` 的中文/坐标，点击回退。

### 3.5 导航与背谱

- `navSource` 仍用于「上一盘/下一盘」；树浏览不改变该逻辑。
- 背谱入口继续以 `currentGame` 为准；树浏览中 `currentGame` 取初始进入谱或所选分支代表谱。

## 4. 测试

### 4.1 后端 `tests/test_variation_api.py`

用合法着法构造（坐标序列可用 `parse` 或直接手写）。核心用例：

1. **分叉在第 5 着之后**：A、B 同 `category="古谱 · 测试集"`，前 5 着相同、第 6 着不同。查询分叉前局面 → `branchable=true`，`branches` 长度 2。
2. **分叉在第 4 着内**：共享 3 着即分叉 → `branchable=false`。
3. **严格大于 4**：恰好共享 4 着（`ply=4` 的分叉点）→ `branchable=false`；共享 5 着（`ply=5`）→ `true`。
4. **转置合并**：A、B 以不同着法顺序到达同一局面 → 该局面 `branches` 合并，来源谱含两者。
5. **跨集隔离**：不同 `category` 的同着法谱不计入 `branches`。
6. **单谱 / 非棋谱集**：仅一盘或 `category="中炮"` → `branchable=false`。
7. **索引同步**：更新棋谱 moves 后，旧分支消失、新分支出现；删除棋谱后其来源不再出现。

### 4.2 前端

- `MobileVariationPicker.test.js`：渲染分支、点击 emit、末步标记。
- `MobileHomeView.test.js` 增补：mock `api.variationChildren`，验证到达分叉点显示入口、选择后路径与 ply 正确、缓存命中不再请求。

## 5. 验收标准

1. `cd backend && .venv/bin/python -m pytest` 全绿（含新增用例）。
2. `cd frontend && npx vitest run` 全绿。
3. `cd frontend && npm run build` 成功，`dist/` 更新（AGENTS 要求）。
4. 手工验收：导入同一 `古谱 · X` 集的两盘棋，前 5 着相同、第 6 着不同；浏览到第 5 着后出现「变着」入口，选择后进入另一分支，棋盘与路径正确。

## 6. 风险与注意

- **前端 `piecesToFen` 需与后端 `fen.py` 严格对齐**（大小写、空位计数、行棋方），否则 `fen_key` 对不上；建议用后端返回的 `to_fen` 或加单测对拍。
- **索引同步遗漏**：`update`/`delete` 是易漏点，测试用例 7 覆盖。
- **阈值 4 误连**：见设计文档 §6；如需调整，改 `children(threshold=...)` 默认值或加集级配置。
- **步的分组键**：`Move` 仅有坐标，`game_steps.move` 存 `x1,y1,x2,y2` 文本，`branches` 去重即按此键；中文着法由后端 `notation` 生成。
- 大集可后续加全量 `tree` 接口与缓存，v1 用 `children` 懒加载。

## 7. 实现记录（2026-09-30）

- 纯逻辑（`fen_key` / `collection_of` / `build_steps` / `move_key`）放在 `chess_engine/variation.py`，保持无 Flask/SQLAlchemy 依赖；`children` 查询与索引维护放在 `backend/routes/games.py`（依赖 ORM）。
- `game_steps.move` 存 `x1,y1,x2,y2` 文本（`Move` 无 ICCS）；`children` 返回的 move 含中文（`notation.move_to_chinese`，异常回退空串）。
- 启动回填：`app.py` 非 TESTING 时后台线程调用 `_backfill_variation_index`，仅当 `game_steps` 为空且存在古谱时执行；另有 `scripts/rebuild_game_steps.py` 手动全量重建。
- 前端：`MobileVariationPicker.vue` 承接变着选择；`MobileHomeView.vue` 按 `currentFen` 查询并缓存 children，选分支时用来源谱重建后续路径（`locatePly`），从而可继续浏览；`BoardControls` 新增 `show-variation`/`variation-count` 按钮。
- 真实库（152279 盘）实测：古谱 11084 盘 → `game_steps` 242393 行，重建 14s；示例「象棋路边摊」已识别出分叉节点（2 条分支）。
- 验证：后端 570 passed / 2 skipped；前端 214 passed；`npm run build` 成功。
