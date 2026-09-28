#!/usr/bin/env python3
"""下载棋盘识别 ONNX 模型到 backend/weights/。

模型来源：开源项目 TheOne1006/chinese-chess-recognition 的 ONNX 导出，
托管于 HuggingFace Space `yolo12138/Chinese_Chess_Recognition`：

- pose.onnx   棋盘四角关键点检测（约 10.7MB）
- layout.onnx 棋盘布局分类 10x9x16（约 31.1MB）

用法：
    python scripts/download_models.py
    python scripts/download_models.py --force        # 强制重新下载
    python scripts/download_models.py --dir /path    # 自定义目录
"""

import argparse
import os
import urllib.request

BASE_URL = (
    "https://huggingface.co/spaces/yolo12138/Chinese_Chess_Recognition/resolve/main/onnx"
)
FILES = {
    "pose.onnx": f"{BASE_URL}/pose/4_v6-0301.onnx",
    "layout.onnx": f"{BASE_URL}/layout_recognition/nano_v3-0319.onnx",
}
DEFAULT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "weights"
)
USER_AGENT = "chess-board-scan/1.0"


def download(url, dest, force=False):
    if os.path.isfile(dest) and not force:
        print(f"已存在，跳过：{dest}")
        return
    print(f"下载 {url}")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    tmp = dest + ".part"
    with urllib.request.urlopen(request, timeout=180) as response, open(tmp, "wb") as out:
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = response.read(1 << 20)
            if not chunk:
                break
            out.write(chunk)
            done += len(chunk)
            if total:
                percent = done * 100 // total
                print(
                    f"\r  {percent:>3}% ({done // (1 << 20)}MB/{total // (1 << 20)}MB)",
                    end="",
                    flush=True,
                )
            else:
                print(f"\r  {done // (1 << 20)}MB", end="", flush=True)
    print()
    os.replace(tmp, dest)


def main():
    parser = argparse.ArgumentParser(description="下载棋盘识别模型")
    parser.add_argument("--dir", default=DEFAULT_DIR, help="模型保存目录")
    parser.add_argument("--force", action="store_true", help="已存在时重新下载")
    args = parser.parse_args()

    os.makedirs(args.dir, exist_ok=True)
    for name, url in FILES.items():
        download(url, os.path.join(args.dir, name), args.force)
    print(f"完成，模型目录：{args.dir}")


if __name__ == "__main__":
    main()
