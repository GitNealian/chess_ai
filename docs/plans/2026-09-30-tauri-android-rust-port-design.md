# 象棋记谱 Android App 改造方案（Tauri 2 + Rust 引擎）

日期：2026-09-30

## 1. 目标与约束

把现有「象棋记谱 Web」改造为一个**完全离线、可上架应用商店的 Android App**：

- 离线运行：棋谱库 / 背谱 / 复习 / AI 分析 / 人机对战 / 局面扫描，全部在设备本地完成，不依赖任何服务器。
- 可上架：产出标准 Android 工程，可生成 AAB（Google Play）与 APK（国内商店）。
- 复用最大化：现有 Vue 3 移动端 UI（`frontend/src/mobile/`）与桌面端 UI 全部保留，只替换数据/计算后端。
- 引擎用 **Rust 重写**（含规则引擎与 AI 搜索引擎），识别模型沿用现有 ONNX 权重。
- 附带收益：同一套 Tauri 工程天然支持桌面端（Windows/macOS/Linux），未来可一份代码多端发布。

### 现状盘点（改造起点）

| 层 | 现状 | 处置 |
|---|---|---|
| 前端 | Vue 3 + Vite + Pinia，`src/mobile/` 已有完整移动端 UI；通过 `src/api/index.js`（axios + fetch 流）访问 `/api` | **保留组件**，仅重写 `api/index.js` 内部实现 |
| 规则引擎 | 纯 Python `backend/chess_engine/`（board/fen/move/notation/rules/parser） | **移植到 Rust** |
| AI 引擎 | Python + numba/Cython `backend/engine/`（位棋盘 + negaScout/PVS + Lazy SMP + 意图推演） | **移植到 Rust** |
| 识别 | Python + OpenCV + onnxruntime，两个 ONNX 模型（pose 10.7MB / layout 31.1MB） | **Rust + ort + 纯 Rust 图像处理**，模型不变 |
| 数据 | Flask-SQLAlchemy + SQLite（games / game_activity / reviews / review_logs） | **复用 SQLite schema**，Rust 侧 rusqlite 访问 |
| 认证 | 可选单用户密码 + session cookie | 离线 App **移除**（或改本地 PIN，见 §9） |
| 托管 | Flask 托管 `frontend/dist` 静态资源 | 由 Tauri WebView 直接加载 dist |

现状里前端只是 HTTP 客户端，规则/AI/识别全部在后端 Python，因此「离线化」的实质是**把 Python 后端整体重写为 Rust 并内嵌进 App**；前端改动被压到最小（仅 API 适配层）。

## 2. 技术选型

| 组件 | 选型 | 理由 |
|---|---|---|
| 应用框架 | **Tauri 2.x**（2.11+） | 复用 Vue 前端；Android 支持成熟（`tauri android init/build`）；Rust 后端与引擎同语言；一套代码多端 |
| 规则引擎 | **Rust**（移植 `chess_engine/`） | 纯逻辑，移植直接；消除 Python 运行时 |
| AI 引擎 | **Rust**（移植 `engine/`） | 位棋盘/搜索/评估表可直接对应；Rust 无 GC、支持原生线程做 Lazy SMP；性能可接近原 Cython 后端 |
| ONNX 推理 | **`ort` 2.x + `load-dynamic`** | 官方 ONNX Runtime 的 Rust 绑定；`load-dynamic` 运行时 dlopen `libonnxruntime.so`，避免交叉编译链接地狱；支持 Android NNAPI / XNNPACK EP |
| 图像处理 | **纯 Rust**：`image` + `fast_image_resize` + `ndarray` + 自写透视采样 | 不引入 OpenCV C++ 依赖（Android 交叉编译极其麻烦）；识别所需仅解码/缩放/仿射/透视/裁剪/归一化，均可纯 Rust 实现 |
| 数据库 | **`rusqlite`（bundled）** | bundled 特性把 SQLite C 源码随 crate 编译，NDK 可直接交叉编译；schema 与现有库兼容，便于迁移 |
| 流式 IPC | **Tauri `ipc::Channel` + 取消令牌** | 替代原 NDJSON over HTTP；channel 从 Rust 流式推送 `{type,...}`，前端沿用既有解析回调 |
| 并行搜索 | **`std::thread` + `crossbeam`** | Android 可用；线程数取 `available_parallelism` |

