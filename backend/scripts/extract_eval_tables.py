#!/usr/bin/env python3
"""从 Java 源码提取评估表，生成 backend/engine/eval_tables.py。

用法：
    backend/.venv/bin/python backend/scripts/extract_eval_tables.py

数据来源（GBK 编码，按 errors="replace" 读取）：
    $CHESS_JAVA_ROOT/evaluate/EvaluateCompute.java
    $CHESS_JAVA_ROOT/evaluate/EvaluateComputeMiddleGame.java
    $CHESS_JAVA_ROOT/evaluate/EvaluateComputeEndGame.java
默认 $CHESS_JAVA_ROOT=/tmp/opencode/ChineseChess/com/pj/chess。

提取规则：`int[] name = {...}` 与 `int name[] = {...}` 两种声明；
红方位置表 = 黑方位置表行镜像（row ↔ 9-row），与 Tools.exchange 等价。
脚本内置自校验（长度、值域、红黑镜像、源码抽查值），并打印摘要。
"""

import hashlib
import os
import re
import sys
from pathlib import Path

import numpy as np

JAVA_ROOT = Path(
    os.environ.get("CHESS_JAVA_ROOT", "/tmp/opencode/ChineseChess/com/pj/chess")
)
EVALUATE_DIR = JAVA_ROOT / "evaluate"
BASE_FILE = EVALUATE_DIR / "EvaluateCompute.java"
MIDDLE_FILE = EVALUATE_DIR / "EvaluateComputeMiddleGame.java"
END_FILE = EVALUATE_DIR / "EvaluateComputeEndGame.java"
OUTPUT = Path(__file__).resolve().parent.parent / "engine" / "eval_tables.py"

# 位置表按角色顺序：卒/士/象/炮/马/车/将（即 role-8 索引 0..6）
ROLE_ORDER = (
    ("SOLDIER", "blackSoldierAttach"),
    ("GUARD", "GuardAttach"),
    ("ELEPHANT", "ElephantAttch"),
    ("GUN", "blackGunAttach"),
    ("KNIGHT", "blackKnightAttach"),
    ("CHARIOT", "blackChariotAttach"),
    ("KING", "kingAttach"),
)

# 分区代号 → 分区表名（chessRolePartitionSite 的组合方式）
PARTITION_SITE_TABLES = (
    "SoldierPartitionSite",
    "DefensePartitionSite",
    "DefensePartitionSite",
    "GunPartitionSite",
    "KnightPartitionSite",
    "ChariotPartitionSite",
    "KingPartitionSite",
)

# 源码抽查值（前 10 个数字与关键点，人工核对用）
SPOT_CHECKS = {
    "middle": {
        "blackKnightAttach": (
            [-60, -36, -20, -20, -20, -20, -20, -36, -60, -20],
            {13: -70, 40: 60},
        ),
        "blackGunAttach": ([-30, 0, 30, 40, 20, 40, 30, 0, -30, -20], {13: 40}),
        "blackChariotAttach": ([-60, -10, 0, 20, -10, 20, 0, -10, -60, -10], {13: -40}),
        "blackSoldierAttach": ([0] * 10, {40: 35, 49: 110}),
        "ElephantAttch": ([0, 0, 10, 0, 0, 0, 10, 0, 0, 0], {22: 30, 63: -10}),
        "GuardAttach": ([0] * 10, {13: 25, 21: 10}),
        "kingAttach": ([0, 0, 0, 10, 20, 10, 0, 0, 0, 0], {12: -45, 13: -50, 22: -90}),
    },
    "end": {
        "blackKnightAttach": ([0] * 10, {11: 30, 22: 45}),
        "blackGunAttach": ([0, 0, 30, 80, 20, 80, 30, 0, 0, 0], {13: 55}),
        "blackChariotAttach": ([20, 20, 20, 65, 0, 65, 20, 20, 20, 20], {13: 35}),
        "blackSoldierAttach": ([0] * 10, {40: 60, 49: 120}),
        "ElephantAttch": ([0, 0, 10, 0, 0, 0, 10, 0, 0, 0], {2: 10, 22: 30}),
        "GuardAttach": ([0] * 10, {13: 25, 21: 20}),
        "kingAttach": ([0, 0, 0, 10, 10, 10, 0, 0, 0, 0], {13: -20, 22: -50}),
    },
}


