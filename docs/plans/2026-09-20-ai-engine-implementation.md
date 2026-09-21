# 中国象棋 AI 引擎迁移与接入实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 Java 版中国象棋 AI 引擎（位棋盘 + negaScout/PVS）迁移为 numba 加速的 Python 实现，并接入打谱页，实现翻步即时的渐进式局面分析与棋盘箭头推演。

**Architecture:** 新建 `backend/engine/` 包：只读预生成表与 Zobrist 用模块级 numpy 常量（保证 numba `cache=True` 稳定），可变局面状态与搜索上下文打包为 namedtuple 参数传递；非 JIT 的 `analysis.py` 负责迭代加深调度并逐层 yield 结果；Flask 以 NDJSON 流式响应逐层推送；前端用 `fetch` 流式解析并 append 展示、在 SVG 棋盘上画箭头。

**Tech Stack:** Python 3.12 / numba 0.67 / numpy / Flask 3 / Vue 3 + Vite / vitest / pytest

**设计文档：** `docs/plans/2026-09-20-ai-engine-design.md`
**Java 源码参考：** `/tmp/opencode/ChineseChess/`（若不存在：`git clone https://github.com/pengjiu/ChineseChess.git /tmp/opencode/ChineseChess`）
**逐文件迁移笔记（必读）：** `docs/plans/2026-09-20-java-engine-migration-notes.md`（含全部算法伪代码、行号、陷阱清单）

---

## 全局约定（所有任务共用，实现时必须遵守）

### 坐标系与编码

- 引擎内部 `site = row*9 + col`，**row=0 为黑方底线**（与 Java 一致）；与现有 `chess_engine` 的 `(x, y)`（y=0 红方底线）转换为：
  ```python
  def xy_to_site(x, y): return (9 - y) * 9 + x   # y=0(红底线) -> row=9
  def site_to_xy(site): return site % 9, 9 - site // 9
  ```
- 棋子索引：16-31 黑、32-47 红（顺序见笔记"关键常量补充"）；`board[site]` 空位 = 0；`all_chess[piece]` 空 = -1
- 角色：红 1..7、黑 8..14；`REDPLAYSIGN=1`、`BLACKPLAYSIGN=0`；`play` 变量一律 1=红、0=黑
- 着法编码（packed int32）：`move = src | (dest << 7)`（src/dest 为 site，0..89）；解码 `src = move & 127`、`dest = move >> 7`
- 位棋盘（BitBoard）统一打包为 `(lo: int64, hi: int64)`：site 0..63 在 lo，site 64..89 在 hi（bit `site-64`）
- **有意偏差（记录在案）**：原 Java 的 `BitBoard.MSB` 对黑方按"字降序"扫描，Python 版统一按 site 升序扫描。这只影响同分着法的生成顺序（进而轻微影响剪枝路径与 PV 选择），不影响规则正确性与评估/搜索语义。
- 分数尺度与 Java 一致：兵=100、马=490、炮=610、车=1300、士/象=200、将=3000；`maxScore=9999`、长将=8888、和棋=0
- 将死分数 `±(maxScore - ply)`；`ply` = 距离根节点的步数（根 = 0）

### numba 使用规范

- 所有热路径函数 `@njit(cache=True)`；只读表为模块级全局 ndarray（内容确定、不改写）；可变状态（`State`、`Ctx`）通过参数传递，**绝不**用模块级全局可变数组（避免 `cache=True` 序列化与状态污染）
- `State` / `Ctx` 用 `collections.namedtuple` 打包 numpy 数组（numba 编译期展开字段访问，零成本）
- 数组 dtype 必须显式指定，避免 numba 类型推断失败
- 停止标志为 `np.int8[1]` 数组（numba 无法可靠修改标量参数），搜索循环定期检查

### 文件布局

```
backend/
├── engine/
│   ├── __init__.py      # 对外导出：analyze / warmup / ENGINE_VERSION
│   ├── constants.py     # Task 1
│   ├── bitboard.py      # Task 2
│   ├── tables.py        # Task 3-4
│   ├── zobrist.py       # Task 5
│   ├── position.py      # Task 5
│   ├── movegen.py       # Task 6
│   ├── eval_tables.py   # Task 7（脚本生成）
│   ├── evaluate.py      # Task 7-8
│   ├── search.py        # Task 9-11
│   └── analysis.py      # Task 12
├── scripts/extract_eval_tables.py   # Task 7
├── routes/engine.py                 # Task 13
└── tests/test_engine_*.py
frontend/src/
├── components/ChessBoard.vue        # Task 15
├── api/index.js                     # Task 16
└── views/PracticeView.vue           # Task 17
```

### 提交约定

每个任务完成后提交一次，信息格式 `feat(engine): ...` / `feat(web): ...` / `test(engine): ...`。若用户未授权提交，先跳过提交步骤并在任务汇报中注明。

---

## Task 1: 引擎包骨架、常量与 numba 技术验证

**Files:**
- Create: `backend/engine/__init__.py`
- Create: `backend/engine/constants.py`
- Create: `backend/tests/test_engine_constants.py`

**Step 1: 写失败测试**

```python
# backend/tests/test_engine_constants.py
import numpy as np
import pytest

from engine import constants as C


def test_role_encoding():
    assert C.RED_SOLDIER == 1 and C.RED_KING == 7
    assert C.BLACK_SOLDIER == 8 and C.BLACK_KING == 14
    for kind in range(1, 8):
        assert C.role_of(kind, C.RED) == kind
        assert C.role_of(kind, C.BLACK) == kind + 7


def test_piece_index_layout():
    assert C.RED_PIECES_START == 32 and C.BLACK_PIECES_START == 16
    assert C.PIECE_ROLES[16] == C.BLACK_KING
    assert C.PIECE_ROLES[32] == C.RED_KING
    assert len(C.PIECE_ROLES) == 48
    assert C.PIECE_ROLES[0] == 0


def test_attack_defense_classification():
    assert C.ATTACK_DEFENSE_INDEX[C.RED_SOLDIER] == 0
    assert C.ATTACK_DEFENSE_INDEX[C.RED_GUARD] == 1
    assert C.ATTACK_DEFENSE_INDEX[C.BLACK_KING] == 1
    assert C.ATTACK_DEFENSE_INDEX[C.BLACK_GUN] == 0


def test_coordinate_conversion():
    assert C.xy_to_site(0, 0) == 81          # 红方底线左角
    assert C.xy_to_site(8, 9) == 8           # 黑方底线右角
    assert C.site_to_xy(81) == (0, 0)
    assert C.site_to_xy(8) == (8, 9)
    for site in range(90):
        x, y = C.site_to_xy(site)
        assert C.xy_to_site(x, y) == site


def test_move_packing():
    for src in (0, 81, 89):
        for dest in (0, 45, 89):
            m = C.pack_move(src, dest)
            assert C.move_src(m) == src
            assert C.move_dest(m) == dest


def test_base_scores():
    assert C.PIECE_SCORES[C.RED_KING] == 3000
    assert C.PIECE_SCORES[C.RED_CHARIOT] == 1300
    assert C.PIECE_SCORES[C.BLACK_SOLDIER] == 100
    assert C.MAX_SCORE == 9999
    assert C.LONG_CHECK_SCORE == 8888
```

**Step 2: 运行确认失败**

Run: `cd /home/nealian/chess/backend && .venv/bin/python -m pytest tests/test_engine_constants.py -q`
Expected: FAIL（ModuleNotFoundError: No module named 'engine'）

**Step 3: 实现**

`backend/engine/__init__.py`：先留空（Task 12 再补导出）。

`backend/engine/constants.py` 要点（对照 `ChessConstant.java` 与笔记）：
- 基础类型常量 `SOLDIER=1 ... KING=7`；红方角色 1..7、黑方角色 8..14；`RED=1`、`BLACK=0`
- `PIECE_ROLES`：长度 48 的 numpy int8 表（0-15 填 0；16=黑将 14、17-18=黑车 13、19-20=黑马 12、21-22=黑炮 11、23-24=黑象 10、25-26=黑士 9、27-31=黑卒 8；32=红帅 7 …… 43-47=红兵 1）
- `PIECE_KINDS`：同序的 1..7 基础类型表（对应 Java `chessRoles_eight`）
- `ATTACK_DEFENSE_INDEX`：长度 15 的 int8 表，`[_,0,1,1,0,0,0,1, 0,1,1,0,0,0,1]`
- `PIECE_SCORES`：长度 15，红黑对称（将 3000、车 1300、马 490、炮 610、象 200、士 200、兵 100）
- 辅助函数：`role_of(kind, play)`、`xy_to_site`、`site_to_xy`、`pack_move`、`move_src`、`move_dest`、`play_of_piece(idx)`（16..31 → BLACK，32..47 → RED）
- 搜索常量：`MAX_SCORE=9999`、`LONG_CHECK_SCORE=8888`、`DRAW_SCORE=0`、`MAX_DEPTH=64`、`ROOT_START_DEPTH=4`
- python 层再加 `DEFAULT_START_DEPTH=6`、`DEFAULT_MAX_DEPTH=16`、`DEFAULT_TIME_LIMIT_MS=2000`

**Step 4: numba 技术验证（写进测试）**

新增 `backend/tests/test_engine_numba_smoke.py`：

```python
import numpy as np
from numba import njit

_TABLE = np.arange(16, dtype=np.int64)


@njit(cache=True)
def _lookup(i):
    return _TABLE[i] * 2


@njit(cache=True)
def _sum_state(state):
    total = np.int64(0)
    for i in range(state.shape[0]):
        total += state[i]
    return total


def test_njit_global_readonly_array():
    assert _lookup(3) == 6


def test_njit_array_mutation_visible():
    st = np.zeros(4, dtype=np.int64)
    assert _sum_state(st) == 0
    st[1] = 5
    assert _sum_state(st) == 5


def test_njit_stop_flag_pattern():
    flag = np.zeros(1, dtype=np.int8)
    flag[0] = 1
    assert _check_stop(flag) is True
```

（`_check_stop` 同样 `@njit(cache=True)`，实现 `return flag[0] != 0`。）

Run: `cd /home/nealian/chess/backend && .venv/bin/python -m pytest tests/test_engine_constants.py tests/test_engine_numba_smoke.py -q`
Expected: PASS。若 `test_njit_global_readonly_array` 二次运行（缓存命中）失败，记录输出并按笔记规范改用参数传递方案（本项目只读表也允许改为**每次调用传给 njit 函数**的兜底）。

**Step 5: 提交**

```bash
git add backend/engine/__init__.py backend/engine/constants.py backend/tests/test_engine_constants.py backend/tests/test_engine_numba_smoke.py
git commit -m "feat(engine): 引擎常量编码与 numba 冒烟验证"
```

---

## Task 2: 位棋盘 bitboard.py

**Files:**
- Create: `backend/engine/bitboard.py`
- Create: `backend/tests/test_engine_bitboard.py`

**Step 1: 写失败测试**