不使用 Chaquopy / 内嵌 Python：numba 依赖 LLVM JIT，不支持 Android ARM；Cython 交叉编译到 Android 亦不可控。Rust 重写是离线 + 上架目标下唯一干净的路线。

## 3. 总体架构

```
Android App（Tauri 2）
├─ WebView 前端（Vue 3，现有 src/ 复用）
│    ├─ src/mobile/**            现有移动端 UI（零改动）
│    └─ src/api/index.js         重写：axios/fetch → invoke/Channel（接口签名不变）
│
├─ Rust 后端（src-tauri/）
│    ├─ commands/    Tauri 命令层（对应原 REST 端点）
│    ├─ db/          rusqlite + 仓储（games / review / activity）
│    ├─ chess/       规则引擎（移植 chess_engine/）
│    ├─ engine/      AI 引擎（移植 engine/）+ 意图推演
│    ├─ recognizer/  ort 推理 + 图像前/后处理
│    └─ srs.rs       SM-2 调度（移植 srs.py）
│
├─ 资源：weights/pose.onnx + layout.onnx（打包进 APK）
└─ 数据：app_data_dir/chess.db（SQLite，可导入现有库）
```

数据流（以「扫描局面」为例，对比现状）：

```
现状：拍照 → canvas 压缩 → POST /api/recognize(multipart) → Python 识别 → JSON pieces
改造：拍照 → canvas 压缩 → invoke("recognize", {bytes}) → Rust: 解码→pose→透视→layout → pieces
```

数据流（以「实时分析」为例）：

```
现状：analyzeStream(payload) → fetch NDJSON 流 → onResult/onDone/onError
改造：analyzeStream(payload) → invoke("analyze", { payload, channel }) → Rust 迭代加深 channel.send({type:"result"}) → 前端同回调
```

## 4. 目录结构（新增 `src-tauri/`）

```
chess/
├── frontend/                        # 现有，保留
│   ├── src/api/index.js             # 重写为 Tauri 桥接
│   └── ...
├── src-tauri/                       # 新增
│   ├── Cargo.toml                   # tauri / ort / rusqlite / image / ...
│   ├── tauri.conf.json              # frontendDist=../frontend/dist；Android 配置
│   ├── build.rs
│   ├── assets/weights/              # pose.onnx / layout.onnx（约 42MB，.gitignore）
│   ├── src/
│   │   ├── main.rs                  # 桌面入口
│   │   ├── lib.rs                   # #[cfg_attr(mobile, tauri::mobile_entry_point)]
│   │   ├── commands/
│   │   │   ├── mod.rs
│   │   │   ├── games.rs             # 棋谱 CRUD / 解析 / PGN / 收藏 / 打开
│   │   │   ├── review.rs            # 复习队列 / 提交 / 统计
│   │   │   ├── engine.rs            # validate-move / best-move / validate-position / analyze / intent
│   │   │   └── recognize.rs         # 局面识别
│   │   ├── db/
│   │   │   ├── mod.rs               # 连接初始化 + 建表/迁移
│   │   │   └── repo.rs              # Game/Review/ReviewLog/Activity 仓储
│   │   ├── chess/                   # ← 移植 backend/chess_engine/
│   │   │   ├── board.rs
│   │   │   ├── move.rs
│   │   │   ├── fen.rs
│   │   │   ├── notation.rs
│   │   │   ├── rules.rs
│   │   │   ├── parser.rs
│   │   │   └── mod.rs
│   │   ├── engine/                  # ← 移植 backend/engine/
│   │   │   ├── bitboard.rs
│   │   │   ├── position.rs
│   │   │   ├── movegen.rs
│   │   │   ├── search.rs
│   │   │   ├── evaluate.rs
│   │   │   ├── tables.rs
│   │   │   ├── eval_tables.rs       # 由 backend/engine/eval_tables.py 机械转换
│   │   │   ├── zobrist.rs
│   │   │   ├── intent.rs            # 意图推演（promotion/threat/bait）
│   │   │   ├── analysis.rs          # analyze / best_move / warmup 对外封装
│   │   │   └── mod.rs
│   │   ├── recognizer/
│   │   │   ├── pose.rs              # 角点检测（SimCC 解码）
│   │   │   ├── classifier.rs        # 90×16 argmax
│   │   │   ├── pipeline.rs          # 透视 + 图像原语 + 警告聚合
│   │   │   └── mod.rs
│   │   ├── srs.rs                   # SM-2（移植 srs.py）
│   │   ├── jobs.rs                  # 分析任务注册表 + 取消令牌
│   │   └── error.rs                 # 统一 AppError → 前端 message/detail
│   └── gen/android/                 # tauri android init 生成（gitignore）
└── docs/plans/                      # 本方案
```

