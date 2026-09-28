"""棋盘关键点检测（pose）单元测试：仿射矩阵与 SimCC 解码数学。"""

import numpy as np
import pytest

from recognizer.pose import (
    INPUT_SIZE,
    _bbox_center_scale,
    _decode,
    _third_point,
    _warp_matrix,
)


def test_third_point_is_perpendicular():
    assert _third_point(np.array([10.0, 0.0]), np.array([0.0, 0.0])).tolist() == [0.0, 10.0]


def test_bbox_center_scale_applies_padding():
    center, scale = _bbox_center_scale([0, 0, 100, 200])
    assert center.tolist() == [50.0, 100.0]
    assert scale.tolist() == [125.0, 250.0]


def test_warp_matrix_round_trip():
    center = np.array([320.0, 240.0])
    scale = np.array([400.0, 300.0])
    forward = _warp_matrix(center, scale)
    inverse = _warp_matrix(center, scale, inv=True)

    point = np.array([100.0, 50.0])
    warped = forward @ np.append(point, 1.0)
    restored = inverse @ np.append(warped, 1.0)
    assert restored[:2] == pytest.approx(point, abs=1e-3)


def test_decode_recovers_original_points():
    """构造理想 SimCC 输出，验证解码 + 逆仿射能把关键点还原到原图。"""
    center = np.array([200.0, 150.0])
    scale = np.array([400.0, 300.0])
    forward = _warp_matrix(center, scale)

    original = np.array(
        [[50.0, 40.0], [350.0, 40.0], [50.0, 260.0], [350.0, 260.0]], dtype=np.float64
    )
    homogeneous = np.hstack([original, np.ones((4, 1))])
    warped = (forward @ homogeneous.T).T

    out_w, out_h = INPUT_SIZE
    simcc_x = np.zeros((1, 4, out_w * 2), dtype=np.float32)
    simcc_y = np.zeros((1, 4, out_h * 2), dtype=np.float32)
    for index, (wx, wy) in enumerate(warped):
        simcc_x[0, index, int(round(wx * 2))] = 1.0
        simcc_y[0, index, int(round(wy * 2))] = 1.0

    keypoints, scores = _decode(simcc_x, simcc_y, center, scale)
    assert keypoints == pytest.approx(original, abs=1.0)
    assert scores.tolist() == [1.0, 1.0, 1.0, 1.0]
