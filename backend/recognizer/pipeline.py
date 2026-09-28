"""识别流水线：关键点 -> 透视校正 -> 布局分类 -> 棋子数组。

棋盘方向约定：透视变换把 [A0, A8, J0, J8]（黑方两端 + 红方两端）映射到
左上/右上/左下/右下，因此校正后第 0 行为黑方底线，与象棋 FEN 一致。
"""

import time

import cv2
import numpy as np

from .classifier import LayoutClassifier
from .errors import BoardNotFound
from .pose import PoseDetector

PERSPECTIVE_DST = (450, 500)  # (w, h)
PERSPECTIVE_PADDING = 50
KEYPOINT_SCORE_THRESHOLD = 0.1
MIN_BOARD_AREA_RATIO = 0.05
LOW_CONFIDENCE = 0.5
MAX_SIDE = 2048
ROWS, COLS = 10, 9


def _limit_size(image_rgb, max_side=MAX_SIDE):
    height, width = image_rgb.shape[:2]
    longest = max(height, width)
    if longest <= max_side:
        return image_rgb
    scale = max_side / longest
    return cv2.resize(
        image_rgb,
        (max(1, int(round(width * scale))), max(1, int(round(height * scale)))),
        interpolation=cv2.INTER_AREA,
    )


def _board_geometry_ok(keypoints, image_shape):
    """四角须构成凸四边形，且面积占画面比例不低于阈值。"""
    points = np.asarray(keypoints, dtype=np.float32).reshape(-1, 1, 2)
    hull = cv2.convexHull(points)
    if len(hull) != 4:
        return False
    area = abs(float(cv2.contourArea(hull)))
    height, width = image_shape[:2]
    return area >= MIN_BOARD_AREA_RATIO * width * height


def extract_board(image_rgb, keypoints):
    """按四角关键点透视校正为固定尺寸俯视棋盘。"""
    width, height = PERSPECTIVE_DST
    pad = PERSPECTIVE_PADDING
    src = np.float32(keypoints[:4])
    dst = np.float32(
        [[pad, pad], [width - pad, pad], [pad, height - pad], [width - pad, height - pad]]
    )
    matrix = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(image_rgb, matrix, (width, height))


def labels_to_pieces(labels, confidences):
    """10x9 类别矩阵 -> 棋子数组 + 中文警告。

    空格 `.` 跳过；遮挡 `x` 按空位处理并计数；置信度低于阈值的棋子计数提示。
    """
    pieces = []
    blocked = 0
    low = 0
    for row_index, row in enumerate(labels):
        for col_index, label in enumerate(row):
            if label == "x":
                blocked += 1
                continue
            if label == ".":
                continue
            if confidences[row_index][col_index] < LOW_CONFIDENCE:
                low += 1
            pieces.append(
                {
                    "x": col_index,
                    "y": 9 - row_index,
                    "side": "red" if label.isupper() else "black",
                    "kind": label.upper(),
                }
            )

    warnings = []
    if blocked:
        warnings.append(f"检测到 {blocked} 处遮挡，已按空位处理")
    if low:
        warnings.append(f"{low} 个格子识别置信度较低，请核对")
    return pieces, warnings


class BoardRecognizer:
    """加载两个 ONNX 模型并完成一次完整识别。"""

    def __init__(self, pose_path, layout_path):
        self._pose = PoseDetector(pose_path)
        self._layout = LayoutClassifier(layout_path)

    def recognize(self, image_bgr):
        image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        image_rgb = _limit_size(image_rgb)

        start = time.perf_counter()
        keypoints, scores = self._pose.detect(image_rgb)
        pose_done = time.perf_counter()
        if float(np.min(scores)) < KEYPOINT_SCORE_THRESHOLD or not _board_geometry_ok(
            keypoints, image_rgb.shape
        ):
            raise BoardNotFound("未检测到棋盘，请让棋盘完整入镜后重试")

        warped = extract_board(image_rgb, keypoints)
        labels, confidences = self._layout.predict(warped)
        classify_done = time.perf_counter()

        pieces, warnings = labels_to_pieces(labels, confidences)
        return {
            "pieces": pieces,
            "layout": ["".join(row) for row in labels],
            "warnings": warnings,
            "stats": {
                "pose_ms": round((pose_done - start) * 1000),
                "classify_ms": round((classify_done - pose_done) * 1000),
                "keypoint_scores": [round(float(score), 4) for score in scores],
                "confidences": [
                    [round(float(value), 4) for value in row] for row in confidences
                ],
            },
        }