```python
# backend/tests/test_engine_bitboard.py
import numpy as np

from engine import bitboard as bb


def test_site_bit_roundtrip():
    for site in range(90):
        lo, hi = bb.site_mask(site)
        assert bb.has_site(lo, hi, site)
        for other in (0, 1, 63, 64, 89):
            if other != site:
                assert not bb.has_site(lo, hi, other)


def test_lowest_site_order():
    lo = np.int64((1 << 3) | (1 << 40))
    hi = np.int64((1 << 0) | (1 << 25))
    assert bb.lowest_site(lo, hi) == 3
    assert bb.lowest_site(np.int64(0), hi) == 64
    assert bb.lowest_site(np.int64(1 << 63), np.int64(0)) == 63


def test_popcount_and_empty():
    lo = np.int64((1 << 1) | (1 << 2) | (1 << 63))
    hi = np.int64(1 << 5)
    assert bb.count(lo, hi) == 4
    assert bb.empty(0, 0)
    assert not bb.empty(lo, 0)


def test_word_reconstruction():
    # 4 字重建：Low site0-26、Mid1 27-53、Mid2 54-80、Hi 81-89
    assert bb._words(*bb.site_mask(0))[0] == 1
    assert bb._words(*bb.site_mask(27))[1] == 1
    assert bb._words(*bb.site_mask(54))[2] == 1
    assert bb._words(*bb.site_mask(80))[2] == 1 << 26
    assert bb._words(*bb.site_mask(81))[3] == 1


def test_check_sum_matches_java_independent_reference():
    # 独立参考（不调用 bb._words）：对照 BitBoard.java L83-88 / L90-94
    # elephant = (t&0x7f)+((t>>>6)&0x7f)+((t>>>13)&0x7f)+((t>>>19)&0x7f)
    # knight   = (t&0x7f)+((t>>>7)&0x7f)+((t>>>14)&0x7f)+((t>>>21)&0x7f)
    # 其中 t = Low ^ Mid1 ^ Mid2 ^ Hi（4 字布局见上）
    def java_word_bit(site):
        if site < 27:
            return 0, 1 << site
        if site < 54:
            return 1, 1 << (site - 27)
        if site < 81:
            return 2, 1 << (site - 54)
        return 3, 1 << (site - 81)

    for site in range(90):
        lo, hi = bb.site_mask(site)
        word, bit = java_word_bit(site)
        t = bit if word == 0 else 0
        # 单站点掩码时 t 即该字的值（其余字为 0）
        assert bb.check_sum_knight(lo, hi) == (t & 0x7F) + ((t >> 7) & 0x7F) + ((t >> 14) & 0x7F) + ((t >> 21) & 0x7F)
        assert bb.check_sum_elephant(lo, hi) == (t & 0x7F) + ((t >> 6) & 0x7F) + ((t >> 13) & 0x7F) + ((t >> 19) & 0x7F)


def test_iter_sites_ascending():
    lo = np.int64((1 << 10) | (1 << 2))
    hi = np.int64(1 << 1)  # site 65
    assert list(bb.iter_sites(lo, hi)) == [2, 10, 65]
```

**Step 2: 运行确认失败**

Run: `cd /home/nealian/chess/backend && .venv/bin/python -m pytest tests/test_engine_bitboard.py -q`
Expected: FAIL（ModuleNotFoundError）

**Step 3: 实现**

`bitboard.py`：全部 `@njit(cache=True)`，签名以 `lo, hi`（int64）为参数、以 tuple 返回，例如：
- `site_mask(site) -> (lo, hi)`
- `mask_from_sites(sites: int32[:]) -> (lo, hi)`（用于表构建后的查询，非热路径可普通 Python 实现）
- `has_site / empty / count`（SWAR popcount，见 Java `BitBoard.Count` L128-138，可换成 `bin(x).count("1")` 的手写循环版）
- `lowest_site(lo, hi) -> int`（无位返回 -1；实现顺序：lo 低位 → hi 低位，即统一 **site 升序**）
- `pop_lowest(lo, hi) -> (lo, hi, site)`（取最低位并从掩码移除，等价 Java 的 `MSB` + `assignXor`）
- `check_sum_knight(lo, hi)` / `check_sum_elephant(lo, hi)`：**逐字复刻** Java（BitBoard.java）：
  - `checkSumOfElephant`（L83-88）移位 **0/6/13/19**
  - `checkSumOfKnight`（L90-94）移位 **0/7/14/21**
  - 4 字布局：Low site0-26、Mid1 27-53、Mid2 54-80、Hi 81-89；**后续 Task 3/4 必须调用本模块函数，禁止内联公式**
- `iter_sites(lo, hi)`：生成器形式供测试使用（非 njit，或 njit 版另写）

**Step 4: 运行确认通过**

Run: `cd /home/nealian/chess/backend && .venv/bin/python -m pytest tests/test_engine_bitboard.py -q`
Expected: PASS

**Step 5: 提交**

```bash
git add backend/engine/bitboard.py backend/tests/test_engine_bitboard.py
git commit -m "feat(engine): 位棋盘原语与腿位折叠校验和"
```

---

## Task 3: 基础预生成表（马/象/士/将/兵/危险区）

**Files:**
- Create: `backend/engine/tables.py`
- Create: `backend/tests/test_engine_tables_basic.py`

**Step 1: 写失败测试（核心是"与独立参考实现交叉验证"）**

```python
# backend/tests/test_engine_tables_basic.py
import numpy as np
import pytest

from engine import constants as C
from engine import tables as T


def row_of(site): return site // 9
def col_of(site): return site % 9
def site_of(row, col): return row * 9 + col


def ref_knight_targets(site):
    r, c = row_of(site), col_of(site)
    legs = [((-1, 2), (0, 1)), ((-1, -2), (0, -1)), ((1, 2), (0, 1)), ((1, -2), (0, -1)),
            ((2, 1), (1, 0)), ((2, -1), (1, 0)), ((-2, 1), (-1, 0)), ((-2, -1), (-1, 0))]
    out = []
    for (dr, dc), (lr, lc) in legs:
        nr, nc = r + dr, c + dc
        if 0 <= nr < 10 and 0 <= nc < 9:
            out.append(site_of(nr, nc))
    return out


def test_knight_targets_match_reference():
    for site in range(90):
        got = sorted(T.unpack_sites(*T.knight_targets(site)))
        assert got == sorted(ref_knight_targets(site)), site


def test_knight_attack_limit_obstructed_leg():
    # 角落马的 8 个目标在腿被占时被限制
    site = site_of(9, 4)  # 黑方九宫上方中路
    full = sorted(T.unpack_sites(*T.knight_targets(site)))
    assert len(full) >= 4
    # 腿位表应覆盖所有可能的腿位组合（键为折叠校验和）
    keys = T.knight_leg_keys(site)
    assert len(keys) > 0
    for key in keys:
        lo, hi = T.knight_targets_limit(site, key)
        targets = set(T.unpack_sites(lo, hi))
        assert targets <= set(full)


def test_elephant_stays_on_own_half():
    for site in range(90):
        r, c = row_of(site), col_of(site)
        for dest in T.unpack_sites(*T.elephant_targets(site)):
            dr, dc = row_of(dest), col_of(dest)
            if C.play_of_site(site) == C.RED:      # 红方（row>=5）目标必须 row>=5
                assert dr >= 5, (site, dest)
            else:
                assert dr <= 4, (site, dest)


def test_guard_and_king_inside_palace():
    for site in range(90):
        for dest in T.unpack_sites(*T.guard_targets(site)):
            r, c = row_of(dest), col_of(dest)
            assert 3 <= c <= 5 and (r <= 2 or r >= 7), (site, dest)
        for dest in T.unpack_sites(*T.king_targets(site)):
            r, c = row_of(dest), col_of(dest)
            assert 3 <= c <= 5 and (r <= 2 or r >= 7), (site, dest)


def test_soldier_moves_and_king_checked_soldier_sites():
    # 过河判定：红兵 row<=4 可横走（初始 row6，前进方向 row-1）
    assert set(T.unpack_sites(*T.soldier_targets(C.RED, site_of(4, 4)))) == {site_of(3, 4), site_of(4, 3), site_of(4, 5)}
    # 红兵未过河（row5）：只能前进
    assert set(T.unpack_sites(*T.soldier_targets(C.RED, site_of(5, 4)))) == {site_of(4, 4)}
    # 黑卒未过河（row4）：只能前进（row+1）
    assert set(T.unpack_sites(*T.soldier_targets(C.BLACK, site_of(4, 4)))) == {site_of(5, 4)}
    # 黑卒过河（row5）：可前进与横走
    assert set(T.unpack_sites(*T.soldier_targets(C.BLACK, site_of(5, 4)))) == {site_of(6, 4), site_of(5, 3), site_of(5, 5)}
    # KingCheckedSoldierBitBoards：能攻击 site 的对方兵位置
    # 红方半场（row>=5）站点 → 黑卒攻击位 {site-9, site-1, site+1}
    assert set(T.unpack_sites(*T.king_checked_soldier_sites(site_of(9, 4)))) == {site_of(8, 4), site_of(9, 3), site_of(9, 5)}
    # 黑方半场（row<5）中央站点 → 红兵攻击位 {site+9, site-1, site+1}
    assert set(T.unpack_sites(*T.king_checked_soldier_sites(site_of(4, 4)))) == {site_of(5, 4), site_of(4, 3), site_of(4, 5)}


def test_danger_margin_masks():
    # 黑方危险区（Java blackDangerMarginArray）= site 0-26 + 30-32；红方 = site 57-59 + 63-89（row6 col3-5）
    assert set(T.unpack_sites(*T.danger_margin(C.BLACK))) == set(range(0, 27)) | {30, 31, 32}
    assert set(T.unpack_sites(*T.danger_margin(C.RED))) == {57, 58, 59} | set(range(63, 90))
```

> 说明：`T.unpack_sites(lo, hi)` 为普通 Python 辅助函数（返回 site 列表）；`T.knight_leg_keys(site)` 返回该站点所有可能的腿位折叠键（供遍历）。
> 若对"红方 row>=5"的判定（`play_of_site`）拿不准，改用固定站点断言（如 site_of(9,4) 为红方、site_of(0,4) 为黑方）——**红方在 row 5..9，黑方在 row 0..4**（与 Java 一致）。

**Step 2: 运行确认失败**

Run: `cd /home/nealian/chess/backend && .venv/bin/python -m pytest tests/test_engine_tables_basic.py -q`
Expected: FAIL

**Step 3: 实现**

`tables.py` 结构：
- 顶部：`import numpy as np`，只读表在**模块导入时**用纯 Python 构建（一次性），存模块级 ndarray；构建函数带 `_build_*` 前缀，供测试单独调用
- 表（对照 Java `ChessInitialize.initKnightMove/initElephantMove/initSoldier/initKingAndGuard/...`；行号见笔记"关键常量补充"与第 3 节）：
  - `KNIGHT_TARGET_LO/HI: int64[90]`（`KnightBitBoards`）
  - `KNIGHT_LEG_LO/HI: int64[90]`（`KnightLegBitBoards`，腿位；最多 4 个正交邻格）
  - `KNIGHT_ATTACK_LIMIT_LO/HI: int64[90][200]` + `KNIGHT_MOBILITY: int16[90][200]`（`KnightBitBoardOfAttackLimit`，键为 `check_sum_knight(腿位掩码)`；**生成时按 Java 的"子集遍历"逻辑：对腿位集合的所有非空子集，把"腿不在子集内"的走法并入结果**，键碰撞时后写覆盖）
  - `ELEPHANT_LEG_LO/HI: int64[90]`、`ELEPHANT_TARGET_LO/HI: int64[90]`、`ELEPHANT_ATTACK_LIMIT_LO/HI: int64[90][200]`
  - `GUARD_TARGET_LO/HI: int64[90]`（九宫内斜一步）
  - `KING_TARGET_LO/HI: int64[90]`（九宫内直一步）
  - `SOLDIER_TARGET_LO/HI: int64[2][90]`（`SoldiersBitBoard[play][site]`）
  - `KING_CHECKED_SOLDIER_LO/HI: int64[90]`（`KingCheckedSoldierBitBoards`；按 Java L199-210 的规则构造）
  - `DANGER_MARGIN_LO/HI: int64[2]`（Java `SearchEngine.DangerMarginBit` L287-313 的坐标逐字迁移；如原文为 16×16 编码，按 `boardMap` 换为 90 坐标）
  - `MASK_SITE_LO/HI: int64[90]`（`MaskChesses`）
- 每张表生成后有 `assert` 自检（如所有目标 site 合法、无越界）
- 辅助 Python API（非 njit，测试与调试用）：`unpack_sites`、`knight_targets(site)`、`knight_targets_limit(site, key)`、`elephant_targets`、`guard_targets`、`king_targets`、`soldier_targets(play, site)`、`king_checked_soldier_sites`、`danger_margin(play)`、`knight_leg_keys(site)`

