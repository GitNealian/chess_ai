#!/usr/bin/env python3
"""引擎搜索基准：固定局面下测量指定深度的耗时、加速比与 NPS。

用法：
    .venv/bin/python scripts/bench_engine.py
    .venv/bin/python scripts/bench_engine.py --depths 8,10 --threads 1,4,8 --repeats 3
    .venv/bin/python scripts/bench_engine.py --depths 10 --threads 8 \
        --hash-sizes 524288,1048576,2097152,4194304

口径：
- 先 `warmup()` 完成 JIT 编译，再逐档测量；
- 每档重复 `--repeats` 次，报告耗时中位数与最小值（加速比按中位数）；
- `nodes` 只统计主线程（并行时辅助线程不计数），因此并行档的 NPS
  只用于同档纵向对比，不代表总吞吐；
- `--hash-sizes` 为置换表槽数（2 的幂），缺省用引擎默认（`search.N`）。

已测结论（2026-09-22，初始局面 depth 10，nproc=20）：
- 扩容置换表无实质收益，默认 `N = 1 << 19` 保持：串行档 2^19 最快
  （26.8s；2^20/2^21/2^22 均 33s+、节点数反而多约 20%——槽映射变化改变
  搜索路径，无单调关系）；并行档（8 线程）2^19 与 2^21 的最快耗时基本
  相同（9.50s vs 9.37s），中位数差异属噪声。
"""

import argparse
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine import analyze, warmup

INITIAL_FEN = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"


def parse_int_list(raw):
    return [int(part) for part in raw.split(",") if part.strip()]


def _run_once(fen, depth, threads, time_limit_ms, hash_size):
    t0 = time.perf_counter()
    results = list(
        analyze(
            fen,
            start_depth=depth,
            max_depth=depth,
            time_limit_ms=time_limit_ms,
            threads=threads,
            hash_size=hash_size,
        )
    )
    elapsed = time.perf_counter() - t0
    if not results:
        return elapsed, 0, None
    last = results[-1]
    return elapsed, int(last.nodes), int(last.score_red)


def main():
    parser = argparse.ArgumentParser(description="引擎搜索基准")
    parser.add_argument("--fen", default=INITIAL_FEN, help="待测局面 FEN")
    parser.add_argument("--depths", default="8,10", help="深度列表，逗号分隔")
    parser.add_argument("--threads", default="1,2,4,8", help="线程数列表，逗号分隔")
    parser.add_argument(
        "--hash-sizes",
        default="",
        help="置换表槽数列表（2 的幂），逗号分隔；缺省用引擎默认",
    )
    parser.add_argument("--repeats", type=int, default=3, help="每档重复次数")
    parser.add_argument(
        "--time-limit-ms", type=int, default=60000, help="单次分析时限（毫秒）"
    )
    args = parser.parse_args()

    depths = parse_int_list(args.depths)
    threads_list = parse_int_list(args.threads)
    hash_sizes = parse_int_list(args.hash_sizes) or [None]

    print(
        f"cpus={os.cpu_count()} repeats={args.repeats} "
        f"time_limit_ms={args.time_limit_ms}"
    )
    warmup()

    for hash_size in hash_sizes:
        label = "default" if hash_size is None else str(hash_size)
        print(f"\n== hash_size={label} ==")
        for depth in depths:
            baseline = None
            for threads in threads_list:
                times = []
                nodes = 0
                score = None
                for _ in range(args.repeats):
                    elapsed, nodes, score = _run_once(
                        args.fen, depth, threads, args.time_limit_ms, hash_size
                    )
                    times.append(elapsed)
                median = statistics.median(times)
                if baseline is None:
                    baseline = median
                nps = int(nodes / median) if median > 0 else 0
                speedup = baseline / median if median > 0 else 0.0
                print(
                    f"depth={depth} threads={threads} "
                    f"median={median:.2f}s min={min(times):.2f}s "
                    f"speedup={speedup:.2f}x nodes={nodes} nps={nps} "
                    f"score={score}"
                )


if __name__ == "__main__":
    main()
