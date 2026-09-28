"""棋盘识别：摄像头照片/截图 -> 局面。

两级 ONNX 模型（四角关键点检测 + 10x9 布局分类）来自开源项目
TheOne1006/chinese-chess-recognition 的 ONNX 导出，文件默认位于
`WEIGHTS_DIR`（backend/weights/）：可用 `scripts/download_models.py` 下载。

对外接口：

- `recognize_image(bytes)`：解码图片并识别，返回 `pieces`/`layout`/
  `warnings`/`stats`；模型缺失抛 `ModelNotInstalled`；
- `models_installed()`：模型文件是否齐备；
- 识别串行执行（模块级锁），避免单机并发推理打满 CPU。
"""

import os
import threading

import cv2
import numpy as np

from config import WEIGHTS_DIR

from .errors import BoardNotFound, ModelNotInstalled, RecognitionError
from .pipeline import BoardRecognizer

POSE_MODEL = "pose.onnx"
LAYOUT_MODEL = "layout.onnx"

__all__ = [
    "BoardNotFound",
    "ModelNotInstalled",
    "RecognitionError",
    "recognize_image",
    "models_installed",
]

_recognizer = None
_load_lock = threading.Lock()
_run_lock = threading.Lock()


def model_files():
    return os.path.join(WEIGHTS_DIR, POSE_MODEL), os.path.join(WEIGHTS_DIR, LAYOUT_MODEL)


def models_installed():
    return all(os.path.isfile(path) for path in model_files())


def get_recognizer():
    """懒加载单例（double-checked locking）。"""
    global _recognizer
    if _recognizer is not None:
        return _recognizer
    with _load_lock:
        if _recognizer is None:
            pose_path, layout_path = model_files()
            if not (os.path.isfile(pose_path) and os.path.isfile(layout_path)):
                raise ModelNotInstalled("识别模型未安装，请先运行 scripts/download_models.py")
            _recognizer = BoardRecognizer(pose_path, layout_path)
    return _recognizer


def recognize_image(image_bytes):
    image = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise RecognitionError("无法解析图片")
    with _run_lock:
        return get_recognizer().recognize(image)