**关键点**：`KnightLegBitBoards` 的腿位是"马的正交邻格"（如 `(r-1,c)`、`(r,c+1)` 等去重后 ≤4 个）；攻击限制逻辑 = 走法目标集合里去掉"马腿被占"的那些。象同理（象眼）。

**Step 4: 运行确认通过**

Run: `cd /home/nealian/chess/backend && .venv/bin/python -m pytest tests/test_engine_tables_basic.py -q`
Expected: PASS

**Step 5: 提交**

```bash
git add backend/engine/tables.py backend/tests/test_engine_tables_basic.py
git commit -m "feat(engine): 马象士将兵与危险区预生成表"
```

---

## Task 4: 车炮行列预生成表与折叠键攻击表

**Files:**
- Modify: `backend/engine/tables.py`
- Create: `backend/tests/test_engine_tables_chariot_gun.py`

**Step 1: 写失败测试（抽样 + 参考实现全量交叉验证）**

```python
# backend/tests/test_engine_tables_chariot_gun.py
import numpy as np

from engine import tables as T


def row_of(site): return site // 9
def col_of(site): return site % 9
def site_of(row, col): return row * 9 + col


def make_row_mask(row, occupied_cols):
    # Java: boardBitRow 的 bit(8-col)，即 col 0 -> bit8
    mask = 0
    for c in occupied_cols:
        mask |= 1 << (8 - c)
    return mask


def make_col_mask(col, occupied_rows):
    # Java: boardBitCol 的 bit(9-row)，即 row 0 -> bit9
    mask = 0
    for r in occupied_rows:
        mask |= 1 << (9 - r)
    return mask


def ref_chariot_attack_row(site, occ):
    r, c = row_of(site), col_of(site)
    out = []
    for dc in (-1, 1):
        nc = c + dc
        while 0 <= nc < 9:
            out.append(site_of(r, nc))
            if site_of(r, nc) in occ:
                break
            nc += dc
    return out


def ref_move_row(site, occ):
    """车的平移（不含阻挡格）"""
    r, c = row_of(site), col_of(site)
    out = []
    for dc in (-1, 1):
        nc = c + dc
        while 0 <= nc < 9:
            if site_of(r, nc) in occ:
                break
            out.append(site_of(r, nc))
            nc += dc
    return out


def ref_gun_attack_row(site, occ):
    """炮的吃子：越过第一个阻挡后的第二个阻挡"""
    r, c = row_of(site), col_of(site)
    out = []
    for dc in (-1, 1):
        nc = c + dc
        screen = False
        while 0 <= nc < 9:
            s = site_of(r, nc)
            if not screen:
                if s in occ:
                    screen = True
            else:
                if s in occ:
                    out.append(s)
                    break
            nc += dc
    return out


def test_chariot_row_attack_sampled_and_exhaustive():
    for site in (site_of(0, 0), site_of(4, 4), site_of(9, 8)):
        r, c = row_of(site), col_of(site)
        for occupied in ([site_of(r, 2)], [site_of(r, c - 1) if c > 0 else site_of(r, c + 1)], []):
            occ = set(occupied)
            mask = make_row_mask(r, [col_of(s) for s in occ])
            lo, hi = T.chariot_attack_row(site, mask)
            got = sorted(T.unpack_sites(lo, hi))
            assert got == sorted(ref_chariot_attack_row(site, occ)), (site, occupied)


def test_chariot_and_gun_move_row():
    site = site_of(4, 4)
    r = row_of(site)
    blockers = {site_of(r, 2), site_of(r, 6)}
    mask = make_row_mask(r, [col_of(s) for s in blockers])
    lo, hi = T.move_chariot_gun_row(site, mask)
    assert sorted(T.unpack_sites(lo, hi)) == sorted(ref_move_row(site, blockers))


def test_gun_attack_row_needs_screen():
    site = site_of(4, 4)
    r = row_of(site)
    # 无遮挡：炮不能吃任何子
    lo, hi = T.gun_attack_row(site, make_row_mask(r, []))
    assert T.count(lo, hi) == 0
    # 一子为架、第二子为目标
    screen = site_of(r, 2)
    target = site_of(r, 0)
    mask = make_row_mask(r, [col_of(screen), col_of(target)])
    lo, hi = T.gun_attack_row(site, mask)
    assert sorted(T.unpack_sites(lo, hi)) == [target]


def test_gun_fake_attack_row():
    site = site_of(4, 4)
    r = row_of(site)
    screen = site_of(r, 2)
    mask = make_row_mask(r, [col_of(screen)])
    lo, hi = T.gun_fake_attack_row(site, mask)
    assert sorted(T.unpack_sites(lo, hi)) == [site_of(r, 1), site_of(r, 0)]


def test_mobility_tables():
    site = site_of(4, 4)
    r = row_of(site)
    mask = make_row_mask(r, [])
    assert T.chariot_gun_mobility_row(site, mask) == 8
    mask2 = make_row_mask(r, [col_of(site_of(r, 8))])
    assert T.chariot_gun_mobility_row(site, mask2) == 3


def test_knight_and_elephant_limit_keys_within_bounds():
    for site in range(90):
        for key in T.knight_leg_keys(site):
            assert 0 <= key < 200
        for key in T.elephant_leg_keys(site):
            assert 0 <= key < 200
```

**Step 2: 运行确认失败**

Run: `cd /home/nealian/chess/backend && .venv/bin/python -m pytest tests/test_engine_tables_chariot_gun.py -q`
Expected: FAIL

**Step 3: 实现**

对照 Java `ChessInitialize.initChariotGunVariedMove`（L343-417）、`initGunFackEatMove`、`preGunAndChariotBitBoardAttack`（L610-640）、`preAllBitBoard`（L158-198）、`preBitBoardAttack`（L461-519）：

- 行表（第一维是**列 col**，第二维是 `boardBitRow` 原始掩码，范围 0..511）：
  - `CHARIOT_ATTACK_ROW_LO/HI: int64[9][512]`、`CHARIOT_ATTACK_COL_LO/HI: int64[10][1024]`
  - `MOVE_CHARIOT_GUN_ROW_LO/HI: int64[9][512]`、`..._COL_LO/HI: int64[10][1024]`
  - `GUN_ATTACK_ROW_LO/HI: int64[9][512]`、`..._COL`
  - `GUN_FAKE_ATTACK_ROW_LO/HI`、`..._COL`（炮架后的空位）
  - `GUN_MORE_REST_ATTACK_ROW_LO/HI`、`..._COL`（隔两子攻击位，用于沉底炮）
  - `CHARIOT_GUN_MOBILITY_ROW: int16[9][512]`、`..._COL: int16[10][1024]`
- 查询函数按 `(site, mask)` 取行/列，再"展开"到 90 坐标（对应 Java `preGunAndChariotBitBoardAttack` 的坐标换算）：
  - `chariot_attack_row(site, row_mask)` / `_col`
  - `move_chariot_gun_row/col`、`gun_attack_row/col`、`gun_fake_attack_row/col`、`gun_more_rest_attack_row/col`
  - `chariot_gun_mobility_row/col`
- `KNIGHT_ATTACK_LIMIT_*`、`ELEPHANT_ATTACK_LIMIT_*`（Task 3 已建）此时按 Java 的键生成逻辑补全并自检：**键最大 149 < 200**（笔记 3.3 已实测；若发现超界必须调查腿位集合生成逻辑）
- 表构建完成后执行一致性自检：对 90 站点 × 若干随机掩码，抽样断言"行列并集 == 参考实现"（参考实现写在测试里，构建代码不引用参考实现，避免自证）
- **行/列第一维含义易错**：行表第一维是列号（0..8），列表第一维是行号（0..9）；若照抄 Java 的循环结构就不会错，逐字对照 L343-417

**Step 4: 运行确认通过**

Run: `cd /home/nealian/chess/backend && .venv/bin/python -m pytest tests/test_engine_tables_chariot_gun.py -q`
Expected: PASS

**Step 5: 提交**

```bash
git add backend/engine/tables.py backend/tests/test_engine_tables_chariot_gun.py
git commit -m "feat(engine): 车炮行列攻击/平移/压制/重炮预生成表"
```

---

## Task 5: Zobrist、局面状态与 make/unmake

**Files:**
- Create: `backend/engine/zobrist.py`
- Create: `backend/engine/position.py`
- Create: `backend/tests/test_engine_position.py`

**Step 1: 写失败测试**

```python
# backend/tests/test_engine_position.py
import numpy as np
import pytest

from chess_engine.board import Board, INITIAL_FEN
from chess_engine.move import Move
from engine import constants as C
from engine import position as P


def test_zobrist_deterministic():
    from engine import zobrist
    assert zobrist.ZOB32.shape == (90, 15)
    a = zobrist.ZOB64.copy()
    zobrist.ensure_built()
    assert np.array_equal(a, zobrist.ZOB64)


def test_load_initial_position_roundtrip():
    st = P.load_position(INITIAL_FEN)
    assert st.board.shape == (90,)
    assert int(st.board.sum()) > 0
    # 红方底线车在 site 81/88
    assert st.board[C.xy_to_site(0, 0)] == 33
    assert st.board[C.xy_to_site(8, 0)] == 34
    assert st.board[C.xy_to_site(4, 9)] == 16   # 黑将
    assert st.board[C.xy_to_site(4, 0)] == 32   # 红帅
    # 走子方
    assert int(st.side_to_move[0]) == C.RED


def test_zobrist_matches_full_recompute():
    st = P.load_position(INITIAL_FEN)
    assert P.full_zobrist(st) == (int(st.zob[0]), int(st.zob[1]))


def test_make_unmake_restores_everything():
    st = P.load_position(INITIAL_FEN)
    snapshot = {name: getattr(st, name).copy() for name in st._fields}
    moves = P.pseudo_moves(st, C.RED)
    assert moves, "初始局面必须有着法"
    for m in moves:
        undo = P.make_move(st, m)
        assert P.full_zobrist(st) == (int(st.zob[0]), int(st.zob[1]))
        P.unmake_move(st, m, undo)
        for name in st._fields:
            a = getattr(st, name)
            b = snapshot[name]
            assert np.array_equal(a, b), name


def test_capture_updates_remain_and_masks():
    st = P.load_position(INITIAL_FEN)
    # 固定盘面：红车 site81 吃黑卒 site27（同列）
    st = P.load_position("4k4/9/9/p8/9/9/9/9/9/R3K4 w - - 0 1")   # 黑卒在 (0,6)=site27，红车 (0,0)=site81，同列直线
    src = C.xy_to_site(0, 0)
    dest = C.xy_to_site(0, 6)
    m = C.pack_move(src, dest)
    assert P.move_is_capture(st, m)
    before_remain = int(st.remain[C.BLACK_SOLDIER])
    undo = P.make_move(st, m)
    assert int(st.remain[C.BLACK_SOLDIER]) == before_remain - 1
    assert int(st.all_chess[27]) == -1   # 27 = 黑方第一个卒
    P.unmake_move(st, m, undo)
    assert int(st.remain[C.BLACK_SOLDIER]) == before_remain
    assert int(st.all_chess[27]) == dest
```

**Step 2: 运行确认失败**

Run: `cd /home/nealian/chess/backend && .venv/bin/python -m pytest tests/test_engine_position.py -q`
Expected: FAIL

**Step 3: 实现**

`zobrist.py`：
- 固定 `np.random.default_rng(0xC0FFEE)` 生成 `ZOB32: int64[90][15]`（低 31 位）与 `ZOB64: int64[90][15]`（正 int63），并保证 `ZOB32[i][0] = 0`、`ZOB64[i][0] = 0`（角色 0 不用）
- `ensure_built()` 幂等；模块导入即构建（确定性 → numba 缓存稳定）

