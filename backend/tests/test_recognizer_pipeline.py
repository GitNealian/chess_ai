"""识别流水线单元测试：布局映射、透视校正、几何校验、整体流程。"""

import numpy as np
import pytest

from recognizer.errors import BoardNotFound
from recognizer.pipeline import (
    COLS,
    _board_geometry_ok,
    _limit_size,
    extract_board,
    labels_to_pieces,
)
from recognizer.pipeline import BoardRecognizer


def _labels(cells):
    rows = [["."] * COLS for _ in range(10)]
    for (row, col), value in cells.items():
        rows[row][col] = value
    return ["".join(row) for row in rows]


def _conf(value=1.0):
    return [[value] * COLS for _ in range(10)]


def test_labels_to_pieces_maps_coordinates_and_sides():
    labels = _labels({(0, 0): "r", (0, 4): "k", (9, 0): "R", (9, 4): "K", (3, 2): "p"})
    pieces, warnings = labels_to_pieces(labels, _conf())
    by_pos = {(piece["x"], piece["y"]): piece for piece in pieces}
    assert by_pos[(0, 9)] == {"x": 0, "y": 9, "side": "black", "kind": "R"}
    assert by_pos[(4, 9)] == {"x": 4, "y": 9, "side": "black", "kind": "K"}
    assert by_pos[(0, 0)] == {"x": 0, "y": 0, "side": "red", "kind": "R"}
    assert by_pos[(4, 0)] == {"x": 4, "y": 0, "side": "red", "kind": "K"}
    assert by_pos[(2, 6)] == {"x": 2, "y": 6, "side": "black", "kind": "P"}
    assert warnings == []


def test_labels_to_pieces_warns_on_blocked_and_low_confidence():
    labels = _labels({(1, 1): "x", (2, 2): "x", (5, 5): "P"})
    conf = _conf()
    conf[5][5] = 0.2
    pieces, warnings = labels_to_pieces(labels, conf)
    assert len(pieces) == 1
    assert warnings == ["检测到 2 处遮挡，已按空位处理", "1 个格子识别置信度较低，请核对"]


def test_extract_board_maps_four_corners_to_target():
    """A0/A8/J0/J8 应分别落在 左上/右上/左下/右下。"""
    image = np.zeros((200, 300, 3), dtype=np.uint8)
    image[0:40, 0:40] = [255, 0, 0]
    image[0:40, 260:300] = [0, 255, 0]
    image[160:200, 0:40] = [0, 0, 255]
    image[160:200, 260:300] = [255, 255, 0]
    keypoints = np.array([[0, 0], [299, 0], [0, 199], [299, 199]], dtype=np.float32)

    warped = extract_board(image, keypoints)
    assert warped.shape == (500, 450, 3)
    assert warped[60, 60].tolist() == [255, 0, 0]
    assert warped[60, 390].tolist() == [0, 255, 0]
    assert warped[440, 60].tolist() == [0, 0, 255]
    assert warped[440, 390].tolist() == [255, 255, 0]


def test_board_geometry_ok():
    shape = (1000, 1000, 3)
    good = np.array([[100, 100], [900, 120], [120, 880], [880, 900]], dtype=np.float32)
    assert _board_geometry_ok(good, shape)
    small = np.array([[10, 10], [60, 12], [12, 58], [58, 60]], dtype=np.float32)
    assert not _board_geometry_ok(small, shape)
    collinear = np.array([[100, 100], [200, 100], [300, 100], [400, 100]], dtype=np.float32)
    assert not _board_geometry_ok(collinear, shape)


def test_limit_size_scales_down_long_side():
    large = np.zeros((1000, 3000, 3), dtype=np.uint8)
    assert _limit_size(large, max_side=1000).shape[:2] == (333, 1000)
    small = np.zeros((100, 200, 3), dtype=np.uint8)
    assert _limit_size(small, max_side=1000) is small


class _StubPose:
    def __init__(self, scores=(0.9, 0.9, 0.9, 0.9)):
        self.scores = scores

    def detect(self, _image):
        return np.array([[0, 0], [100, 0], [0, 100], [100, 100]], dtype=np.float32), np.array(
            self.scores, dtype=np.float32
        )


class _StubLayout:
    def __init__(self, labels, confidences):
        self.labels = labels
        self.confidences = confidences

    def predict(self, _image):
        return self.labels, self.confidences


def _recognizer(pose, layout):
    recognizer = BoardRecognizer.__new__(BoardRecognizer)
    recognizer._pose = pose
    recognizer._layout = layout
    return recognizer


def test_board_recognizer_end_to_end_with_stubs():
    labels = _labels({(0, 0): "r", (9, 0): "R"})
    recognizer = _recognizer(_StubPose(), _StubLayout(labels, _conf()))
    result = recognizer.recognize(np.zeros((200, 200, 3), dtype=np.uint8))
    assert result["layout"] == labels
    assert len(result["pieces"]) == 2
    assert result["warnings"] == []
    assert set(result["stats"]) == {"pose_ms", "classify_ms", "keypoint_scores", "confidences"}


def test_board_recognizer_rejects_low_confidence_keypoints():
    labels = _labels({(0, 0): "r"})
    recognizer = _recognizer(
        _StubPose(scores=(0.9, 0.9, 0.9, 0.01)), _StubLayout(labels, _conf())
    )
    with pytest.raises(BoardNotFound):
        recognizer.recognize(np.zeros((200, 200, 3), dtype=np.uint8))
