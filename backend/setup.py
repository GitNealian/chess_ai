"""Cython 扩展构建（MVP 探针）。

用法：.venv/bin/python setup.py build_ext --inplace
"""
import numpy as np
from setuptools import Extension, setup

from Cython.Build import cythonize

extensions = [
    Extension(
        "engine._cycore",
        ["engine/_cycore.pyx"],
        include_dirs=[np.get_include()],
        extra_compile_args=["-O3", "-fno-math-errno"],
    )
]

setup(
    name="engine-cycore",
    ext_modules=cythonize(extensions, language_level=3, quiet=True),
)