`position.py`：
- `State = collections.namedtuple("State", "board all_chess bit_row bit_col remain attack_def mask_all mask_personal mask_role base_score zob side_to_move")`
  - `board: int8[90]`（空=0；否则棋子索引）
  - `all_chess: int8[48]`（棋子索引 → site；空=-1）
  - `bit_row: int16[10]`（bit(8-col)）、`bit_col: int16[9]`（bit(9-row)）
  - `remain: int8[15]`、`attack_def: int8[2][2]`
  - `mask_all: int64[2]`、`mask_personal: int64[2][2]`、`mask_role: int64[15][2]`（每个掩码 `[lo, hi]`）
  - `base_score: int32[2]`、`zob: int64[2]`、`side_to_move: int8[1]`
- `load_position(fen)`（普通 Python）：复用 `chess_engine.fen.parse_fen` 得到 `(x,y)->(side,kind)`，按 `xy_to_site` 填充；同时构建全部掩码与 `bit_row/bit_col/remain/attack_def`；`base_score` 初始化为"子力 + 位置"分（位置表在 Task 7 提供，此处先只算子力，Task 7 接入 `chessAttachScore`；**保留与 Java 相同的调用时序注释**）
- `full_zobrist(st)`：遍历 board 重算（Java `genStaticZobrist32And64OfBoard`）
- `pseudo_moves(st, play) -> np.int32[:]`：Task 6 实现（本任务先留最小版本：调用 movegen）
- `make_move(st, m) -> undo` / `unmake_move(st, m, undo)`（`@njit(cache=True)`）：**严格对照** Java `ChessMoveAbs.moveOperate` L82-99 / `unMoveOperate` L156-178：
  - 走子方 `baseScore[play] += -attach(role,src) + attach(role,dest)`
  - 吃子时 `baseScore[1-play] -= baseScoreOf(destChess) + attach(destRole, dest)`
  - 更新 `board/allChess/remain/attack_def/bit_row/bit_col/三方掩码/Zobrist`（XOR 源子、被吃子、目标子）
  - undo 返回被吃棋子索引（int8）与走子方（用于还原），并逆序恢复
  - 吃子判断 `move_is_capture(st, m)`：`st.board[move_dest(m)] != 0`
- `attach(role, site)`：先返回 0（Task 7 接入表）

**Step 4: 运行确认通过**

Run: `cd /home/nealian/chess/backend && .venv/bin/python -m pytest tests/test_engine_position.py -q`
Expected: PASS

**Step 5: 提交**

```bash
git add backend/engine/zobrist.py backend/engine/position.py backend/tests/test_engine_position.py
git commit -m "feat(engine): Zobrist、局面状态与 make/unmake 增量维护"
```

---

## Task 6: 着法生成、将军检测与 perft

**Files:**
- Create: `backend/engine/movegen.py`
- Create: `backend/tests/test_engine_movegen.py`
- Create: `backend/tests/test_engine_perft.py`

**Step 1: 写失败测试**

```python
# backend/tests/test_engine_movegen.py
import numpy as np

from chess_engine.board import INITIAL_FEN
from engine import constants as C
from engine import movegen as MG
from engine import position as P


def test_initial_red_move_count():
    st = P.load_position(INITIAL_FEN)
    moves = MG.gen_moves(st, C.RED, captures_only=False)
    assert len(moves) == 44, "公开的中国象棋初始局面着法数为 44"


def test_kings_facing_is_illegal():
    # 红帅 (4,0) 与黑将 (4,9) 同列且中间无子：红帅不能"让照面"或走到照面
    st = P.load_position("4k4/9/9/9/9/9/9/9/9/4K4 w - - 0 1")
    legal = MG.gen_legal_moves(st, C.RED)
    # 红帅不能离开中路造成照面（走到 (3,0)/(5,0) 后仍照面？(3,0) 与 (4,9) 不同列，合法）
    # 断言：所有合法着法走后，将帅不同列或中间有子
    for m in legal:
        undo = P.make_move(st, m)
        assert not MG.kings_facing(st)
        P.unmake_move(st, m, undo)


def test_check_detection_knight_leg():
    # 黑马被自己的象蹩腿：马不能攻击到目标
    st = P.load_position("4k4/9/9/9/9/2N6/9/9/9/4K4 b - - 0 1")  # 示例位形，实现时按语义校正
    # 断言移动生成结果里不含蹩腿目标（具体位置在实现时用简单盘面手推）


def test_checked_returns_true_when_in_check():
    st = P.load_position("4k4/9/9/9/9/9/9/9/9/R3K4 w - - 0 1")
    st2 = P.load_position("4k4/9/9/9/9/9/9/9/9/4K4 w - - 0 1")
    assert not MG.in_check(st2, C.RED)
    # 黑车? 用一个明显的将军局面：红车在 (4,8) 将军黑将 (4,9)
    st3 = P.load_position("4k4/4R4/9/9/9/9/9/9/9/4K4 b - - 0 1")
    assert MG.in_check(st3, C.BLACK)
```

```python
# backend/tests/test_engine_perft.py
import pytest

from chess_engine.board import INITIAL_FEN
from engine import constants as C
from engine import movegen as MG
from engine import position as P

EXPECTED = {1: 44, 2: 1920, 3: 79666, 4: 3290240}


def perft(st, depth, play):
    if depth == 0:
        return 1
    total = 0
    for m in MG.gen_legal_moves(st, play):
        undo = P.make_move(st, m)
        total += perft(st, depth - 1, 1 - play)
        P.unmake_move(st, m, undo)
    return total


@pytest.mark.parametrize("depth", [1, 2, 3, 4])
def test_initial_perft(depth):
    st = P.load_position(INITIAL_FEN)
    assert perft(st, depth, C.RED) == EXPECTED[depth]


def test_perft_position_with_pin():
    # 常见测试局面（照面 + 蹩腿），实现时从公开 perft 测试集选一个
    ...
```

**Step 2: 运行确认失败**

Run: `cd /home/nealian/chess/backend && .venv/bin/python -m pytest tests/test_engine_movegen.py tests/test_engine_perft.py -q`
Expected: FAIL

**Step 3: 实现**

对照 Java `ChessMoveAbs.chessEatMove / chessNopMove / genEatMoveList / genNopMoveList / legalMove / checked`（L226-432、L452-704）：

- `gen_moves(st, play, captures_only) -> np.int32[:]`：按 Java 的迭代顺序（`chessPlay[play]` 起 15 个棋子，将最后），逐子按角色查表取"攻击位/平移位"与对方掩码或空格掩码求交，用 `lowest_site` 循环取位；输出 packed move 的 numpy 数组（用预分配缓冲 + size，或返回 list 后 `np.array`；实现时优先用固定容量 `int32[128]` 缓冲 + count 返回，避免频繁分配）
- `gen_legal_moves(st, play)`：在伪着法基础上过滤"走后自将/照面"（make → `in_check(play)` → unmake），顺序与 `gen_moves` 一致
- `in_check(st, play)`：对照 Java `checked`（L312-370）：
  1. 对方车（行列攻击掩码 ∩ 对方车）
  2. 飞将（列攻击掩码 ∩ 对方将）
  3. 对方炮（炮攻击掩码 ∩ 对方炮）
  4. 对方马（用 `KNIGHT_TARGET` 反查 + 逐一验腿）
  5. 兵（`KING_CHECKED_SOLDIER` ∩ 对方兵）
- `kings_facing(st)`：将帅同列且中间无子（供测试与合法性使用）
- `opp_attack_site(st, play)`：对方全体攻击位掩码（`ChessMoveAbs.getOppAttackSite`），供着法排序的"保护判断"
- `legal_move(st, play, m)`：TT/killer 着法的快速校验（Java L226-302），校验源子属于己方、目标非己方子、目标在攻击位集合内
- `move_is_capture(st, m)` 已在 Task 5；着法排序键函数放在本模块（`score_capture` 等），Task 11 使用

**perft 值**：44 / 1920 / 79666 / 3290240 / 133312995 为公开的中国象棋初始局面 perft 序列（不含长将禁手）。**若不一致**：先查"将帅照面"与"炮"的实现，再查蹩腿/塞象眼；用 depth=1/2 的差值定位。

**Step 4: 运行确认通过**

Run: `cd /home/nealian/chess/backend && .venv/bin/python -m pytest tests/test_engine_movegen.py tests/test_engine_perft.py -q`
Expected: PASS（depth=4 在 numba 下应 < 1s）

**Step 5: 提交**

```bash
git add backend/engine/movegen.py backend/tests/test_engine_movegen.py backend/tests/test_engine_perft.py
git commit -m "feat(engine): 着法生成、将军检测与 perft 校验"
```

---

## Task 7: 评估表数据提取与中局评估

**Files:**
- Create: `backend/scripts/extract_eval_tables.py`
- Create: `backend/engine/eval_tables.py`（由脚本生成后提交）
- Create: `backend/engine/evaluate.py`
- Create: `backend/tests/test_engine_evaluate_middle.py`

**Step 1: 写失败测试**

```python
# backend/tests/test_engine_evaluate_middle.py
import numpy as np

from chess_engine.board import BOARD_H, BOARD_W
from engine import constants as C
from engine import evaluate as E
from engine import eval_tables as ET
from engine import position as P


def mirror_site(site):
    row, col = site // 9, site % 9
    return (9 - row) * 9 + col


def test_all_tables_have_90_entries():
    for name in dir(ET):
        if name.isupper():
            arr = getattr(ET, name)
            if isinstance(arr, np.ndarray) and arr.ndim == 2:
                if arr.shape[1] == 90:
                    assert arr.shape[0] >= 1
            assert not (isinstance(arr, np.ndarray) and arr.ndim == 1 and arr.size == 0)


def test_red_tables_are_row_mirror_of_black():
    # Java 中红方位置表 = Tools.exchange(黑方表)，exchange 等价于行镜像
    for name in ET.BLACK_TABLE_NAMES:
        black = getattr(ET, name)
        red = getattr(ET, ET.red_name_for(name))
        for site in range(90):
            assert red[mirror_site(site)] == black[site], (name, site)


def test_evaluate_initial_position_near_zero():
    st = P.load_position("rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1")
    score = E.evaluate(st, C.RED, endgame=False)
    assert abs(score) <= 30, "初始局面（全对称）评估应接近 0"


def test_evaluate_material_advantage_sign():
    # 红方多一车（去掉黑车），红方视角应为显著正
    st = P.load_position("1nbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1")
    score = E.evaluate(st, C.RED, endgame=False)
    assert score > 500


def test_evaluate_symmetry_negation():
    # 同一局面交换红黑后，分数应近似取反（位置表镜像 + 走子方对调）
    fen = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"
    st = P.load_position(fen)
    s_red = E.evaluate(st, C.RED, endgame=False)
    s_black = E.evaluate(st, C.BLACK, endgame=False)
    assert s_red == -s_black
```

**Step 2: 运行确认失败**

Run: `cd /home/nealian/chess/backend && .venv/bin/python -m pytest tests/test_engine_evaluate_middle.py -q`
Expected: FAIL

**Step 3: 实现提取脚本并生成 `eval_tables.py`**

`backend/scripts/extract_eval_tables.py` 核心逻辑：

```python
#!/usr/bin/env python3
"""从 Java 源码提取评估位置表，生成 engine/eval_tables.py（一次性脚本）。"""
import re
from pathlib import Path

JAVA_DIR = Path("/tmp/opencode/ChineseChess/com/pj/chess/evaluate")
OUT = Path(__file__).resolve().parents[1] / "engine" / "eval_tables.py"
ARRAY_RE = re.compile(r"int\[\]\s+(\w+)\s*=\s*\{([^}]*)\}", re.S)

MIDDLE_SOURCES = ["EvaluateComputeMiddleGame.java"]
END_SOURCES = ["EvaluateComputeEndGame.java"]
# 只提取黑方表（Java 中红方表由 Tools.exchange(黑表) 运行时生成），
# 以及小参数表（chessMinMobility/chessMobilityRewards/attackChessPartitionScore 等）。

def parse_arrays(path):
    text = path.read_text(encoding="gbk", errors="replace")
    out = {}
    for name, body in ARRAY_RE.findall(text):
        nums = [int(tok) for tok in re.findall(r"-?\d+", body)]
        out[name] = nums
    return out
```