# EvaluateCompute 的子力价值常量（chessBaseScore 数组内引用这些标识符）
SUB_MATERIAL_CONSTANTS = {
    "KINGSCORE": 3000,
    "CHARIOTSCORE": 1300,
    "KNIGHTSCORE": 490,
    "GUNSCORE": 610,
    "ELEPHANTSCORE": 200,
    "GUARDSCORE": 200,
    "SOLDIERSCORE": 100,
}


def read_java(path):
    with open(path, "rb") as handle:
        return handle.read().decode("gbk", errors="replace")


def strip_comments(text):
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL)
    return re.sub(r"//[^\n]*", " ", text)


def extract_int_array(text, name, constants=SUB_MATERIAL_CONSTANTS):
    pattern = (
        r"int\s*(?:\[\s*\])*\s*"
        + re.escape(name)
        + r"\s*(?:\[\s*\])*\s*=\s*(?:new\s+int\s*(?:\[\s*\])*\s*)?\{([^{}]*)\}"
    )
    match = re.search(pattern, text, flags=re.DOTALL)
    if match is None:
        raise ValueError(f"未找到数组 {name}")
    body = match.group(1)
    for identifier in sorted(set(re.findall(r"[A-Za-z_]\w*", body))):
        if identifier not in constants:
            raise ValueError(f"数组 {name} 含未识别标识符 {identifier}")
        body = re.sub(rf"\b{identifier}\b", str(constants[identifier]), body)
    return [int(value) for value in re.findall(r"[+-]?\d+", body)]


def row_mirror(values):
    array = np.array(values, dtype=np.int32).reshape(10, 9)
    return np.ascontiguousarray(array[::-1, :]).reshape(-1)


def to_masks(values):
    lo = 0
    hi = 0
    for site, value in enumerate(values):
        if not value:
            continue
        if site < 64:
            lo |= 1 << site
        else:
            hi |= 1 << (site - 64)
    if lo >= 1 << 63:
        lo -= 1 << 64
    return lo, hi


def check_length(values, expected, label):
    if len(values) != expected:
        raise AssertionError(f"{label} 长度 {len(values)} != {expected}")


def check_range(values, label, low=-500, high=500):
    bad = [v for v in values if not low <= v <= high]
    if bad:
        raise AssertionError(f"{label} 值越界：{bad[:8]}")
    return min(values), max(values)


def build_position_tables(text, group):
    """返回 (black int32[7][90], red int32[7][90])；红表由黑表行镜像生成。"""
    black = np.zeros((7, 90), dtype=np.int32)
    for index, (_, java_name) in enumerate(ROLE_ORDER):
        values = extract_int_array(text, java_name)
        check_length(values, 90, java_name)
        check_range(values, java_name)
        head, spots = SPOT_CHECKS[group][java_name]
        if values[:10] != head:
            raise AssertionError(f"{java_name} 前 10 值不符：{values[:10]}")
        for site, want in spots.items():
            if values[site] != want:
                raise AssertionError(f"{java_name}[{site}]={values[site]} != {want}")
        black[index] = values
    red = np.zeros((7, 90), dtype=np.int32)
    for index in range(7):
        red[index] = row_mirror(black[index])
    # 自校验：红表逐项等于黑表行镜像
    for role in range(7):
        for site in range(90):
            row, col = divmod(site, 9)
            assert int(red[role, site]) == int(black[role, (9 - row) * 9 + col])
    return black, red


