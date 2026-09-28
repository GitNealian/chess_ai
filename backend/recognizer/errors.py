"""识别相关异常。"""


class RecognitionError(Exception):
    """识别失败（图片无法解析、结果异常等）。"""


class BoardNotFound(RecognitionError):
    """未能在图片中定位棋盘。"""


class ModelNotInstalled(RecognitionError):
    """识别模型文件缺失。"""