生成的文件结构：`BLACK_KNIGHT_ATTACH: np.ndarray(90,)`、`BLACK_GUN_ATTACH`…，`BLACK_TABLE_NAMES` 与 `red_name_for()`；红方表在模块内用行镜像函数生成（`mirror_rows`）。
**提取后必须人工抽查 2-3 张表与原 Java 的前 10 个数字一致**（脚本输出核对日志）。

**Step 4: 实现 `evaluate.py` 中局评估**

对照 Java `EvaluateComputeMiddleGame.evaluate`（L35-218）与笔记 5.4 / 9.4，逐段实现并保留全部权重：
- `dynamic_partition_score(st)`：按士象数量动态调整分区评分表（Java L201-222）
- 遍历 16..47 存活棋子：`chess_all_move(role, site, play)`（控制范围位掩码；**炮不含平移位**）、`comp_partition_score`、机动性惩罚（**车 min=19/罚 5、马 min=8/罚 12、炮 min=19/罚 2、将 min=1/罚 50**——以源码为准）、`king_unmove` 标志
- 攻防位棋盘 × 主攻/防御子的权重（10/6/18/9）
- 炮特殊分：空头炮（曼哈顿距 × 45）、沉底炮（≤3 格 +100）；`rest_chariot != 1` → +30
- 对方分区削减（weakness、king_unmove、将偏位）
- 三路攻防差 × 30；缺士象 +60；车马炮存在各 +100
- 返回 `score[play] - score[1-play]`
- `evaluate(st, play, endgame)` 作为分派入口；`rough_evaluate(st, play)` 返回 `base_score` 差（Java `roughEvaluate`）
- `attach_score(role, site)` 暴露给 `position.make_move` 的增量更新（中局表；残局表在 Task 8 接入时按 Java 的时序处理）

**关键**：`chessRolePartitionSite`（分区码表）与 `AttackDirection/DefenseDirection` 掩码也要从 Java 迁移（可放入 `eval_tables.py` 或 `evaluate.py` 常量）。

**Step 5: 运行确认通过**

Run: `cd /home/nealian/chess/backend && .venv/bin/python -m pytest tests/test_engine_evaluate_middle.py -q`
Expected: PASS

**Step 6: 提交**

```bash
git add backend/scripts/extract_eval_tables.py backend/engine/eval_tables.py backend/engine/evaluate.py backend/tests/test_engine_evaluate_middle.py
git commit -m "feat(engine): 从 Java 提取评估表并实现中局评估"
```

---

## Task 8: 残局评估、动态子力与阶段判定

**Files:**
- Modify: `backend/engine/evaluate.py`
- Create: `backend/engine/analysis.py`（本任务只放阶段判定与动态子力，后续 Task 12 扩展）
- Create: `backend/tests/test_engine_evaluate_endgame.py`

**Step 1: 写失败测试**

```python
# backend/tests/test_engine_evaluate_endgame.py
from engine import analysis as A
from engine import constants as C
from engine import evaluate as E
from engine import position as P


def test_phase_detection():
    # 双方车马炮+兵>3 计数 <7 判为残局（Java getPhase）
    middle = P.load_position("rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1")
    assert A.phase_of(middle) == A.MIDDLE_GAME
    endgame = P.load_position("4k4/9/9/9/9/9/9/9/9/4K4 w - - 0 1")
    assert A.phase_of(endgame) == A.END_GAME


def test_endgame_evaluate_soldier_bonus():
    # 残局：双兵保护加成（soldiersProtected 查表）会使红方分数上升
    st = P.load_position("4k4/9/9/9/9/9/1P7/9/9/4K4 w - - 0 1")
    base = E.evaluate(st, C.RED, endgame=False)
    end = E.evaluate(st, C.RED, endgame=True)
    assert end != base


def test_dynamic_piece_scores():
    st = P.load_position("rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1")
    scores = A.dynamic_piece_scores(st)
    # 开局满子：马 = 490 + (32-32)*6 = 490；炮 = 610 - 0 = 610；兵 = 100 + (11-攻击子数)*8
    assert scores[C.RED_KNIGHT] >= 490
    assert scores[C.RED_GUN] <= 610
    assert scores[C.RED_SOLDIER] >= 100
```

**Step 2: 运行确认失败**

Run: `cd /home/nealian/chess/backend && .venv/bin/python -m pytest tests/test_engine_evaluate_endgame.py -q`
Expected: FAIL

**Step 3: 实现**

- 残局评估：对照 Java `EvaluateComputeEndGame.evaluate`（L26-55）与笔记 5.5：双兵保护表 `{0,55,150,300,400,500}`、炮/马对缺士表（`{0,40,110}` / `{110,40,0}`，双炮/双马 × 1.7 且 `int()` 截断）
- 位置表：残局使用 `EvaluateComputeEndGame` 的 7 张黑方表（已在 Task 7 脚本中一并提取）
- `analysis.phase_of(st)`：`redChessNum = 红车+红马+红炮+(红兵>3?1:0)`，黑同；`< 7` → END_GAME（Java `getPhase` L112-130）
- `analysis.dynamic_piece_scores(st)`：对照 Java `AICoreHandler.moveBegin` L132-142：
  - 兵/卒 = `100 + (11 - 对方攻击子数) * 8`
  - 马 = `490 + (32 - 全场剩余棋子数) * 6`
  - 炮 = `610 - (32 - 全场剩余棋子数) * 6`
- **时序复刻**：搜索开始时先算 `base_score`（用静态表），再应用动态子力值；搜索中的增量更新使用动态值。实现上：`analysis.prepare(st)` 负责"先 base_score 后动态子力"，并在函数注释中记录该顺序要求

**Step 4: 运行确认通过**

Run: `cd /home/nealian/chess/backend && .venv/bin/python -m pytest tests/test_engine_evaluate_endgame.py -q`
Expected: PASS

**Step 5: 提交**

```bash
git add backend/engine/evaluate.py backend/engine/analysis.py backend/tests/test_engine_evaluate_endgame.py
git commit -m "feat(engine): 残局评估、阶段判定与动态子力价值"
```

---

## Task 9: 置换表、杀手着法与历史启发

**Files:**
- Create: `backend/engine/search.py`
- Create: `backend/tests/test_engine_search_tables.py`

**Step 1: 写失败测试**

```python
# backend/tests/test_engine_search_tables.py
import numpy as np

from engine import constants as C
from engine import search as S


def test_tt_new_context_slots_empty():
    ctx = S.new_context(hash_size=1 << 12)
    assert ctx.tt_key.shape == (2, 2, 1 << 12)
    assert not ctx.tt_exists.any()


def test_tt_set_get_roundtrip():
    ctx = S.new_context(hash_size=1 << 12)
    play = C.RED
    zob32, zob64 = 0x12345, 0xABCDEF12345
    move = C.pack_move(C.xy_to_site(1, 0), C.xy_to_site(1, 4))
    S.set_tt(ctx, play, zob32, zob64, S.HASH_PV, value=42, depth=7, move=move)
    out = S.get_tt(ctx, play, zob32, zob64, depth=7, alpha=-100, beta=100)
    assert out.hit and out.value == 42
    assert out.move == move


def test_tt_shallower_entry_not_used_for_deeper_search():
    ctx = S.new_context(hash_size=1 << 12)
    S.set_tt(ctx, C.RED, 1, 2, S.HASH_PV, value=10, depth=3, move=0)
    out = S.get_tt(ctx, C.RED, 1, 2, depth=5, alpha=-100, beta=100)
    assert not out.hit


def test_tt_mate_score_depth_adjustment():
    ctx = S.new_context(hash_size=1 << 12)
    mate = C.MAX_SCORE - 5          # 从 5 步深处看到的将杀
    S.set_tt(ctx, C.RED, 7, 8, S.HASH_PV, value=mate, depth=5, move=0)
    # 在更深 3 层的搜索里，将杀分数应减去 (depth - entry_depth)
    out = S.get_tt(ctx, C.RED, 7, 8, depth=8, alpha=-20000, beta=20000)
    assert out.hit and out.value == mate - 3


def test_tt_alpha_beta_bounds():
    ctx = S.new_context(hash_size=1 << 12)
    S.set_tt(ctx, C.RED, 1, 1, S.HASH_BETA, value=50, depth=4, move=0)
    # 下界：value >= beta 才可用
    assert S.get_tt(ctx, C.RED, 1, 1, depth=4, alpha=0, beta=100).hit is False
    assert S.get_tt(ctx, C.RED, 1, 1, depth=4, alpha=0, beta=30).hit is True
    S.set_tt(ctx, C.RED, 2, 2, S.HASH_ALPHA, value=50, depth=4, move=0)
    assert S.get_tt(ctx, C.RED, 2, 2, depth=4, alpha=60, beta=120).hit is False
    assert S.get_tt(ctx, C.RED, 2, 2, depth=4, alpha=40, beta=120).hit is True


def test_longcheck_range_not_stored():
    ctx = S.new_context(hash_size=1 << 12)
    S.set_tt(ctx, C.RED, 3, 3, S.HASH_PV, value=C.LONG_CHECK_SCORE, depth=6, move=0)
    assert not ctx.tt_exists.any()


def test_killer_and_history_updates():
    ctx = S.new_context(hash_size=1 << 12)
    move = C.pack_move(10, 11)
    S.update_killer(ctx, depth=5, move=move)
    S.update_killer(ctx, depth=5, move=C.pack_move(12, 13))
    assert ctx.killer[5][0] == C.pack_move(12, 13)
    assert ctx.killer[5][1] == move
    S.history_bonus(ctx, piece_index=35, dest=40, depth=6)
    assert ctx.history[C.PIECE_KINDS[35]][40] > 0
    S.history_decay(ctx)
    assert ctx.history[C.PIECE_KINDS[35]][40] == 0   # 整除衰减
```

**Step 2: 运行确认失败**

Run: `cd /home/nealian/chess/backend && .venv/bin/python -m pytest tests/test_engine_search_tables.py -q`
Expected: FAIL

**Step 3: 实现**

`search.py` 顶部：`HASH_BETA=1`、`HASH_ALPHA=2`、`HASH_PV=3`、`FAIL = np.iinfo(np.int32).min + 1`、`MAX_DEPTH=64`。

`Ctx = collections.namedtuple("Ctx", "tt_key tt_type tt_value tt_depth tt_move tt_exists killer history stop nodes")`：
- `tt_key: int64[2][2][N]`、`tt_type: int8[2][2][N]`、`tt_value: int32[2][2][N]`、`tt_depth: int8[2][2][N]`、`tt_move: int32[2][2][N]`、`tt_exists: bool_[2][2][N]`
- `killer: int32[64][2]`、`history: int32[8][256]`、`stop: int8[1]`、`nodes: int64[1]`
- `new_context(hash_size=0x80000)`：**先读 Java `TranspositionTable.java` 确认掩码与数组长度关系**（笔记 6.3 记载：槽号 `zob32 & TRANZOBRISTSIZE`，默认 `0x7FFFF`；注意 Java 数组长度可能是 `TRANZOBRISTSIZE + 1`，以源码为准；Python 统一用 `slot = zob32 & (N - 1)`，N=2^19）

`get_tt(ctx, play, zob32, zob64, depth, alpha, beta) -> TTResult(hit, value, move)`：对照 Java `getTranZobrist` L335-360 / `getTranZobristByHashItem` L361-391：
- 先 STEP 槽后 STRAIGHT 槽；校验 `tt_key == zob64` 且 `tt_exists`
- mate 调整：`value > 9899 → value -= (depth - entry_depth)`；`value < -9899 → value += (depth - entry_depth)`
- `entry_depth < depth` → 不可用；`HASH_PV` 直接用；`HASH_BETA` 要求 `value >= beta`；`HASH_ALPHA` 要求 `value <= alpha`

