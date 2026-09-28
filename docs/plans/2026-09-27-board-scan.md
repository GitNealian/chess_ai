# 移动端摄像头扫描棋盘实现记录

日期：2026-09-27

对应设计：`docs/plans/2026-09-27-board-scan-design.md`

## 概述

移动端新增「扫描」功能：拍照/相册选图 → 后端 OpenCV + ONNX 两步识别 → 编辑器核对修正 → 一键加载局面。

识别对象为屏幕上的任意象棋软件画面、截图与本项目棋盘；不含实体棋盘（实体棋盘亦可尝试，但准确率不保证）。

## 识别链路

```
原图（前端 canvas 压缩至长边 ≤1600、JPEG 0.85）
  → 后端 imdecode BGR → RGB
  → 缩图（长边 ≤2048，INTER_AREA）
  → pose.onnx：整图 affine(padding 1.25) 到 256x256，ImageNet 归一化，
      SimCC argmax 解码 → 逆仿射回原图 → 4 角点 A0/A8/J0/J8 + 置信度
  → 判定：min(置信度) ≥ 0.1 且四角凸包为四边形且面积占画面 ≥5%，否则拒绝
  → warpPerspective：[A0,A8,J0,J8] → 左上/右上/左下/右下，输出 450x500（padding 50）
  → layout.onnx：center-crop 400x450 → resize 280x315（w,h），同一归一化
      → 输出 90x16 → argmax → 10 行 x 9 列类别
  → labels_to_pieces：第 r 行第 c 列 → (x=c, y=9-r)；大写红、小写黑；
      `x` 遮挡按空位 + 警告；置信度 <0.5 计低置信度警告
```

模型文件（`backend/weights/`，不入库）：

| 文件 | 来源 | 大小 |
|---|---|---|
| `pose.onnx` | `onnx/pose/4_v6-0301.onnx` | 10.7MB |
| `layout.onnx` | `onnx/layout_recognition/nano_v3-0319.onnx` | 31.1MB |

来源为开源项目 TheOne1006/chinese-chess-recognition 的 ONNX 导出（HF Space `yolo12138/Chinese_Chess_Recognition`），下载脚本 `backend/scripts/download_models.py`。

## 后端

| 文件 | 内容 |
|---|---|
| `recognizer/pose.py` | `_warp_matrix`（bbox 仿射 + 长宽比修正，支持 inv）、`_decode`（SimCC 解码 + 逆仿射）、`PoseDetector.detect` |
| `recognizer/classifier.py` | `_center_crop`、`_preprocess`、`LayoutClassifier.predict`（90x16 argmax） |
| `recognizer/pipeline.py` | `_limit_size`、`_board_geometry_ok`、`extract_board`、`labels_to_pieces`、`BoardRecognizer.recognize` |
| `recognizer/errors.py` | `RecognitionError` / `BoardNotFound` / `ModelNotInstalled` |
| `recognizer/__init__.py` | 懒加载单例（double-checked locking）、识别串行锁、`recognize_image` |
| `routes/recognize.py` | `POST /api/recognize`，错误映射 400 / 413 / 503 |
| `scripts/download_models.py` | urllib 下载模型（支持 --dir / --force，尊重代理环境变量） |
| `scripts/recognize_cli.py` | 离线调试：图片 → 10x9 文本 + 每格置信度 + 关键点分数，可选导出校正图 |

配置与注册：`config.py` 增加模块级 `WEIGHTS_DIR`（环境变量可覆盖）与 `Config.MAX_CONTENT_LENGTH`（8MB）；`app.py` 注册 `/api/recognize` 蓝图并新增 413 JSON 处理器。

关键实现决策：

