"""Zobrist 哈希（32/64 位表与全量重算）。

Java 参考：
- `TranspositionTable.genStaticZobrist32And64OfBoard`（L93-102）；
- 原始表 `InitZobristList32And64.java` 是 90×15 的纯随机常量（无生成逻辑），
  本迁移用固定种子自行生成——键只需引擎内部自洽，碰撞模式与原版不同。

约定：
- 第一维 site（0-89），第二维角色（1-14，0 列保留恒 0）；
- 无走棋方键、无特殊规则键（与 Java 一致）；红黑同一角色值不同（红 1-7、
  黑 8-14），天然区分颜色；
- ZOB32 取低 31 位正数（对应 Java int），ZOB64 取 int63 正数（对应 Java
  long 的正值区间），两者均 XOR 封闭；
- 表导入即构建且只读。
"""

import numpy as np
from numba import njit

from .constants import PIECE_ROLES

__all__ = ["SEED", "ZOB32", "ZOB64", "full_zobrist"]

SEED = 0xC0FFEE

_rng = np.random.default_rng(SEED)
ZOB32 = _rng.integers(0, 1 << 31, size=(90, 15), dtype=np.int64)
ZOB64 = _rng.integers(0, 1 << 63, size=(90, 15), dtype=np.int64)
ZOB32[:, 0] = 0
ZOB64[:, 0] = 0
ZOB32.setflags(write=False)
ZOB64.setflags(write=False)


@njit(cache=True)
def full_zobrist(board):
    """遍历 board（site→棋子索引，空=0）非空格 XOR 两张表，返回 (zob32, zob64)。"""
    z32 = np.int64(0)
    z64 = np.int64(0)
    for site in range(90):
        piece = board[site]
        if piece != 0:
            role = PIECE_ROLES[piece]
            z32 ^= ZOB32[site, role]
            z64 ^= ZOB64[site, role]
    return z32, z64