## 5. 数据层

### 5.1 复用 schema

直接复用现有四张表，字段与 `backend/models.py` 一一对应，保证现有 `backend/chess.db` 可复制进 App 后直接使用：

- `games`：id, name, category, red_player, black_player, event, result, initial_fen, moves(JSON 文本), practice_side, source, source_hash(unique), created_at, updated_at
- `game_activity`：game_id(PK,FK), last_opened_at, favorited_at
- `reviews`：id, game_id(FK,unique), due_date, interval, ease_factor, repetitions, lapses, last_reviewed_at
- `review_logs`：id, game_id(FK), reviewed_at, correct, mistake_count, duration_ms

### 5.2 访问方式

- `rusqlite` bundled + `parking_lot::Mutex<Connection>` 单连接（单用户离线，无需连接池；分析/识别耗时任务不占锁）。
- 数据库路径：`app.path().app_data_dir()/chess.db`；启动时 `CREATE TABLE IF NOT EXISTS`，与现有 `app.py::_ensure_schema` 对齐。
- 可选「导入旧库」：从文件选择器选 `chess.db` 覆盖。
- `moves` 仍以 JSON 文本存储，序列化/反序列化在仓储层完成（对应 model 的 `moves` property）。

## 6. 规则引擎移植（chess/）

逐文件对应，逻辑等价：

| Python | Rust | 要点 |
|---|---|---|
| `chess_engine/board.py` | `chess/board.rs` | 9×10 棋盘、`is_legal`、`apply_move`、`in_check`、`has_legal_move`、`load_fen`/`to_fen`、`side_to_move` |
| `chess_engine/move.py` | `chess/move.rs` | `Move{x1,y1,x2,y2}` + `from_dict` |
| `chess_engine/fen.py` | `chess/fen.rs` | 中国象棋 FEN 解析/生成 |
| `chess_engine/notation.rs` | `chess/notation.rs` | 中文记谱生成 `move_to_chinese` 与解析 |
| `chess_engine/parser.rs` | `chess/parser.rs` | 中文 / ICCS / PGN 解析（含 `[Event]` 等头部） |
| `chess_engine/rules.rs` | `chess/rules.rs` | 摆子合法性 `validate_setup` |

**正确性保障**：以现有 pytest 用例为 golden，为 Rust 版建立对拍测试。做法——编写一次性脚本，用 Python 版对一批局面/着法导出（`is_legal`、`to_fen`、`move_to_chinese`、`parse` 结果）为 JSON fixtures，Rust 测试逐一比对。见 §12。

