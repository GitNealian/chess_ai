"""棋盘识别接口：`POST /api/recognize`。

请求为 `multipart/form-data`，字段 `image` 为棋盘照片/截图；成功返回
`{pieces, layout, warnings, stats}`，失败返回中文错误：

- 400：缺少图片、无法解析图片、未检测到棋盘；
- 413：图片过大（`MAX_CONTENT_LENGTH`）；
- 503：识别模型未安装。
"""

from flask import Blueprint, jsonify, request

from recognizer import (
    BoardNotFound,
    ModelNotInstalled,
    RecognitionError,
    recognize_image,
)

recognize_bp = Blueprint("recognize", __name__)


@recognize_bp.post("")
def recognize_board():
    upload = request.files.get("image")
    if upload is None:
        return jsonify({"error": "缺少图片文件"}), 400
    data = upload.read()
    if not data:
        return jsonify({"error": "无法解析图片"}), 400
    try:
        return jsonify(recognize_image(data))
    except ModelNotInstalled as exc:
        return jsonify({"error": str(exc)}), 503
    except BoardNotFound as exc:
        return jsonify({"error": str(exc)}), 400
    except RecognitionError as exc:
        return jsonify({"error": str(exc)}), 400