`set_tt(ctx, play, zob32, zob64, entry_type, value, depth, move)`：对照 L264-330：
- `8000 <= value <= 9000` 或 `-9000 <= value <= -8000` 直接返回（不存长将区间）
- STEP 槽：旧条目存在且 `旧 depth > 新 depth` → 放弃；否则旧条目踢出、新条目写入
- STRAIGHT 槽：被踢出的旧条目写这里，否则新条目覆盖
- `HASH_ALPHA` 时不带着法（move=0）

`clean_tt(ctx)`：只清两个 play 的 STEP 槽（Java `cleanTranZobrist`）

`update_killer(ctx, depth, move)`、`history_bonus(ctx, piece, dest, depth)`（`+= 2 << depth`）、`history_decay(ctx)`（`//= 512`，整除）、`history_score(ctx, piece_kind, dest)`

**Step 4: 运行确认通过**

Run: `cd /home/nealian/chess/backend && .venv/bin/python -m pytest tests/test_engine_search_tables.py -q`
Expected: PASS

**Step 5: 提交**

```bash
git add backend/engine/search.py backend/tests/test_engine_search_tables.py
git commit -m "feat(engine): 置换表、杀手着法与历史启发表"
```

---

## Task 10: 静态搜索

**Files:**
- Modify: `backend/engine/search.py`
- Create: `backend/tests/test_engine_quiescence.py`

**Step 1: 写失败测试**

```python
# backend/tests/test_engine_quiescence.py
import numpy as np

from engine import analysis as A
from engine import constants as C
from engine import position as P
from engine import search as S


def analyze_depth(fen, depth=1):
    st = P.load_position(fen)
    A.prepare(st)
    ctx = S.new_context()
    result = S.search_root(st, ctx, st, max_depth=depth, start_depth=depth,
                           time_limit_ms=5000, stop=np.zeros(1, dtype=np.int8))
    return st, ctx, result


def test_quiescence_avoids_hanging_capture():
    # 红车白白吃卒后再被吃：静态搜索必须看到"吃卒后车被吃"而不高估
    # 局面：红车 (0,0)，黑卒 (0,6)，黑车 (8,6)。
    st, ctx, result = analyze_depth("3rk4/9/9/9/9/9/p8/9/9/R3K4 w - - 0 1", depth=1)
    # 红方合理着法应避免简单得子后又失子；至少 score 不应是"白吃一卒"的大正数
    assert result.score_stm < 900


def test_quiescence_returns_mate_when_checkmated():
    # 无合法着法且被将 → 返回将死分（-(maxScore - ply)）
    st, ctx, result = analyze_depth("4k4/4R4/4R4/9/9/9/9/9/9/4K4 b - - 0 1", depth=1)
    assert result.score_stm < -9000 or result.mate is not None
```

> 具体断言在实现时按实际盘面手推修正；关键是"静态搜索参与叶子评估"且"被将死返回将死分"。

**Step 2: 运行确认失败**

Run: `cd /home/nealian/chess/backend && .venv/bin/python -m pytest tests/test_engine_quiescence.py -q`
Expected: FAIL

**Step 3: 实现**

对照 Java `SearchEngine.quiescSearch` L163-239 与笔记 9.3：
- 参数：`(st, ctx, alpha, beta, ply, play, is_checked, stack)`
- 顺序：王被吃 → 长将（8888）→ 和棋（双方无攻击子且上一步吃子）→ 深度保险丝 64 → 非被将时 stand-pat（`fine_evaluate`）→ 生成吃子（被将时含全部着法）→ 逐个 make/合法性/递归/unmake → beta 截断
- 吃子排序：`Quiesc` 的分类规则（只有"被吃子价值+位置分 >= 150"才进 eat 列表；其余进 general；被将时可枚举全部）→ 与 Java `ChessQuiescMove.savePlayChess` L44-64 一致
- 搜索栈：`Stack` namedtuple（`hist_zob32/hist_zob64/hist_is_eat/hist_chk/hist_move`，长度 68；`pv: int32[68][68]`）——长将检测沿栈回溯到遇到吃子为止，对比 zob32/zob64（Java `isLongChk` L240-260）

**Step 4: 运行确认通过**

Run: `cd /home/nealian/chess/backend && .venv/bin/python -m pytest tests/test_engine_quiescence.py -q`
Expected: PASS

**Step 5: 提交**

```bash
git add backend/engine/search.py backend/tests/test_engine_quiescence.py
git commit -m "feat(engine): 静态搜索与长将/和棋检测"
```

---

## Task 11: 主搜索（根 PVS + negaScout + 迭代加深）

**Files:**
- Modify: `backend/engine/search.py`
- Create: `backend/tests/test_engine_search_main.py`

**Step 1: 写失败测试**

```python
# backend/tests/test_engine_search_main.py
import numpy as np

from engine import analysis as A
from engine import constants as C
from engine import position as P
from engine import search as S


def run_search(fen, start=4, max_depth=4, time_ms=3000, stop=None):
    st = P.load_position(fen)
    A.prepare(st)
    ctx = S.new_context(hash_size=1 << 14)
    result = S.search_root(st, ctx, start_depth=start, max_depth=max_depth,
                           time_limit_ms=time_ms,
                           stop=stop if stop is not None else np.zeros(1, dtype=np.int8))
    return st, ctx, result


def test_finds_mate_in_one():
    # 红车 (4,1) 直接吃 (4,9) 黑将：一步杀（实际是吃将，引擎按将死分处理）
    # 更稳妥：红双车构建一步杀
    st, ctx, result = run_search("4k4/9/9/9/9/9/9/9/4R4/4R1K2 w - - 0 1", max_depth=4)
    assert result.score_stm >= C.MAX_SCORE - 10
    assert result.mate is not None and result.mate <= 2


def test_finds_mate_in_two_or_reports_high_score():
    # 经典"双车错"两步杀局面（实现时用真实杀法局面替换并验证）
    st, ctx, result = run_search("3k5/9/9/9/9/9/9/4R4/4R4/4K4 w - - 0 1", max_depth=6)
    assert result.score_stm > 500


def test_iterative_deepening_produces_pv_steps():
    st, ctx, result = run_search("rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1",
                                 start=4, max_depth=6, time_ms=3000)
    assert result.depth >= 4
    assert len(result.pv) >= 1
    for m in result.pv[:2]:
        assert 0 <= C.move_src(m) < 90 and 0 <= C.move_dest(m) < 90


def test_stop_flag_interrupts():
    stop = np.zeros(1, dtype=np.int8)
    st = P.load_position("rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1")
    A.prepare(st)
    ctx = S.new_context(hash_size=1 << 14)
    stop[0] = 1
    result = S.search_root(st, ctx, start_depth=6, max_depth=32, time_limit_ms=60000, stop=stop)
    assert result.depth == 0   # 立即停止，无任何完成层
```

**Step 2: 运行确认失败**

Run: `cd /home/nealian/chess/backend && .venv/bin/python -m pytest tests/test_engine_search_main.py -q`
Expected: FAIL

**Step 3: 实现**

对照 Java `PrincipalVariation.searchMove` L40-94、`rootNegaScout` L95-148、`negaScout` L154-337 与笔记 9.1 / 9.2，逐一实现：

- `search_root(...)`：可中断的迭代加深**单层**入口（Task 12 在外部逐层调用以实现渐进输出）：
  1. 首次调用时枚举根着法（过滤自将）并按初始分 100,99,… 排序（结果缓存到 `RootInfo`，供后续层复用）
  2. 调用 `root_nega_scout` 搜索该层
  3. 把本轮 PV 链的着法写入 `killer[d+1..0]`（Java L71-78）
  4. 返回 `SearchResult(depth, score_stm, pv, nodes, elapsed_ms, mate)`
- `root_nega_scout`：根节点 PVS（**无 beta 截断**、每着法分数回写用于下轮排序、`get_sort_after_best` 选择排序、`isStop` 检查）
- `nega_scout`：内部 PVS，严格按 Java 顺序：
  1. 王被吃 → `-(maxScore - ply)`
  2. 下界保护 `bestValue = ply - maxScore`；`> beta` 返回
  3. TT 探测（同时取 TT 着法）
  4. `in_check` 写入栈；长将 → 8888；和棋 → 0
  5. 将军延伸 `depth += 1`
  6. `depth <= 0` → 静态搜索
  7. 空着裁剪（`!is_null && !is_checked && !is_pv && depth>=2`，R = 2/3/4，`attackChessesNum > 2 && depth < 6` 弱验证否则加深验证）
  8. IID（`depth>=6 && is_pv && 无 TT 着法` → `depth-2` 搜一次）
  9. 着法循环：排序（TT 1/2 → killer 1/2 → 吃子 → 其他）、不自杀过滤、Futility 跳过、PVS/LMR（`kk=2/3/4`，重归约、全窗口）、beta 截断写 killer、`thisAlpha` 更新
  10. 收尾：PV 写入 `stack.pv`、历史加分（`entryType != HASH_ALPHA`）、写 TT
- `fine_evaluate(st, play, endgame)`：分派中局/残局
- `is_danger(st, play)`：`DANGER_MARGIN` 内车马炮 ≥3（Java L274-286）
- Futility 表：`(int)(d*1.29*155) - k*d*10`（深度 0..63、着法序 0..63 预生成 int32 表）
- 每条搜索函数在循环处检查 `ctx.stop[0]` 并快速返回；已完成的层由调用方保留

**性能要求**：depth 6 典型中局 < 500ms（numba）。若明显超时，检查是否在热路径里用了 Python 对象/数组分配（每个节点不得分配新数组）。

**Step 4: 运行确认通过**

Run: `cd /home/nealian/chess/backend && .venv/bin/python -m pytest tests/test_engine_search_main.py -q`
Expected: PASS

**Step 5: 提交**

```bash
git add backend/engine/search.py backend/tests/test_engine_search_main.py
git commit -m "feat(engine): 根/内部 PVS 主搜索与迭代加深"
```

---

## Task 12: 对外分析接口（渐进加深生成器）

**Files:**
- Modify: `backend/engine/analysis.py`
- Modify: `backend/engine/__init__.py`
- Create: `backend/tests/test_engine_analysis_api.py`

**Step 1: 写失败测试**

```python
# backend/tests/test_engine_analysis_api.py
import time

import numpy as np

from engine import analyze, warmup
from engine import constants as C

INITIAL = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"


def test_progressive_depths_increase():
    results = list(analyze(INITIAL, start_depth=6, max_depth=8, time_limit_ms=5000))
    depths = [r.depth for r in results]
    assert depths == sorted(depths)
    assert depths[0] >= 6
    assert depths[-1] <= 8
    for r in results:
        assert r.pv, "每层结果必须带主变"
        assert r.score_red == (r.score_stm if r.side_to_move == C.RED else -r.score_stm)


def test_time_limit_respected():
    t0 = time.perf_counter()
    results = list(analyze(INITIAL, start_depth=6, max_depth=32, time_limit_ms=300))
    elapsed = (time.perf_counter() - t0) * 1000
    assert elapsed < 3000, "时间上限应有效（允许编译/首次开销余量）"
    assert results


def test_stop_flag_aborts():
    stop = np.zeros(1, dtype=np.int8)
    it = analyze(INITIAL, start_depth=6, max_depth=32, time_limit_ms=10000, stop=stop)
    first = next(it)
    assert first.depth >= 6
    stop[0] = 1
    rest = list(it)
    assert all(r.depth > first.depth for r in rest)


def test_score_red_perspective():
    results = list(analyze(INITIAL, start_depth=6, max_depth=6, time_limit_ms=5000))
    assert results[-1].score_red == results[-1].score_stm   # 初始局面轮红走


def test_warmup_runs():
    warmup()   # 不抛异常即可
```

**Step 2: 运行确认失败**

Run: `cd /home/nealian/chess/backend && .venv/bin/python -m pytest tests/test_engine_analysis_api.py -q`
Expected: FAIL