## 7. AI 引擎移植（engine/）

### 7.1 模块对应

| Python | Rust | 说明 |
|---|---|---|
| `bitboard.py` | `bitboard.rs` | 90 位打包两个 u64，位运算原语 |
| `position.rs` | `position.rs` | make/unmake 增量维护、Zobrist 更新 |
| `movegen.rs` | `movegen.rs` | 着法生成、将军/合法性 |
| `search.rs` | `search.rs` | 置换表、杀手/历史启发、静态搜索、negaScout/PVS、迭代加深 |
| `evaluate.rs` | `evaluate.rs` | 中局/残局评估 |
| `eval_tables.py` | `eval_tables.rs` | **由脚本机械转换**（数据表，非算法），生成 `const` 数组 |
| `tables.rs` / `zobrist.rs` | 同名 | 预生成表、固定种子 Zobrist |
| `analysis.py` | `analysis.rs` | 对外 `analyze`（迭代加深，逐层产出）、`best_move`、`warmup` |
| （新增） | `intent.rs` | 意图推演，移植前端依赖的 rank/threat/bait 事件序列 |

### 7.2 并行（Lazy SMP）

- 用 `std::thread` + `Arc<SharedTable>`（置换表）复刻 numba 版 Lazy SMP：主线程产出结果，辅助线程共享 TT 互补搜索。
- 线程数默认 `min(max(1, available_parallelism()-1), 8)`，可由请求 `threads`（1..16）覆盖，语义与现状一致。
- 保留「并行模式下 nodes 只统计主线程、分数/PV 可能微变」的现状行为说明。
- 冷启动无需 JIT 预热（Rust 编译型），**消除 numba 首次 20–35s 预热**，启动即用。

### 7.3 行为一致性

- 给定相同评估表、相同搜索参数、`threads=1`，Rust 版与 Python 版应产出相同分/PV；用对拍脚本抽查若干局面。
- 并行档允许非确定性，与现状口径一致。

## 8. 识别模块（recognizer/）

模型与解码逻辑完全沿用，仅替换运行时与图像库：

| 步骤 | 现状 | Rust 实现 |
|---|---|---|
| 图片解码 | cv2 | `image` crate（JPEG/PNG/WebP） |
| 缩放/仿射/center-crop | cv2.resize/warpAffine | `fast_image_resize` + 自写双线性采样 |
| 透视校正 | cv2.warpPerspective | 自写 3×3 单应矩阵 + 双线性采样 |
| 前处理归一化 | numpy（ImageNet mean/std） | `ndarray` |
| 推理 | onnxruntime(Python) | `ort` 2.x + `load-dynamic` |
| SimCC 解码 / argmax | numpy | 纯 Rust |

### 8.1 ONNX Runtime 在 Android 的接入

- `ort` 启用 `load-dynamic`，不静态链接；在启动时用 `ort::init_from(path)` 指定 `libonnxruntime.so`。
- 将 ONNX Runtime 官方 Android 预编译库按 ABI 放入 `src-tauri/gen/android/app/src/main/jniLibs/<abi>/libonnxruntime.so`（`arm64-v8a` / `armeabi-v7a` / `x86_64`，模拟器需要 x86_64）。不启用 ORT 自带的下载策略（Android 不支持）。
- 可选启用 `xnnpack` / `nnapi` EP 提升速度；首版可用 CPU EP 保证兼容，再做加速。
- ProGuard/R8：Android 工程保留规则避免裁剪（若用 AAR 方式需 `-keep class ai.onnxruntime.**`；本项目走 jniLibs 方式则主要关注 .so 不被剥离）。

### 8.2 模型打包

