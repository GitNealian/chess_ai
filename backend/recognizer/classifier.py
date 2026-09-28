"""棋盘布局分类（10x9x16 ONNX）。

输入透视校正后的俯视棋盘（450x500 RGB）：center-crop 400x450 →
resize 280x315 → ImageNet mean/std 归一化；输出 90x16，argmax 得
10 行 x 9 列类别（第 0 行为黑方底线）。

模型来自开源项目 TheOne1006/chinese-chess-recognition（layout ONNX）。
"""

import cv2
import numpy as np
import onnxruntime

CROP_SIZE = (400, 450)  # (w, h)
INPUT_SIZE = (280, 315)  # (w, h)
MEAN = np.array([123.675, 116.28, 103.53], dtype=np.float32)
STD = np.array([58.395, 57.12, 57.375], dtype=np.float32)
CLASSES = (".", "x", "K", "A", "B", "N", "R", "C", "P", "k", "a", "b", "n", "r", "c", "p")
ROWS, COLS = 10, 9


def _center_crop(image, target_w, target_h):
    height, width = image.shape[:2]
    if width < target_w or height < target_h:
        image = cv2.resize(image, (max(target_w, width), max(target_h, height)))
        height, width = image.shape[:2]
    x0 = (width - target_w) // 2
    y0 = (height - target_h) // 2
    return image[y0 : y0 + target_h, x0 : x0 + target_w]


def _preprocess(image_rgb):
    cropped = _center_crop(image_rgb, CROP_SIZE[0], CROP_SIZE[1])
    resized = cv2.resize(cropped, INPUT_SIZE, interpolation=cv2.INTER_LINEAR)
    norm = (resized.astype(np.float32) - MEAN) / STD
    blob = np.transpose(norm, (2, 0, 1))[None]
    return np.ascontiguousarray(blob, dtype=np.float32)


class LayoutClassifier:
    """俯视棋盘布局分类器。"""

    def __init__(self, model_path, session=None):
        if session is None:
            session = onnxruntime.InferenceSession(
                model_path, providers=["CPUExecutionProvider"]
            )
        self.session = session
        self.input_name = self.session.get_inputs()[0].name

    def predict(self, image_rgb):
        """返回 (labels[10][9] str, confidences[10][9] float)。"""
        blob = _preprocess(image_rgb)
        (outputs,) = self.session.run(None, {self.input_name: blob})
        first = outputs[0]
        assert first.shape == (ROWS * COLS, len(CLASSES)), f"输出形状异常：{first.shape}"

        indexes = np.argmax(first, axis=-1)
        scores = first[np.arange(first.shape[0]), indexes]
        labels = [CLASSES[i] for i in indexes.tolist()]
        labels_2d = [labels[r * COLS : (r + 1) * COLS] for r in range(ROWS)]
        scores_2d = [scores[r * COLS : (r + 1) * COLS].tolist() for r in range(ROWS)]
        return labels_2d, scores_2d
