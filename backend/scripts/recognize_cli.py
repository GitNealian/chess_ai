#!/usr/bin/env python3
"""离线运行棋盘识别（调试/实测用）。

用法：
    python scripts/recognize_cli.py 图片路径
    python scripts/recognize_cli.py 图片路径 --dump /tmp/warped.png

输出 10 行 x 9 列类别（第 0 行为黑方底线，`.` 空、`x` 遮挡）、
每格置信度、关键点置信度与用时；`--dump` 可导出透视校正后的棋盘图。
"""

import argparse
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from recognizer import ModelNotInstalled, RecognitionError, get_recognizer  # noqa: E402
from recognizer.pipeline import _limit_size, extract_board  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="离线棋盘识别")
    parser.add_argument("image", help="图片路径")
    parser.add_argument("--dump", help="导出透视校正后的棋盘图路径")
    args = parser.parse_args()

    image_bgr = cv2.imread(args.image)
    if image_bgr is None:
        print(f"无法读取图片：{args.image}", file=sys.stderr)
        return 1

    try:
        recognizer = get_recognizer()
    except ModelNotInstalled as exc:
        print(exc, file=sys.stderr)
        return 1

    rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    rgb = _limit_size(rgb)
    keypoints, scores = recognizer._pose.detect(rgb)
    print("关键点置信度：", [round(float(s), 3) for s in scores])
    warped = extract_board(rgb, keypoints)
    if args.dump:
        cv2.imwrite(args.dump, cv2.cvtColor(warped, cv2.COLOR_RGB2BGR))
        print(f"已导出校正图：{args.dump}")

    try:
        result = recognizer.recognize(image_bgr)
    except RecognitionError as exc:
        print(f"识别失败：{exc}", file=sys.stderr)
        return 1

    print("识别布局（上=黑方）：")
    for row in result["layout"]:
        print("  " + row)
    print("每格置信度：")
    for row in result["stats"]["confidences"]:
        print("  " + " ".join(f"{value:.2f}" for value in row))
    print(
        f"棋子 {len(result['pieces'])} 个，"
        f"pose {result['stats']['pose_ms']}ms，"
        f"classify {result['stats']['classify_ms']}ms"
    )
    if result["warnings"]:
        print("警告：" + "；".join(result["warnings"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