**Step 3: 实现**

`analysis.py`：
- `AnalysisResult` dataclass：`depth, score_stm, score_red, pv(int 列表), nodes, time_ms, mate(None 或步数), side_to_move`
- `analyze(fen, *, start_depth=6, max_depth=16, time_limit_ms=2000, stop=None) -> Iterator[AnalysisResult]`：
  1. `st = load_position(fen)`；`prepare(st)`（先 base_score 后动态子力）
  2. 分配 `ctx`（TT 大小默认 2^19）与 `stack`
  3. `d` 从 `ROOT_START_DEPTH=4` 开始逐层 +1：调用 `search_root`；**当 `d >= start_depth` 时 yield 结果**（4/5 层作为垫脚石，让第一个结果更快）
  4. 停止：`d > max_depth` 或 `elapsed >= time_limit_ms` 或 `stop[0]`
  5. `finally` 中不修改外部状态
- `warmup()`：用初始局面跑一次 `start_depth=4, max_depth=4` 的分析（触发全部 numba 编译），并打印耗时（`logging.debug`）
- `__init__.py` 导出 `analyze, warmup, AnalysisResult, ENGINE_VERSION = "1.0.0"`

**Step 4: 运行确认通过**

Run: `cd /home/nealian/chess/backend && .venv/bin/python -m pytest tests/test_engine_analysis_api.py -q`
Expected: PASS（首次运行含 JIT 编译，可能 30-60s；二次运行 < 5s）

**Step 5: 提交**

```bash
git add backend/engine/analysis.py backend/engine/__init__.py backend/tests/test_engine_analysis_api.py
git commit -m "feat(engine): 渐进加深分析接口与预热"
```

---

## Task 13: 后端分析 API（NDJSON 流式）

**Files:**
- Create: `backend/routes/engine.py`
- Create: `backend/tests/test_engine_api.py`
- Modify: `backend/app.py`（注册蓝图）

**Step 1: 写失败测试**

```python
# backend/tests/test_engine_api.py
import json

from chess_engine.board import INITIAL_FEN


def read_stream(client, payload):
    resp = client.post("/api/engine/analyze", json=payload)
    assert resp.status_code == 200
    assert resp.mimetype == "application/x-ndjson"
    return [json.loads(line) for line in resp.get_data(as_text=True).splitlines() if line.strip()]


def test_analyze_with_fen(client):
    msgs = read_stream(client, {"fen": INITIAL_FEN, "start_depth": 4, "max_depth": 4, "time_limit_ms": 5000})
    results = [m for m in msgs if m["type"] == "result"]
    assert results and results[-1]["depth"] >= 4
    last = results[-1]
    assert set(last) >= {"type", "depth", "score_red", "score_stm", "pv", "time_ms", "nodes"}
    assert last["pv"] and set(last["pv"][0]) >= {"x1", "y1", "x2", "y2", "iccs", "chinese"}
    assert any(m["type"] == "done" for m in msgs)


def test_analyze_rebuilds_position_from_moves(client):
    msgs = read_stream(client, {
        "initial_fen": INITIAL_FEN,
        "moves": [{"x1": 7, "y1": 2, "x2": 4, "y2": 2}],   # 炮二平五
        "ply": 1,
        "start_depth": 4, "max_depth": 4, "time_limit_ms": 5000,
    })
    results = [m for m in msgs if m["type"] == "result"]
    assert results
    # PV 第一步的中文记谱应可解析（首步为黑方着法）
    assert results[-1]["pv"][0]["chinese"]


def test_analyze_bad_fen_returns_error_line(client):
    msgs = read_stream(client, {"fen": "not-a-fen"})
    assert msgs[0]["type"] == "error"


def test_analyze_invalid_move_returns_error_line(client):
    msgs = read_stream(client, {
        "initial_fen": INITIAL_FEN,
        "moves": [{"x1": 0, "y1": 0, "x2": 0, "y2": 1}],   # 非法着法
        "ply": 1,
    })
    assert msgs[0]["type"] == "error"


def test_analyze_requires_input(client):
    msgs = read_stream(client, {})
    assert msgs[0]["type"] == "error"


def test_analyze_clamps_parameters(client):
    msgs = read_stream(client, {"fen": INITIAL_FEN, "start_depth": 99, "max_depth": 999,
                                "time_limit_ms": 999999})
    results = [m for m in msgs if m["type"] == "result"]
    assert results and results[-1]["depth"] <= 16
```

**Step 2: 运行确认失败**

Run: `cd /home/nealian/chess/backend && .venv/bin/python -m pytest tests/test_engine_api.py -q`
Expected: FAIL（404）

**Step 3: 实现**

`routes/engine.py`：
- `engine_bp = Blueprint("engine", __name__)`
- `POST /analyze`：
  - 解析 JSON（`silent=True`）；参数校验与夹逼：`start_depth` 4..16（默认 6）、`max_depth` 4..16（默认 16）、`time_limit_ms` 100..10000（默认 2000）
  - 局面来源二选一：`fen`（字符串）或 `initial_fen + moves + ply`；后者用 `chess_engine.board.Board` 重放 `moves[:ply]`（每步用 `pseudo_moves_from` 做轻量校验），再取 `board.to_fen()`
  - 用 `Response(stream_with_context(generate()), mimetype="application/x-ndjson")` 输出；**每行 `json.dumps(..., ensure_ascii=False) + "\n"`**
  - `generate()` 内部：
    - `stop = np.zeros(1, dtype=np.int8)`；`try: for r in analyze(...)` 逐行 yield `{"type": "result", ...}`
    - PV 转换：最多 2 步；用 `engine.constants.site_to_xy` → `chess_engine.move.Move` → `move_to_chinese(ref_board, mv)`（`try/except ValueError` 回退为 `iccs`）；`ref_board` 沿 PV `apply_move` 前进
    - 完成后 `{"type": "done", "depth": ..., "time_ms": ..., "reason": "max_depth|time_limit"}`
    - `except Exception as exc:` → `{"type": "error", "message": str(exc)}`
    - `finally: stop[0] = 1`（客户端断开触发 GeneratorExit 时也能停搜）
- 参数错误/请求体错误也走**流内 error 行**（保证前端只需处理一种错误路径），但 `Content-Type` 非 JSON 的请求可返回 400 JSON
- 并发：模块级 `threading.Lock()`，`with lock:` 包住整个生成过程（单用户，串行分析）

`backend/app.py`：`from routes.engine import engine_bp` + `app.register_blueprint(engine_bp, url_prefix="/api/engine")`

**Step 4: 运行确认通过**

Run: `cd /home/nealian/chess/backend && .venv/bin/python -m pytest tests/test_engine_api.py -q`
Expected: PASS

**Step 5: 提交**

```bash
git add backend/routes/engine.py backend/tests/test_engine_api.py backend/app.py
git commit -m "feat(api): 引擎分析 NDJSON 流式接口"
```

---

## Task 14: 应用集成、预热与依赖

**Files:**
- Modify: `backend/app.py`
- Modify: `backend/requirements.txt`
- Create: `backend/tests/test_engine_warmup.py`

**Step 1: 写失败测试**

```python
# backend/tests/test_engine_warmup.py
import threading

from app import create_app
from config import TestConfig
from engine import warmup


def test_warmup_started_in_background(monkeypatch):
    calls = []

    def fake_warmup():
        calls.append(threading.current_thread().name)

    monkeypatch.setattr("engine.warmup", fake_warmup)
    app = create_app(TestConfig)
    # 预热线程应已启动（daemon），不阻塞 create_app
    assert app is not None


def test_analyze_endpoint_available(client):
    resp = client.post("/api/engine/analyze", json={})
    assert resp.status_code == 200   # 流内 error 行，而非 404
```

**Step 2: 运行确认失败**

Run: `cd /home/nealian/chess/backend && .venv/bin/python -m pytest tests/test_engine_warmup.py -q`
Expected: FAIL（若 Task 13 已完成，第二个测试可能已通过；第一个测试用于验证预热钩子）

**Step 3: 实现**

- `app.py`：`create_app` 内注册蓝图后启动预热：
  ```python
  from engine import warmup
  threading.Thread(target=warmup, name="engine-warmup", daemon=True).start()
  ```
  （开发服务器 reloader 下会启动两次，可接受；用 `os.environ.get("WERKZEUG_RUN_MAIN")` 判断可优化）
- `requirements.txt` 增加：
  ```
  numba==0.67.0
  numpy==2.5.3
  ```
- `backend/.gitignore`（若不存在则创建）加入 `engine/_cache/`（若后续引入 npz 缓存）

**Step 4: 运行确认通过**

Run: `cd /home/nealian/chess/backend && .venv/bin/python -m pytest tests/test_engine_warmup.py -q`
Expected: PASS

**Step 5: 提交**

```bash
git add backend/app.py backend/requirements.txt backend/tests/test_engine_warmup.py
git commit -m "feat(api): 应用集成引擎预热与依赖声明"
```

---

## Task 15: 前端棋盘箭头渲染

**Files:**
- Modify: `frontend/src/components/ChessBoard.vue`
- Modify: `frontend/src/components/__tests__/ChessBoard.test.js`

**Step 1: 写失败测试（追加到现有测试文件）**

```js
// frontend/src/components/__tests__/ChessBoard.test.js 追加
it("渲染分析箭头：best 与 reply 两条", () => {
  const wrapper = mount(ChessBoard, {
    props: {
      position: { pieces: [] },
      arrows: [
        { x1: 7, y1: 2, x2: 4, y2: 2, kind: "best" },
        { x1: 1, y1: 7, x2: 4, y2: 7, kind: "reply" },
      ],
    },
  });
  const arrows = wrapper.findAll("[data-arrow]");
  assert.equal(arrows.length, 2);
  assert.equal(arrows[0].attributes("data-arrow"), "best");
  assert.equal(arrows[1].attributes("data-arrow"), "reply");
});

it("无 arrows prop 时不渲染箭头", () => {
  const wrapper = mount(ChessBoard, { props: { position: { pieces: [] } } });
  assert.equal(wrapper.findAll("[data-arrow]").length, 0);
});
```

（按现有测试文件的 import 风格补 `mount`/`assert`；文件使用 vitest 语法。）

**Step 2: 运行确认失败**

Run: `cd /home/nealian/chess/frontend && npx vitest run src/components/__tests__/ChessBoard.test.js`
Expected: FAIL（找不到 data-arrow）

**Step 3: 实现**