- `pose.onnx`（10.7MB）+ `layout.onnx`（31.1MB）放 `src-tauri/assets/weights/`，通过 `tauri.conf.json` 的 `bundle.resources` 纳入 App 资源，运行时用 `app.path().resolve("weights/pose.onnx", BaseDirectory::Resource)` 读取。
- 推理会话懒加载单例（double-checked locking + `Mutex`），与现状 `recognizer/__init__.py` 一致；首次识别时加载。
- 权衡：内嵌使 APK 增大 ~42MB；若在意体积，可改为首启从网络下载（与「完全离线」目标冲突），故 v1 选择内嵌。

## 9. 前端适配（改动最小化原则）

**核心策略：保持 `frontend/src/api/index.js` 对外接口签名与返回结构完全不变**，仅替换内部实现。这样 `src/mobile/**` 与桌面 `src/views/**`、stores、组件**零改动**。

### 9.1 普通请求：axios → invoke

```js
// 现状
listGames: (params) => http.get("/games", { params }).then(r => r.data)
// 改造
listGames: (params) => invoke("list_games", { params })
```

错误处理：现有 interceptor 负责 toast 与 401 跳转；改造后在命令封装层统一 catch，抛出的错误映射为 `{ error, detail }`，继续派发 `app-toast` 事件（去掉 401/unauthorized 分支，改为本地 PIN 场景）。

### 9.2 流式分析：fetch NDJSON → Tauri Channel

`analyzeStream` / `intentStream` 的**回调签名保持不变**，内部改用 Channel：

```js
import { Channel, invoke } from "@tauri-apps/api/core";

export async function analyzeStream(payload, { channel, onResult, onDone, onError } = {}) {
  const ch = new Channel();
  ch.onmessage = (msg) => {
    if (msg.type === "result") onResult?.(msg);
    else if (msg.type === "done") onDone?.(msg);
    else if (msg.type === "error") onError?.(new Error(msg.message || "分析失败"));
    // ping 忽略
  };
  try {
    await invoke("analyze", { payload, channel: ch });
  } catch (err) {
    onError?.(err);
  }
}
```

- Rust 侧 `analyze` 命令接收 `channel: Channel<serde_json::Value>`，在迭代加深各层 `channel.send(json!({"type":"result", ...}))`，结束时 `{"type":"done"}`。JSON 字段与现有 `_pv_payload` / `_done_reason` **完全一致**，前端解析逻辑无需改。
- 意图流同理解析 `rank` / `threat` / `bait` / `done`。
- **取消**：Tauri 命令执行中无法直接 abort。新增 `jobs.rs`：命令首参接收 `job_id`，内部把取消标志登记到全局表；前端取消时调用 `invoke("cancel_job", { jobId })` 置位（对应现有 `stop` 数组语义），生成器在线边界停止并返回 `done`。前端把现有 `AbortController` 换成 `job_id` + `cancel_job`。

### 9.3 识别：multipart → 字节数组

- 现有 `<input type="file" capture>` 在 Android WebView 可正常调起相机/相册，**保留不动**。
- `MobileScanDialog` 里 canvas 压缩后，读取 `File` 为 ArrayBuffer，转 base64（或直接传字节数组）交给命令：

```js
recognize: (bytesBase64) => invoke("recognize", { image: bytesBase64 })
```

- Rust 侧 base64 解码 → 识别 pipeline → 返回 `{ pieces, layout, warnings, stats }`，结构与现有 `/api/recognize` 响应一致。

### 9.4 其他

- 前端不再需要 `baseURL: "/api"`、dev proxy 等；`vite.config.js` 去掉 proxy（若同时保留 Web 版可保留）。
- `LoginView.vue` / `stores/auth.js`：默认跳过登录（v1）。若要隐私，改本地 PIN（见 §10）。

## 10. 认证

- 离线单机无多用户，**v1 移除密码登录**：删除 `routes/auth` 语义、`AUTH_PASSWORD`/session；路由守卫默认放行，`authMe` 命令恒返回已登录。
- 可选增强（后续）：本地 PIN 码（Rust 侧 PBKDF2/Argon2 哈希存于 `app_data_dir`），用于「打开 App 时验证」，与数据加密解耦。

