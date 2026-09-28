"""棋盘四角关键点检测（RTMPose / SimCC ONNX）。

输入整幅 RGB 图像，输出四个角点 A0/A8/J0/J8 的像素坐标与置信度：

- A0/A8：黑方底线两端；J0/J8：红方底线两端；
- 预处理为「整图 bbox + padding 1.25」的仿射变换到 256x256，
  ImageNet mean/std 归一化；输出 SimCC 编码，argmax 解码后经逆仿射回原图。

模型来自开源项目 TheOne1006/chinese-chess-recognition（pose ONNX）。
"""

import cv2
import numpy as np
import onnxruntime

INPUT_SIZE = (256, 256)
PADDING = 1.25
MEAN = np.array([123.675, 116.28, 103.53], dtype=np.float32)
STD = np.array([58.395, 57.12, 57.375], dtype=np.float32)
KEYPOINT_NAMES = ("A0", "A8", "J0", "J8")


def _third_point(a, b):
    direction = a - b
    return b + np.array([-direction[1], direction[0]], dtype=np.float32)


def _warp_matrix(center, scale, inv=False):
    """仿射矩阵：原图 bbox -> 256x256（inv=True 时取逆）。

    对应参考实现的 get_warp_size_with_input_size + get_warp_matrix
    （rot=0、shift=0、fix_aspect_ratio=True），先按 1:1 长宽比修正 scale。
    """
    out_w, out_h = INPUT_SIZE
    scale_w, scale_h = scale
    aspect = out_w / out_h
    if scale_w > scale_h * aspect:
        scale = (scale_w, scale_w / aspect)
    else:
        scale = (scale_h * aspect, scale_h)
    src_w, src_h = scale

    src = np.zeros((3, 2), dtype=np.float32)
    dst = np.zeros((3, 2), dtype=np.float32)
    src[0] = center
    src[1] = center + np.array([-src_w * 0.5, 0.0], dtype=np.float32)
    dst[0] = [out_w * 0.5, out_h * 0.5]
    dst[1] = [0.0, out_h * 0.5]
    src[2] = _third_point(src[0], src[1])
    dst[2] = _third_point(dst[0], dst[1])
    if inv:
        return cv2.getAffineTransform(dst, src)
    return cv2.getAffineTransform(src, dst)


def _bbox_center_scale(bbox):
    x1, y1, x2, y2 = bbox
    center = np.array([(x1 + x2) / 2.0, (y1 + y2) / 2.0], dtype=np.float32)
    scale = np.array([(x2 - x1) * PADDING, (y2 - y1) * PADDING], dtype=np.float32)
    return center, scale


def _preprocess(image_rgb, warp_mat):
    warped = cv2.warpAffine(image_rgb, warp_mat, INPUT_SIZE, flags=cv2.INTER_LINEAR)
    norm = (warped.astype(np.float32) - MEAN) / STD
    blob = np.transpose(norm, (2, 0, 1))[None]
    return np.ascontiguousarray(blob, dtype=np.float32)


def _decode(simcc_x, simcc_y, center, scale):
    """SimCC 解码：argmax 归一化坐标 -> 256 坐标系 -> 逆仿射回原图。"""
    out_w, out_h = INPUT_SIZE
    x_idx = np.argmax(simcc_x[0], axis=1).astype(np.float64)
    y_idx = np.argmax(simcc_y[0], axis=1).astype(np.float64)
    keypoints = np.stack([x_idx / (out_w * 2) * out_w, y_idx / (out_h * 2) * out_h], axis=1)
    scores = np.max(simcc_x[0], axis=1) * np.max(simcc_y[0], axis=1)

    inv_mat = _warp_matrix(center, scale, inv=True)
    homogeneous = np.hstack([keypoints, np.ones((keypoints.shape[0], 1))])
    original = homogeneous @ inv_mat.T
    return original, scores


class PoseDetector:
    """四角关键点检测器。"""

    def __init__(self, model_path, session=None):
        if session is None:
            session = onnxruntime.InferenceSession(
                model_path, providers=["CPUExecutionProvider"]
            )
        self.session = session
        self.input_name = self.session.get_inputs()[0].name

    def detect(self, image_rgb):
        """返回 (keypoints[4,2], scores[4])，keypoints 为原图像素坐标。"""
        height, width = image_rgb.shape[:2]
        center, scale = _bbox_center_scale([0, 0, width, height])
        warp_mat = _warp_matrix(center, scale)
        blob = _preprocess(image_rgb, warp_mat)
        simcc_x, simcc_y = self.session.run(None, {self.input_name: blob})
        return _decode(simcc_x, simcc_y, center, scale)
