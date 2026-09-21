"""中国象棋 AI 引擎包。

对外只暴露轻量名称；`AnalysisResult`/`analyze`/`warmup` 通过 PEP 562
`__getattr__` 延迟导入 `engine.analysis`。这样 `from engine import constants`
等子模块导入不会连带触发 `analysis → search → numba` 全链的 JIT 编译准备。
"""

ENGINE_VERSION = "1.0.0"

__all__ = ["ENGINE_VERSION", "AnalysisResult", "analyze", "warmup"]

_LAZY_EXPORTS = frozenset(("AnalysisResult", "analyze", "warmup"))


def __getattr__(name):
    if name in _LAZY_EXPORTS:
        from . import analysis

        return getattr(analysis, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return sorted(__all__)
