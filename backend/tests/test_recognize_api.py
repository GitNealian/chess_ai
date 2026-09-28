"""`POST /api/recognize` 接口测试（识别器以假实现替换）。"""

import io
import os

import pytest

import routes.recognize as recognize_route
from recognizer import BoardNotFound, ModelNotInstalled, RecognitionError

RESULT = {
    "pieces": [{"x": 0, "y": 9, "side": "black", "kind": "R"}],
    "layout": ["r" + "." * 8] + ["." * 9] * 9,
    "warnings": ["1 个格子识别置信度较低，请核对"],
    "stats": {"pose_ms": 5, "classify_ms": 90, "keypoint_scores": [0.9] * 4},
}


def post_image(client, data=b"fake-image", field="image"):
    payload = {field: (io.BytesIO(data), "board.jpg")} if field else {}
    return client.post("/api/recognize", data=payload, content_type="multipart/form-data")


def test_recognize_returns_result(client, monkeypatch):
    monkeypatch.setattr(recognize_route, "recognize_image", lambda _data: RESULT)
    resp = post_image(client)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["pieces"] == RESULT["pieces"]
    assert body["layout"] == RESULT["layout"]
    assert body["warnings"] == RESULT["warnings"]
    assert body["stats"]["classify_ms"] == 90


def test_recognize_requires_image_field(client):
    resp = post_image(client, field=None)
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "缺少图片文件"


def test_recognize_rejects_empty_image(client):
    resp = post_image(client, data=b"")
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "无法解析图片"


@pytest.mark.parametrize(
    "error,status",
    [
        (BoardNotFound("未检测到棋盘，请让棋盘完整入镜后重试"), 400),
        (RecognitionError("无法解析图片"), 400),
        (ModelNotInstalled("识别模型未安装，请先运行 scripts/download_models.py"), 503),
    ],
)
def test_recognize_maps_errors(client, monkeypatch, error, status):
    def boom(_data):
        raise error

    monkeypatch.setattr(recognize_route, "recognize_image", boom)
    resp = post_image(client)
    assert resp.status_code == status
    assert resp.get_json()["error"] == str(error)


def test_recognize_rejects_oversized_image(client, app, monkeypatch):
    app.config["MAX_CONTENT_LENGTH"] = 64
    resp = post_image(client, data=b"x" * 1024)
    assert resp.status_code == 413
    assert resp.get_json()["error"] == "图片过大，请压缩后重试"


def test_recognize_with_real_model():
    """真实模型集成测试：需模型已下载且设置 RECOGNIZE_TEST_IMAGE。"""
    image_path = os.environ.get("RECOGNIZE_TEST_IMAGE")
    if not image_path or not os.path.isfile(image_path):
        pytest.skip("未设置 RECOGNIZE_TEST_IMAGE 环境变量")
    pytest.importorskip("onnxruntime")

    from recognizer import model_files, recognize_image

    if not all(os.path.isfile(path) for path in model_files()):
        pytest.skip("识别模型未安装")

    with open(image_path, "rb") as handle:
        result = recognize_image(handle.read())
    assert len(result["pieces"]) >= 2
    assert len(result["layout"]) == 10
    assert all(len(row) == 9 for row in result["layout"])