- **阈值 0.1 + 几何校验**：参考实现不用 pose 置信度判定失败（仅用于绘制）。实测有棋盘图片四角置信度普遍仅 0.13~0.34，而无棋盘图片（纯色 / 噪声 / 风景）≤0.099，故取 0.1 为下限；四角关键点顺序为 A0→A8→J0→J8（Z 字形），`contourArea` 会因自交而失真，几何校验改用 `convexHull` 后判断凸四边形 + 面积占比。
- 通道统一为 RGB 流水线（`imdecode` 得 BGR 后立即转 RGB），与参考实现语义一致。
- 模型缺失时接口返回 503，服务启动不受影响；识别调用持模块级锁串行执行。

## 前端

| 文件 | 改动 |
|---|---|
| `api/index.js` | 新增 `recognize(formData, config)` |
| `mobile/components/MobileScanDialog.vue` | 新增：`pick → loading → edit` 阶段机 |
| `mobile/components/BoardControls.vue` | 新增 `canScan` 与「扫描」按钮（emit `scan`），样式加 `flex-wrap` |
| `mobile/components/MobileBoardEditor.vue` | 新增可选 props `title` / `notice`（默认值保持原行为） |
| `mobile/views/MobileHomeView.vue` | 新增 `scanOpen`，接入扫描弹层；`onApply` 同时关闭两个弹层 |

交互：

- **pick**：提示文案 + 「拍照」（`capture="environment"`）「相册」两个 file input。不引入 `getUserMedia`（局域网 HTTP 非安全上下文不可用，file input 可直接调起系统相机且兼容相册）。
- **loading**：`createImageBitmap` + canvas 压缩（长边 ≤1600、JPEG 0.85）后以 `FormData` 上传，`AbortController` 可取消，60s 超时。
- **edit**：识别成功直接渲染 `MobileBoardEditor`（标题「识别结果」、notice 汇总后端 warnings），修正逻辑完全复用；组装 pieces 时补 `label`（`ChessBoard` 依赖它渲染汉字）。
- 失败回到 pick 并展示后端中文错误，可重试。

## 测试

后端新增 19 项：

- `tests/test_recognizer_pose.py`：仿射矩阵正逆一致、SimCC 解码还原原图坐标、bbox padding。
- `tests/test_recognizer_pipeline.py`：labels→pieces 坐标与红黑映射、遮挡/低置信度警告、透视四角方向、几何校验、缩图、stub 端到端与低置信度拒绝。
- `tests/test_recognize_api.py`：成功契约、缺字段、空文件、三类错误映射（400/400/503）、413 超大、真实模型集成（`RECOGNIZE_TEST_IMAGE` 未设置时跳过）。

前端新增/更新：`MobileScanDialog.test.js`（阶段流转、压缩上传、成功/失败/进度、apply/cancel 透传）、`BoardControls` 扫描按钮、`MobileBoardEditor` title/notice、`MobileHomeView` 扫描入口与应用。

## 验证结果

- 后端全量 `pytest`：563 passed + 1 skipped（含真实模型集成）；前端全量 `vitest`：324 passed。
- 真实 HTTP 端到端（`app.py` 启动后 curl）：本项目棋盘截图 → 32 子全对；风景照 → `{"error": "未检测到棋盘…"}`；缺字段 → `{"error": "缺少图片文件"}`。
- 模型效果实测（`scripts/recognize_cli.py`）：
  - 本项目棋盘截图（按 `ChessBoard.vue` 样式合成）与象棋游戏画面：**32 子全对、无警告**；
  - 真实拍摄照片（含倾斜、遮挡）：残局基本正确，遮挡格与低置信度会给出警告；
  - 纯色 / 噪声 / 风景：正确拒绝；
  - 单张耗时：pose 5~10ms + classify 92~100ms（首次另含模型加载约 1~2s）。

## 后续可选项

- 识别方向偶发倒置时，可在 edit 阶段加「旋转 180°」按钮（纯坐标变换 `x'=8-x, y'=9-y`）。
- 低置信度格在棋盘上高亮标注（当前仅文字提示）。
- 实时取景识别（需 HTTPS）或上传前手动点选四角以提升倾斜场景成功率。