## 11. 命令层接口映射

原 REST 端点 → Tauri 命令（参数/返回结构保持兼容）：

| 原 REST | 新命令 | 备注 |
|---|---|---|
| `GET /api/games` | `list_games` | 分页/筛选/排序 |
| `GET /api/games/collections` | `list_collections` | |
| `GET /api/games/events` | `list_events` | |
| `GET /api/games/:id` | `get_game` | |
| `POST /api/games` | `create_game` | |
| `PUT /api/games/:id` | `update_game` | |
| `DELETE /api/games/:id` | `delete_game` | |
| `POST /api/games/:id/open` | `open_game` | 写 activity |
| `POST /api/games/:id/favorite` | `favorite_game` | |
| `POST /api/games/parse` | `parse_moves` | 实时预览 |
| `POST /api/games/import-pgn` | `import_pgn` | |
| `POST /api/games/:id/check-move` | `check_move` | |
| `GET /api/review/queue` | `review_queue` | |
| `POST /api/review/:id/submit` | `submit_review` | SM-2 |
| `GET /api/stats` | `stats` | |
| `POST /api/engine/validate-move` | `validate_move` | 无状态 |
| `POST /api/engine/best-move` | `best_move` | |
| `POST /api/engine/validate-position` | `validate_position` | 摆子校验 |
| `POST /api/engine/analyze` | `analyze` | **Channel 流式** |
| `POST /api/engine/intent` | `intent` | **Channel 流式** |
| `POST /api/recognize` | `recognize` | bytes 入参 |
| `GET/POST /api/auth/*` | （移除） | 见 §10 |

约定：命令层返回 `Result<T, AppError>`，`AppError` 序列化为 `{ error, detail? }`，与现有后端错误 JSON 一致，前端 toast 逻辑复用。

## 12. 测试与验证策略

1. **规则引擎对拍**（Rust vs Python golden）：脚本导出局面/着法用例到 JSON fixtures，`cargo test` 比对 `is_legal`/`to_fen`/`move_to_chinese`/`parse`。
2. **引擎对拍**：固定局面、`threads=1`、固定深度，比对分与 PV；评估表由脚本从 `eval_tables.py` 转换后做逐元素校验。
3. **识别回归**：用现有测试图集比对 `pieces` 输出与 Python 版一致（允许模型固有误差，比对到同一结果）。
4. **前端单测**：现有 vitest 用例保持通过（`api` 层可 mock `@tauri-apps/api/core`）。
5. **真机验证**：Android 真机/模拟器跑通「扫描识别 + 实时分析 + 人机对战 + 背谱复习」全链路，观测识别耗时与引擎 NPS。

## 13. 构建与发布

### 13.1 环境（Linux/macOS 主机）

- Rust + `rustup target add aarch64-linux-android armv7-linux-androideabi i686-linux-android x86_64-linux-android`
- Android SDK（`ANDROID_HOME`）、NDK（`NDK_HOME`）、JDK 17/21（`JAVA_HOME`）
- `npm i -D @tauri-apps/cli`（或全局 CLI）

### 13.2 命令

```bash
# 初始化 Android 工程（生成 src-tauri/gen/android，一次性）
npx tauri android init

# 开发（真机/模拟器热更）
npx tauri android dev

# 调试 APK
npx tauri android build --debug --apk

# 发布：APK（国内商店）/ AAB（Google Play）
npx tauri android build --apk
npx tauri android build --aab
```

- 签名：配置 keystore（`gen/android/keystore.properties` + `build.gradle` signingConfig），发布必须正式签名。
- `tauri.conf.json`：`identifier` 用反域名（如 `com.yourname.chess`）、`version`、`bundle.resources` 纳模型、Android `minSdkVersion`（21+，建议 24+）。

### 13.3 上架要点