def format_rows(values, per_row=9):
    """把 90 个数字排成每行 per_row 个；首行以 '[' 开头、末行以 '],' 结尾。"""
    lines = []
    for start in range(0, len(values), per_row):
        chunk = ", ".join(str(int(v)) for v in values[start : start + per_row])
        prefix = "[" if start == 0 else " "
        suffix = "]," if start + per_row >= len(values) else ","
        lines.append(f"        {prefix}{chunk}{suffix}")
    return lines


def format_flat(values, per_row=16):
    lines = []
    for start in range(0, len(values), per_row):
        chunk = ", ".join(str(int(v)) for v in values[start : start + per_row])
        lines.append(f"    {chunk},")
    return lines


def render(name, values, dtype, per_row, ndim):
    if ndim == 2:
        body = "\n".join(
            "\n".join(format_rows(list(values[row]), per_row))
            for row in range(values.shape[0])
        )
        return f"{name} = np.array(\n    [\n{body}\n    ],\n    dtype={dtype},\n)"
    body = "\n".join(format_flat(values, per_row))
    return f"{name} = np.array(\n[\n{body}\n], dtype={dtype}\n)"


def render_masks(name, values):
    body = []
    for play in range(2):
        body.append("    [")
        for side in range(3):
            lo, hi = values[play][side]
            body.append(f"        [{lo}, {hi}],")
        body.append("    ],")
    return f"{name} = np.array(\n[\n" + "\n".join(body) + "\n], dtype=np.int64\n)"


