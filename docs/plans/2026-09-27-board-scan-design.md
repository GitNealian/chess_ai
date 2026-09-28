# 移动端摄像头扫描棋盘设计

日期：2026-09-27

## 目标

在移动端（`/m`）新增「扫描」功能：

1. 手机打开摄像头拍摄屏幕上的中国象棋棋盘，或从相册选择截图；
2. 由后端自动识别为局面；
3. 用户在前端预览识别结果并手动修正；
4. 确认后加载进棋盘（复用现有摆棋编辑器的应用流程）。

范围：仅移动端。识别对象为任意象棋软件/网页画面、截图、本 APP 自身棋盘画面；不含实体棋盘。

## 技术方案

**识别路线：后端 Python + OpenCV + 开源 ONNX 预训练模型（两步式）**

采用开源项目 `TheOne1006/chinese-chess-recognition` 的预训练模型（托管于 HF Space `yolo12138/Chinese_Chess_Recognition`）：

| 步骤 | 模型 | 输入规格 | 输出规格 |
|---|---|---|---|
| 1. 棋盘定位（pose） | `onnx/pose/4_v6-0301.onnx`（10.7MB） | 原图仿射到 1×3×256×256，ImageNet mean/std = `123.675/116.28/103.53`、`58.395/57.12/57.375` | 4 角点 A0/A8/J0/J8 的 SimCC 编码，两组 `1×4×512`，argmax 除以 512 解码；置信度低于 0.6 判失败 |
| 2. 透视校正 | OpenCV `warpPerspective` | 4 角点 `[A0, A8, J0, J8]` → 左上/右上/左下/右下 | 450×500 俯视棋盘（边距 padding=50） |
| 3. 棋子分类（reg） | `onnx/layout_recognition/nano_v3-0319.onnx`（31.1MB） | center-crop 400×450 → resize `1×3×315×280`，同 mean/std | 90（10 行×9 列）×16 分类：空 `.`、遮挡 `x`、红 `K A B N R C P`、黑 `k a b n r c p` |

关键映射：

- 输出第 r 行第 c 列 → 本项目坐标 `x=c, y=9-r`（透视后黑方 A 行在上，与 FEN 方向一致）。
- 大写红、小写黑，与前端 `fenToPieces` / `LABELS` 的 kind 体系完全一致。
- 遮挡 `x` 按空位处理并产生警告；无法识别行棋方，默认红先（编辑器内可改）。
- 模型作者口径：整盘全对率约 83%、误差不超过 3 子 96%。本功能以「预览 + 人工修正」兜底。

**为何用 file input 而非 getUserMedia**：局域网 HTTP 部署下 `getUserMedia` 需要 HTTPS（secure context）不可用；`<input type="file" accept="image/*" capture="environment">` 可直接调起系统相机，且兼容相册选图。v1 不做实时取景。

## 数据流

```
手机拍照/相册选图
  → canvas 压缩（长边 ≤1600、JPEG 0.85）
  → POST /api/recognize（multipart，支持取消）
  → 后端加锁串行：缩图（长边 ≤2048）→ pose → 置信度检查 → 透视 → reg
  → 返回 pieces/layout/warnings
  → MobileScanDialog 进入编辑预览（预填识别结果）
  → 用户修正 → POST /api/engine/validate-position（现有逻辑）
  → onApply 加载进棋盘
```

## 后端设计

### 新增接口 `POST /api/recognize`

- 请求：`multipart/form-data`，字段 `image`（必填）。
- 成功 200 返回：
  - `pieces`：`[{x, y, side, kind}]`
  - `layout`：10 行 9 列原始字符数组（便于调试）
  - `warnings`：中文提示数组（如「3 个格子识别置信度较低，请核对」「检测到 1 处遮挡，已按空位处理」）
  - `stats`：`{pose_ms, classify_ms, keypoint_scores}`
- 错误：400「无法解析图片」/「未检测到棋盘，请让棋盘完整入镜后重试」；413 图片过大（`MAX_CONTENT_LENGTH=8MB`）；503「识别模型未安装」（`weights/` 缺文件，启动不因此失败）。
- 复用现有约定：蓝图 + `jsonify` + 中文 `error` 字段；鉴权沿用全局 session 拦截，无需白名单。

### 模块与文件

```
backend/recognizer/__init__.py      # 懒加载单例（double-checked locking）+ 识别锁 + get_recognizer()
backend/recognizer/pose.py          # 仿射预处理、SimCC 解码、逆变换回原图
backend/recognizer/classifier.py    # crop/resize/normalize、90×16 argmax 解码
backend/recognizer/pipeline.py      # 4 点透视、labels 转 pieces、警告聚合
backend/routes/recognize.py         # 蓝图，注册于 /api/recognize
backend/scripts/download_models.py  # 从 HF 下载模型到 backend/weights/（urllib，无新依赖）
backend/scripts/recognize_cli.py    # 离线调试：图片路径 → 10×9 文本 + 置信度
```