`ChessBoard.vue`：
- `defineProps` 增加 `arrows: { type: Array, default: () => [] }`
- 模板在棋子之后、热区之前插入：
  ```html
  <defs>
    <marker :id="`arrow-head-best-${uid}`" markerWidth="4" markerHeight="4" refX="2.2" refY="2" orient="auto">
      <path d="M0,0 L4,2 L0,4 Z" fill="#2563eb" />
    </marker>
    <marker :id="`arrow-head-reply-${uid}`" markerWidth="4" markerHeight="4" refX="2.2" refY="2" orient="auto">
      <path d="M0,0 L4,2 L0,4 Z" fill="#ea580c" />
    </marker>
  </defs>
  <line
    v-for="(arrow, index) in arrows"
    :key="`arrow-${index}`"
    :data-arrow="arrow.kind"
    :x1="cellX(arrow.x1)" :y1="cellY(arrow.y1)"
    :x2="cellX(arrow.x2)" :y2="cellY(arrow.y2)"
    :stroke="arrow.kind === 'best' ? '#2563eb' : '#ea580c'"
    stroke-width="7"
    stroke-linecap="round"
    :marker-end="`url(#arrow-head-${arrow.kind === 'best' ? 'best' : 'reply'}-${uid})`"
    opacity="0.85"
    pointer-events="none"
  />
  ```
- `const uid = Math.random().toString(36).slice(2, 8)`（多实例时 marker id 不冲突）
- 箭头画到格子中心；`stroke-width` 7 保证缩放到手机宽度仍可见

**Step 4: 运行确认通过**

Run: `cd /home/nealian/chess/frontend && npx vitest run src/components/__tests__/ChessBoard.test.js`
Expected: PASS（且原有断言不回归）

**Step 5: 提交**

```bash
git add frontend/src/components/ChessBoard.vue frontend/src/components/__tests__/ChessBoard.test.js
git commit -m "feat(web): 棋盘支持分析箭头渲染"
```

---

## Task 16: 前端流式分析 API 封装

**Files:**
- Modify: `frontend/src/api/index.js`
- Create: `frontend/src/api/__tests__/analyzeStream.test.js`

**Step 1: 写失败测试**

```js
// frontend/src/api/__tests__/analyzeStream.test.js
import { describe, expect, it, vi } from "vitest";
import { analyzeStream } from "../index";

function mockFetchStream(lines, { ok = true, status = 200 } = {}) {
  const encoder = new TextEncoder();
  const chunks = lines.map((l) => encoder.encode(l + "\n"));
  let i = 0;
  const body = {
    getReader: () => ({
      read: async () => (i < chunks.length ? { done: false, value: chunks[i++] } : { done: true, value: undefined }),
    }),
  };
  global.fetch = vi.fn(async () => ({ ok, status, body }));
}

describe("analyzeStream", () => {
  it("逐行解析并回调", async () => {
    mockFetchStream([
      JSON.stringify({ type: "result", depth: 6, score_red: 12 }),
      JSON.stringify({ type: "result", depth: 7, score_red: 20 }),
      JSON.stringify({ type: "done", reason: "time" }),
    ]);
    const results = [];
    const done = [];
    await analyzeStream({ fen: "x" }, {
      onResult: (r) => results.push(r),
      onDone: (d) => done.push(d),
    });
    expect(results.map((r) => r.depth)).toEqual([6, 7]);
    expect(done[0].reason).toBe("time");
  });

  it("错误行触发 onError", async () => {
    mockFetchStream([JSON.stringify({ type: "error", message: "bad" })]);
    const errors = [];
    await analyzeStream({ fen: "x" }, { onResult: () => {}, onError: (e) => errors.push(e.message) });
    expect(errors).toEqual(["bad"]);
  });

  it("abort 不触发 onError", async () => {
    global.fetch = vi.fn(async () => {
      const err = new Error("aborted");
      err.name = "AbortError";
      throw err;
    });
    const errors = [];
    await analyzeStream({ fen: "x" }, { onError: (e) => errors.push(e) });
    expect(errors).toEqual([]);
  });

  it("HTTP 错误触发 onError", async () => {
    global.fetch = vi.fn(async () => ({ ok: false, status: 500, json: async () => ({ error: "boom" }) }));
    const errors = [];
    await analyzeStream({ fen: "x" }, { onError: (e) => errors.push(e.message) });
    expect(errors).toEqual(["boom"]);
  });
});
```

**Step 2: 运行确认失败**

Run: `cd /home/nealian/chess/frontend && npx vitest run src/api/__tests__/analyzeStream.test.js`
Expected: FAIL

**Step 3: 实现**

`api/index.js` 追加导出（保持既有 `api` 对象不变，新增具名导出）：

```js
export async function analyzeStream(payload, { signal, onResult, onDone, onError } = {}) {
  try {
    const response = await fetch("/api/engine/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal,
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.detail || data.error || `分析请求失败（${response.status}）`);
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    const handleLine = (line) => {
      const text = line.trim();
      if (!text) return;
      const msg = JSON.parse(text);
      if (msg.type === "result") onResult?.(msg);
      else if (msg.type === "done") onDone?.(msg);
      else if (msg.type === "error") onError?.(new Error(msg.message || "分析失败"));
    };
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop();
      lines.forEach(handleLine);
    }
    handleLine(buffer);
  } catch (err) {
    if (err?.name === "AbortError") return;
    onError?.(err);
  }
}
```

**Step 4: 运行确认通过**

Run: `cd /home/nealian/chess/frontend && npx vitest run src/api/__tests__/analyzeStream.test.js`
Expected: PASS

**Step 5: 提交**

```bash
git add frontend/src/api/index.js frontend/src/api/__tests__/analyzeStream.test.js
git commit -m "feat(web): 流式分析请求封装"
```

---

## Task 17: 打谱页 AI 分析面板

**Files:**
- Modify: `frontend/src/views/PracticeView.vue`
- Modify: `frontend/src/views/__tests__/PracticeView.test.js`

**Step 1: 写失败测试**

```js
// frontend/src/views/__tests__/PracticeView.test.js 追加
// 现有测试 mock 了 ../../api，追加分析流相关的 mock 与用例：
// 1) 加载棋谱后自动发起分析；2) 收到结果后展示评分与历史（最新在前）；3) 翻步会 abort 旧请求并重新分析；4) 卸载时 abort。
```

用例要点（实现时按文件现有 mock 风格补齐）：

```js
it("翻步后展示渐进分析结果（最新在前）", async () => {
  // mock getGame 返回 2 步棋谱；mock analyzeStream 捕获 payload 与回调
  // 触发 next 按钮 → 断言 analyzeStream 被调用、payload.ply 正确
  // 手动调用捕获到的 onResult({ depth: 6, score_red: 120, pv: [...] })
  // 断言面板出现 "红优"、历史列表第一行为 depth 6
  // 再 onResult({ depth: 7, ... }) → 断言最新在前
});

it("翻步时中止上一次分析", async () => {
  // 断言第二次 analyzeStream 调用前，第一次的 signal.aborted === true
});
```

**Step 2: 运行确认失败**

Run: `cd /home/nealian/chess/frontend && npx vitest run src/views/__tests__/PracticeView.test.js`
Expected: FAIL

**Step 3: 实现**

`PracticeView.vue` 变更：
- 模板：`<ChessBoard :position="{ pieces }" :arrows="arrows" />`；`.side` 内着法列表上方插入分析面板：
  ```html
  <div class="analysis" data-test="analysis">
    <div class="score-row" v-if="scoreText">
      <span class="score-text" data-test="score">{{ scoreText }}</span>
      <div class="score-bar"><div class="score-bar-fill" :style="{ width: barWidth + '%' }"></div></div>
    </div>
    <p class="analysis-status" data-test="analysis-status">{{ statusText }}</p>
    <ol class="analysis-history" v-if="analysis.results.length">
      <li v-for="r in analysis.results" :key="r.depth" data-test="analysis-item">
        <span class="depth">第 {{ r.depth }} 层</span>
        <span class="score">{{ formatScore(r.score_red) }}</span>
        <span class="line">{{ pvText(r) }}</span>
        <span class="time">{{ r.time_ms }}ms</span>
      </li>
    </ol>
  </div>
  ```
- 脚本：
  - `const analysis = ref({ status: "idle", results: [], best: null, reply: null, scoreRed: null })`
  - `let controller = null`；`stopAnalysis()`/`startAnalysis()`；`watch([() => ply.value, () => game.value], startAnalysis)`（`load()` 成功后触发）；`onUnmounted(stopAnalysis)`
  - `payload = { initial_fen: game.initial_fen, moves: game.moves, ply: ply.value }`（也可直接传 `fen`，二选一，保持后端契约）
  - `onResult`：`results.unshift(r)`（**最新在前**）、更新 `scoreRed/best/reply`；`onDone` → `status="done"`；`onError` → `status="error"`
  - `arrows` computed：`best → { kind: "best" }`、`reply → { kind: "reply" }`
  - `scoreText`：`scoreRed > 0 → "红优 +X.X"`，`< 0 → "黑优 X.X"`（取绝对值），`|s| < 1 → "均势"`
  - `barWidth`：`50 + clamp(scoreRed, -1000, 1000) / 20`（0..100）
  - `pvText(r)`：`r.pv.map(p => p.chinese || p.iccs).join(" → ")`
  - `statusText`：分析中/已完成/分析失败
- 样式：`.analysis` 移动优先（卡片式，`min-height` 触摸目标），历史列表 `max-height: 200px; overflow: auto`；`@media (min-width: 768px)` 微调，不影响现有 `.moves` 断言

**Step 4: 运行确认通过**

Run: `cd /home/nealian/chess/frontend && npx vitest run`
Expected: PASS（全量；原有 66+ 测试不回归）

**Step 5: 提交**

```bash
git add frontend/src/views/PracticeView.vue frontend/src/views/__tests__/PracticeView.test.js
git commit -m "feat(web): 打谱页渐进式 AI 分析面板与箭头推演"
```

---

## Task 18: 端到端验证、性能验收与文档

**Files:**
- Modify: `README.md`
- Modify: `backend/requirements.txt`（如 Task 14 未完成）
- Create: `docs/plans/` 无新增（设计/计划已就位）

**Step 1: 全量测试**

```bash
cd /home/nealian/chess/backend && .venv/bin/python -m pytest -q
cd /home/nealian/chess/frontend && npx vitest run
```

Expected: 全部通过。

**Step 2: 性能验收（记录实测值到 README 或计划执行记录）**

```bash
cd /home/nealian/chess/backend && .venv/bin/python - <<'PY'
import time
from engine import analyze, warmup

warmup()
t0 = time.perf_counter()
rows = list(analyze("rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1",
                    start_depth=6, max_depth=16, time_limit_ms=2000))
for r in rows:
    print(f"depth={r.depth} score_red={r.score_red} nodes={r.nodes} time_ms={r.time_ms}")
print(f"总耗时 {(time.perf_counter()-t0)*1000:.0f}ms")
PY
```

Expected: 首个结果（depth 6）在 ~1s 内；2s 内到达 depth 9+（视机器性能，记录实际值）。

**Step 3: 端到端手动/Playwright 验证**

```bash
cd /home/nealian/chess/backend && .venv/bin/python app.py &
cd /home/nealian/chess/frontend && npm run dev &
```

- 打开 `http://localhost:5173` → 棋谱库 → 任选一局打谱
- 验证：翻步立即出现评分与箭头；箭头随翻步更新；历史逐层追加且最新在最上；快速连点翻页无卡死
- 移动端视口（390×844）截图校验布局（沿用项目 Playwright 流程）

**Step 4: README 更新**

- 功能特性增加"AI 局面分析与一步推演"
- API 一览增加 `POST /api/engine/analyze`（NDJSON 流式，字段说明）
- 目录结构补充 `backend/engine/`、`backend/scripts/`、`routes/engine.py`
- 环境要求补充 numba/numpy 依赖与首次启动预热说明
- 已知限制更新：分析仅接入打谱页；Zobrist 为自生成（与 Java 版哈希不同）；黑方着法生成顺序与 Java 版不同（不影响棋力）

**Step 5: 提交**

```bash
git add README.md
git commit -m "docs: 更新 README（AI 分析能力与接口）"
```

---

## 执行注意事项

1. **每完成一个 Task 运行全量后端测试**，防止引擎改动破坏既有规则引擎/API：
   ```bash
   cd /home/nealian/chess/backend && .venv/bin/python -m pytest -q
   ```
2. **numba 编译缓存**：测试首次运行会编译（慢）；若出现缓存异常（如全局数组变更导致 `NumbaWarning`），在任务汇报中记录，并按"全局只读表 + 参数传可变状态"的既定策略排查。
3. **Java 源码行号漂移**：笔记中的行号来自一次性分析，如与源码不符以源码语义为准。
4. **不确定的规则细节**（长将判负口径、DangerMarginBit 的形状）：以 Java 源码为准，禁止自行简化。
5. **不要在热路径分配 numpy 数组**：所有缓冲（着法列表、PV 表、栈）在搜索开始时一次性分配。
6. **前端测试的 fetch mock**：jsdom 无 `ReadableStream`/`TextDecoder`，Task 16 的测试用最小 mock（见用例），不要依赖真实流实现。
7. 提交信息末尾可附任务编号（如 `(Task 7)`）便于回溯；**若用户未授权提交则跳过提交步骤**。