def source_sha256(path):
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def main():
    base_text = strip_comments(read_java(BASE_FILE))
    middle_text = strip_comments(read_java(MIDDLE_FILE))
    end_text = strip_comments(read_java(END_FILE))

    base_scores = extract_int_array(base_text, "chessBaseScore")
    check_length(base_scores, 48, "chessBaseScore")
    mobility_rewards = extract_int_array(middle_text, "chessMobilityRewards")
    min_mobility = extract_int_array(middle_text, "chessMinMobility")
    check_length(mobility_rewards, 48, "chessMobilityRewards")
    check_length(min_mobility, 48, "chessMinMobility")

    attack_partition = extract_int_array(base_text, "attackChessPartitionScore")
    defense_partition = extract_int_array(base_text, "defenseChessPartitionScore")
    check_length(attack_partition, 48, "attackChessPartitionScore")
    check_length(defense_partition, 48, "defenseChessPartitionScore")
    guard_elephant_score = extract_int_array(base_text, "guarAndElephantNumScore")
    gun_depend_guard = extract_int_array(base_text, "gunNumScoreDependGuard")
    knight_depend_guard = extract_int_array(base_text, "knightNumScoreDependGuard")
    for name, values in (
        ("guarAndElephantNumScore", guard_elephant_score),
        ("gunNumScoreDependGuard", gun_depend_guard),
        ("knightNumScoreDependGuard", knight_depend_guard),
    ):
        check_length(values, 3, name)

    role_partition = np.zeros((15, 90), dtype=np.int8)
    for role in range(1, 8):
        table_name = PARTITION_SITE_TABLES[role - 1]
        values = extract_int_array(base_text, table_name)
        check_length(values, 90, table_name)
        role_partition[role] = values
        role_partition[role + 7] = values
    if set(np.unique(role_partition).tolist()) - {
        0,
        1,
        2,
        3,
        4,
        5,
        6,
        31,
        32,
        33,
        64,
        65,
        66,
    }:
        raise AssertionError("分区代号值域异常")

    red_attack_left = extract_int_array(base_text, "AttackRedLeftSite")
    red_attack_right = extract_int_array(base_text, "AttackRightSite")
    red_attack_mid = extract_int_array(base_text, "AtackRedMidSite")
    directions = []
    for values in (red_attack_left, red_attack_right, red_attack_mid):
        check_length(values, 90, "AttackDirection")
        directions.append(values)
    black_directions = [row_mirror(values).tolist() for values in directions]
    attack_direction = np.zeros((2, 3, 2), dtype=np.int64)
    defense_direction = np.zeros((2, 3, 2), dtype=np.int64)
    for side in range(3):
        attack_direction[1, side] = to_masks(directions[side])
        attack_direction[0, side] = to_masks(black_directions[side])
        defense_direction[0, side] = to_masks(directions[side])
        defense_direction[1, side] = to_masks(black_directions[side])

    middle_black, middle_red = build_position_tables(middle_text, "middle")
    end_black, end_red = build_position_tables(end_text, "end")

    soldiers_protected = extract_int_array(end_text, "soldiersProtected")
    gun_oppt_not_guard = extract_int_array(end_text, "gunOpptNotGuard")
    knight_oppt_not_guard = extract_int_array(end_text, "knightOpptNotGuard")
    check_length(soldiers_protected, 6, "soldiersProtected")
    for name, values in (
        ("gunOpptNotGuard", gun_oppt_not_guard),
        ("knightOpptNotGuard", knight_oppt_not_guard),
    ):
        check_length(values, 3, name)

    # ---- 摘要与哈希 ----
    digest = hashlib.sha256()
    for tag, array in (
        ("base_scores", np.array(base_scores, dtype=np.int32)),
        ("mobility_rewards", np.array(mobility_rewards, dtype=np.int32)),
        ("min_mobility", np.array(min_mobility, dtype=np.int32)),
        ("attack_partition", np.array(attack_partition, dtype=np.int32)),
        ("defense_partition", np.array(defense_partition, dtype=np.int32)),
        ("guard_elephant_score", np.array(guard_elephant_score, dtype=np.int32)),
        ("gun_depend_guard", np.array(gun_depend_guard, dtype=np.int32)),
        ("knight_depend_guard", np.array(knight_depend_guard, dtype=np.int32)),
        ("middle_black", middle_black),
        ("middle_red", middle_red),
        ("end_black", end_black),
        ("end_red", end_red),
        ("role_partition", role_partition),
        ("attack_direction", attack_direction),
        ("defense_direction", defense_direction),
        ("soldiers_protected", np.array(soldiers_protected, dtype=np.int32)),
        ("gun_oppt_not_guard", np.array(gun_oppt_not_guard, dtype=np.int32)),
        ("knight_oppt_not_guard", np.array(knight_oppt_not_guard, dtype=np.int32)),
    ):
        digest.update(tag.encode())
        digest.update(array.tobytes())
    table_digest = digest.hexdigest()

    print("=== 提取与校验摘要 ===")
    for path in (BASE_FILE, MIDDLE_FILE, END_FILE):
        print(f"  源文件 {path.name}: sha256={source_sha256(path)}")
    for group, black in (("中局", middle_black), ("残局", end_black)):
        for index, (role, java_name) in enumerate(ROLE_ORDER):
            head = ", ".join(str(int(v)) for v in black[index, :10])
            print(f"  {group} {role:8s} {java_name:20s} 前10={head}")
    print(f"  机动性 weights head={mobility_rewards[:8]}")
    print(f"  机动性 min     head={min_mobility[:8]}")
    print(f"  数据摘要 sha256={table_digest}")
    print("  校验：长度/值域/源码抽查值/红黑行镜像 全部通过")

    header = f'''"""自动生成，勿手改；由 backend/scripts/extract_eval_tables.py 从 Java 源码提取。

来源（Java 源码，GBK）：
- {BASE_FILE.name} sha256={source_sha256(BASE_FILE)}
- {MIDDLE_FILE.name} sha256={source_sha256(MIDDLE_FILE)}
- {END_FILE.name} sha256={source_sha256(END_FILE)}
数据摘要 sha256={table_digest}
生成脚本：backend/scripts/extract_eval_tables.py

位置表按角色顺序索引：0=卒/兵、1=士、2=象、3=炮、4=马、5=车、6=将/帅；
MIDDLE_RED / END_RED 由对应黑表行镜像（row ↔ 9-row）生成。
"""

import numpy as np

__all__ = [
    "ATTACK_DIRECTION",
    "ATTACK_PARTITION_SCORE",
    "BASE_SCORES",
    "DEFENSE_DIRECTION",
    "DEFENSE_PARTITION_SCORE",
    "END_BLACK",
    "END_RED",
    "GUARD_ELEPHANT_NUM_SCORE",
    "GUN_NUM_SCORE_DEPEND_GUARD",
    "GUN_OPPT_NOT_GUARD",
    "KNIGHT_NUM_SCORE_DEPEND_GUARD",
    "KNIGHT_OPPT_NOT_GUARD",
    "MIDDLE_BLACK",
    "MIDDLE_RED",
    "MIN_MOBILITY",
    "MOBILITY_REWARDS",
    "ROLE_PARTITION_SITE",
    "SOLDIERS_PROTECTED",
]
'''

    blocks = [
        render("BASE_SCORES", base_scores, "np.int32", 16, 1),
        render("MIDDLE_BLACK", middle_black, "np.int32", 9, 2),
        render("MIDDLE_RED", middle_red, "np.int32", 9, 2),
        render("END_BLACK", end_black, "np.int32", 9, 2),
        render("END_RED", end_red, "np.int32", 9, 2),
        render("MOBILITY_REWARDS", mobility_rewards, "np.int32", 16, 1),
        render("MIN_MOBILITY", min_mobility, "np.int32", 16, 1),
        render("ROLE_PARTITION_SITE", role_partition, "np.int8", 9, 2),
        render("ATTACK_PARTITION_SCORE", attack_partition, "np.int32", 16, 1),
        render("DEFENSE_PARTITION_SCORE", defense_partition, "np.int32", 16, 1),
        render("GUARD_ELEPHANT_NUM_SCORE", guard_elephant_score, "np.int32", 3, 1),
        render("GUN_NUM_SCORE_DEPEND_GUARD", gun_depend_guard, "np.int32", 3, 1),
        render("KNIGHT_NUM_SCORE_DEPEND_GUARD", knight_depend_guard, "np.int32", 3, 1),
        render_masks("ATTACK_DIRECTION", attack_direction),
        render_masks("DEFENSE_DIRECTION", defense_direction),
        render("SOLDIERS_PROTECTED", soldiers_protected, "np.int32", 6, 1),
        render("GUN_OPPT_NOT_GUARD", gun_oppt_not_guard, "np.int32", 3, 1),
        render("KNIGHT_OPPT_NOT_GUARD", knight_oppt_not_guard, "np.int32", 3, 1),
    ]
    freeze_names = [
        "BASE_SCORES",
        "MIDDLE_BLACK",
        "MIDDLE_RED",
        "END_BLACK",
        "END_RED",
        "MOBILITY_REWARDS",
        "MIN_MOBILITY",
        "ROLE_PARTITION_SITE",
        "ATTACK_PARTITION_SCORE",
        "DEFENSE_PARTITION_SCORE",
        "GUARD_ELEPHANT_NUM_SCORE",
        "GUN_NUM_SCORE_DEPEND_GUARD",
        "KNIGHT_NUM_SCORE_DEPEND_GUARD",
        "ATTACK_DIRECTION",
        "DEFENSE_DIRECTION",
        "SOLDIERS_PROTECTED",
        "GUN_OPPT_NOT_GUARD",
        "KNIGHT_OPPT_NOT_GUARD",
    ]
    freeze = (
        "\nfor _table in (\n"
        + "".join(f"    {name},\n" for name in freeze_names)
        + "):\n    _table.setflags(write=False)\ndel _table\n"
    )

    OUTPUT.write_text(
        header + "\n\n" + "\n\n\n".join(blocks) + "\n\n\n" + freeze, encoding="utf-8"
    )
    print(f"已写入 {OUTPUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