说明：

- 模型目录命名为 `backend/weights/`（避免与 `backend/models.py` 同名冲突），模型文件为 `pose.onnx`、`layout.onnx`；`weights/` 加入 `.gitignore`。
- `app.py`：注册蓝图、413 JSON 错误处理。
- `config.py`：新增 `MAX_CONTENT_LENGTH`、`WEIGHTS_DIR`（可环境变量覆盖），`TestConfig` 自动继承。
- `requirements.txt`：新增 `opencv-python-headless`、`onnxruntime`；`numpy` 已有。
- 颜色通道约定：内部统一 RGB 流水线（`imdecode` 得 BGR 后转 RGB），避免红黑颠倒。

## 前端设计

| 文件 | 改动 |
|---|---|
| `src/api/index.js` | 新增 `recognize(formData, config)` |
| `src/mobile/components/MobileScanDialog.vue` | 新增组件：阶段机 `pick → loading → edit` |
| `src/mobile/components/BoardControls.vue` | 新增 `canScan` prop 与「扫描」按钮（emit `scan`）；样式加 `flex-wrap` |
| `src/mobile/components/MobileBoardEditor.vue` | 新增可选 props `title`（默认「编辑局面」）与 `notice`（默认空），保持向后兼容 |
| `src/mobile/views/MobileHomeView.vue` | 新增 `scanOpen` 状态；监听 `scan`；`apply` 复用现有 `onApply`（并关闭弹层） |

### `MobileScanDialog` 交互

- **pick**：提示文案（「将屏幕上的棋盘完整放入画面，尽量正对拍摄，避免反光」）+ 两个按钮「拍照」（file input 带 `capture="environment"`）「相册」（无 `capture`）。
- **loading**：显示「识别中…」+ 取消按钮（`AbortController`）；失败显示后端中文错误 + 「重试」。
- **edit**：识别成功直接渲染 `MobileBoardEditor` 并预填识别结果，标题「识别结果」、`notice` 显示识别警告——同一时刻只有一个遮罩，修正逻辑完全复用（点棋子移动/删除、棋子面板补子、红先/黑先、确认时 `validate-position`）。
- 组装 `pieces` 时补 `label`（`ChessBoard` 依赖 `label` 渲染汉字）。
- 压缩：`createImageBitmap` + canvas `toBlob`（jpeg 0.85），老旧浏览器回退 `img` + `URL.createObjectURL`。

## 边界与错误处理

- 识别失败（未检测到棋盘、图片无法解析、模型未安装、网络错误）均在 `pick` 阶段回到可重试状态并展示中文提示。
- 遮挡 `x` 与低置信度格按空位处理，由编辑器 `validate-position` 最终兜底（如出现非法局面会提示修正）。
- 取消识别：中止请求、释放对象 URL、关闭弹层。
- 从识别结果确认时，`onApply` 同时关闭扫描弹层与编辑弹层，并清理棋谱上下文（与手动编辑一致）。

## 测试

后端（`backend` 下执行 `.venv/bin/python -m pytest`）：

- `tests/test_recognizer_pose.py`：SimCC 解码、仿射逆变换数学（构造理想输出验证坐标）。
- `tests/test_recognizer_pipeline.py`：labels 转 pieces 映射（含遮挡与低置信度警告）、透视变换方向、警告聚合。
- `tests/test_recognize_api.py`：monkeypatch 识别器为假实现，测成功契约、未检测到棋盘 400、非图片 400、缺文件 400、模型缺失 503、超大 413。
- 集成测试（真模型 + 真图片）：模型或环境变量图片缺失时跳过。

前端（`frontend` 下执行 `npm run test`）：

- `MobileScanDialog.test.js`（新增）：阶段流转、mock `api.recognize` 成功/失败、取消、apply 冒泡；mock `createImageBitmap` 与 canvas。
- `BoardControls.test.js`：scan 按钮显隐与 emit。
- `MobileBoardEditor.test.js`：`title`/`notice` 默认值与原行为兼容。
- `MobileHomeView.test.js`：点击扫描打开弹层、apply 后局面更新。

人工端到端：手机访问 `/m` 实测本 APP 截图、天天象棋类界面、手机拍电脑屏幕三类画面。

## 风险

1. 模型许可证未声明（源仓库无 LICENSE）：仅自用；模型与代码解耦（`weights/` 不入库）。
2. 屏幕画面效果待实测：摩尔纹/反光/倾斜可能降低准确率，靠人工修正兜底或增加拍摄引导。
3. 模型下载依赖 HuggingFace 网络，脚本失败时支持手动放置。
4. CPU 推理约 1~4 秒：接口加锁串行，前端 loading 且可取消。
