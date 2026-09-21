"""阶段判定与动态子力价值（Task 8）。

Java 参考：
- `AICoreHandler.getPhase` L112-130：中局/残局判定；
- `AICoreHandler.moveBegin` L132-142：兵/卒、马、炮的动态子力价值。

约定与差异：
- Java 的时序是"先用静态子力表算 baseScore、之后 moveBegin 才改动态子力表"，
  导致同一局面的 baseScore 与后续走子增量使用不同的子力值；本项目 `prepare`
  统一为"动态子力 + 当前阶段位置表全量重算 base_score"，属**有意简化**
  （更自洽，增量与全量恒等）。
- 兵/卒的动态值使用**兵所属方自己**的攻击子数：Java moveBegin 中黑卒传
  `BLACKPLAYSIGN`、红兵传 `REDPLAYSIGN`，即 `getAttackChessesNum(己方)`；
  迁移笔记 5.2 写作"对方攻击子数"系笔误，此处以 Java 源码为准。
- `st.piece_scores`/`st.phase` 由 `position.State` 以视图 property 提供
  （分别打包在 `base_score[_PIECE_SCORES_OFFSET:...]`、
  `side_to_move[_PHASE_SLOT]`），此处可直接读写；njit 热路径按索引或
  `position.get_phase` 访问，理由见 `position` 模块 docstring。
"""

import numpy as np
from numba import njit

from . import constants as C
from .position import full_base_score

__all__ = [
    "END_GAME",
    "MIDDLE_GAME",
    "dynamic_piece_scores",
    "phase_of",
    "prepare",
]

# 与 position.State.phase / attach_score 的取值约定一致
MIDDLE_GAME = 0
END_GAME = 1


@njit(cache=True)
def phase_of(st):
    """阶段判定（对应 Java `AICoreHandler.getPhase`）。

    redChessNum = 红车 + 红马 + 红炮 + (红兵 > 3 ? 1 : 0)，黑方同理；
    两者之和 < 7 → END_GAME，否则 MIDDLE_GAME。
    """
    red = 0
    red += int(st.remain[C.RED_CHARIOT])
    red += int(st.remain[C.RED_KNIGHT])
    red += int(st.remain[C.RED_GUN])
    if st.remain[C.RED_SOLDIER] > 3:
        red += 1
    black = 0
    black += int(st.remain[C.BLACK_CHARIOT])
    black += int(st.remain[C.BLACK_KNIGHT])
    black += int(st.remain[C.BLACK_GUN])
    if st.remain[C.BLACK_SOLDIER] > 3:
        black += 1
    if red + black < 7:
        return END_GAME
    return MIDDLE_GAME


@njit(cache=True)
def dynamic_piece_scores(st):
    """动态子力价值（对应 Java `AICoreHandler.moveBegin` L132-142）。

    返回新的 `np.int32[15]`（索引 = 角色 1..14，不修改只读常量表）：

    - 兵/卒 = 100 + (11 - 己方攻击子数) * 8（兵所属方自己的车马炮兵数）；
    - 马 = 490 + (32 - 全场剩余棋子数) * 6（越到残局越升值）；
    - 炮 = 610 - (32 - 全场剩余棋子数) * 6（越到残局越贬值）；
    - 其余角色保持 `constants.PIECE_SCORES`。
    """
    scores = np.copy(C.PIECE_SCORES)
    total = 0
    for role in range(1, 15):
        total += int(st.remain[role])
    left = 32 - total
    scores[C.BLACK_SOLDIER] = np.int32(
        100 + (11 - int(st.attack_def[C.BLACK, 0])) * 8
    )
    scores[C.RED_SOLDIER] = np.int32(
        100 + (11 - int(st.attack_def[C.RED, 0])) * 8
    )
    scores[C.BLACK_KNIGHT] = np.int32(490 + left * 6)
    scores[C.RED_KNIGHT] = np.int32(490 + left * 6)
    scores[C.BLACK_GUN] = np.int32(610 - left * 6)
    scores[C.RED_GUN] = np.int32(610 - left * 6)
    return scores


def prepare(st):
    """搜索前一次性准备：动态子力 → 阶段 → base_score 全量重算。

    顺序：
    1. `st.piece_scores[:] = dynamic_piece_scores(st)`（视图写入）；
    2. `st.phase[0] = phase_of(st)`（视图写入）；
    3. `base_score = full_base_score(st)` 写回（动态子力 + 当前阶段位置表）。

    Java 中 baseScore 先于动态子力表刷新，本项目统一为先写动态表再全量重算
    （有意简化，见模块 docstring）；此后 make/unmake 的增量维护与之恒等。
    """
    st.piece_scores[:] = dynamic_piece_scores(st)
    st.phase[0] = np.int8(phase_of(st))
    red, black = full_base_score(st)
    st.base_score[C.RED] = np.int32(red)
    st.base_score[C.BLACK] = np.int32(black)