- Google Play：AAB、Play Console 账号、隐私政策、数据安全表单（本 App 纯离线、不采集数据，声明简单）；如含相机用途需说明。
- 国内应用商店：一般需 APK + 软件著作权证书 + 备案等，流程另计。
- 体积：内嵌识别模型后 APK 约 60–100MB（debug 更大）；发布版可开 R8/资源压缩。

## 14. 分阶段实施计划

| 阶段 | 内容 | 产出 | 预估 |
|---|---|---|---|
| P0 环境打通 | Tauri 工程脚手架；Vue dist 加载进 WebView；Android 真机跑通空壳 | 能安装的 APK、显示现有 UI | 1–2 天 |
| P1 离线 MVP | db 层 + 规则引擎移植 + games/review/srs 命令 + api 层改造 | **棋谱库 / 复习 / 背谱 全离线可用** | 1–2 周 |
| P2 AI 引擎 | engine 移植 + eval 表转换 + analysis/intent + Channel 流式 + 取消 | 实时分析 / 意图推演 / 人机对战可用 | 2–3 周 |
| P3 识别 | 图像原语 + ort 接入 + pose/classifier/pipeline + 模型打包 | 局面扫描可用 | 1–2 周 |
| P4 打包发布 | 签名、AAB/APK、图标/启动屏、隐私政策、上架 | 可上架制品 | 3–5 天 |

P1 结束即可得到一个「离线背谱 App」，AI 与识别作为后续增量，便于尽早验证与交付。

## 15. 风险与对策

| 风险 | 影响 | 对策 |
|---|---|---|
| Rust 引擎与 Python 行为不一致 | 分析/意图体验回退 | §12 对拍测试；先保证 `threads=1` 逐一等价 |
| Rust 引擎性能不及 Cython 后端 | 手机算得浅、发热 | 位棋盘 + 原生多线程；真机基准后再调搜索参数/时间预算 |
| `ort` + Android `.so` 集成踩坑 | 识别不可用 | 优先 POC 验证（§16）；备选改用 AAR 方式或 onnxruntime-android Java 桥 |
| Tauri Channel 取消语义 | 分析无法中断 | `jobs.rs` 取消令牌 + 线边界停；POC 验证 |
| Android 系统 WebView 兼容 | 旧机型渲染异常 | 设 minSdk 24+；真机矩阵测试 |
| APK 体积大（模型 42MB+） | 下载/上架体验 | 发布版压缩；必要时模型拆分/首启下载（权衡离线） |
| 纯 Rust 图像处理精度 | 识别率下降 | 与 cv2 输出对拍（透视/缩放中间结果），保证像素级一致 |

## 16. 先行技术验证（POC，建议 P0 内完成）

在投入大规模移植前，用最小样例验证三个高风险点：

1. **引擎**：Rust 实现位棋盘 + 单线程浅层搜索，跑初始局面，确认可编译到 `aarch64-linux-android` 并在真机运行、NPS 可接受。
2. **识别**：`ort` + `load-dynamic` 在真机加载 `libonnxruntime.so`，对一张棋盘图跑 `pose`+`layout`，与 Python 版输出一致。
3. **流式**：Tauri `Channel` 从 Rust 逐层推 `{type:"result"}` 到 Vue，并验证 `cancel_job` 能中断。

三点通过后再按 P1–P4 推进；任一不通过则调整对应选型（如识别改 AAR 桥、引擎改单线程保守参数）。

## 17. 遗留决策点

1. 是否保留 Web（浏览器）部署能力：若保留，`api/index.js` 需做「Tauri/HTTP」双实现，或维护两套分支；若纯 App 可删 HTTP 路径（本方案默认后者）。
2. 是否需要本地 PIN 保护（§10）。
3. 识别模型内嵌 vs 首启下载（§8.2）——当前按内嵌以兑现「完全离线」。
4. 是否同时发布桌面版（Tauri 天然支持，成本很低）。
