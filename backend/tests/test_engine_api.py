"""Task 13：`POST /api/engine/analyze` NDJSON 流式接口测试。

覆盖：
- `fen` 与 `initial_fen + moves`（含 `ply` 缺省/裁剪）两种局面来源；
- 参数越界夹逼、done 行 reason、PV 至多 2 步与 ICCS/中文记谱；
- 非法 FEN/着法/空请求体走流内 error 行；
- 并发请求由模块级锁串行化（互不干扰）；
- Task 14：等待期间产出 `ping` 保活行；客户端断开（生成器 close）
  立即置位停旗停止后台搜索，后续请求不必等前一次搜完。

首次调用会触发搜索链 numba JIT 编译（约 20-35s，预期内）；
各用例用 `max_depth=4/6` 把搜索耗时控制在亚秒级。
"""

import json
import re
import threading
import time

from chess_engine.board import INITIAL_FEN, Board
from chess_engine.move import Move

ICCS_RE = re.compile(r"^[a-i][0-9][a-i][0-9]$")


def read_stream(client, payload):
    resp = client.post("/api/engine/analyze", json=payload)
    assert resp.status_code == 200
    assert resp.mimetype == "application/x-ndjson"
    return [
        json.loads(line)
        for line in resp.get_data(as_text=True).splitlines()
        if line.strip()
    ]


def _of_type(messages, kind):
    return [message for message in messages if message["type"] == kind]


def _parse_iccs(text):
    def point(part):
        return ord(part[0]) - 97, int(part[1])

    return point(text[:2]), point(text[2:])


def test_analyze_with_fen(client):
    messages = read_stream(
        client,
        {"fen": INITIAL_FEN, "start_depth": 4, "max_depth": 4, "time_limit_ms": 5000},
    )
    results = _of_type(messages, "result")
    assert results and results[-1]["depth"] >= 4
    last = results[-1]
    assert set(last) >= {
        "type",
        "depth",
        "score_red",
        "score_stm",
        "mate",
        "pv",
        "time_ms",
        "nodes",
        "side_to_move",
    }
    assert isinstance(last["score_red"], int)
    assert isinstance(last["score_stm"], int)
    assert last["side_to_move"] in ("red", "black")
    assert last["pv"] and set(last["pv"][0]) >= {
        "x1",
        "y1",
        "x2",
        "y2",
        "iccs",
        "chinese",
    }
    assert ICCS_RE.match(last["pv"][0]["iccs"])
    done = _of_type(messages, "done")
    assert done and done[-1]["depth"] >= 4


def test_analyze_rebuilds_position_from_moves(client):
    moves = [{"x1": 7, "y1": 2, "x2": 4, "y2": 2}]  # 炮二平五
    messages = read_stream(
        client,
        {
            "initial_fen": INITIAL_FEN,
            "moves": moves,
            "ply": 1,
            "start_depth": 4,
            "max_depth": 4,
            "time_limit_ms": 5000,
        },
    )
    results = _of_type(messages, "result")
    assert results
    last = results[-1]
    assert last["side_to_move"] == "black"
    first = last["pv"][0]
    assert first["chinese"]

    # PV 首步为黑方着法：起点棋子属于黑方
    board = Board()
    board.load_fen(INITIAL_FEN)
    board.apply_move(Move(7, 2, 4, 2))
    assert board.side_to_move == "black"
    src, _ = _parse_iccs(first["iccs"])
    piece = board.piece_at(*src)
    assert piece is not None and piece[0] == "black"

    # ply 缺省 = len(moves)：同样重放到黑方走子
    base = {
        "initial_fen": INITIAL_FEN,
        "moves": moves,
        "start_depth": 4,
        "max_depth": 4,
        "time_limit_ms": 5000,
    }
    default_ply = _of_type(read_stream(client, dict(base)), "result")[-1]
    assert default_ply["side_to_move"] == "black"
    # ply=0 表示不重放，仍是红方走子
    zero_ply = _of_type(read_stream(client, dict(base, ply=0)), "result")[-1]
    assert zero_ply["side_to_move"] == "red"


def test_analyze_bad_fen_returns_error_line(client):
    messages = read_stream(client, {"fen": "not-a-fen"})
    assert len(messages) == 1
    assert messages[0]["type"] == "error"
    assert messages[0]["message"]


def test_analyze_invalid_move_returns_error_line(client):
    messages = read_stream(
        client,
        {
            "initial_fen": INITIAL_FEN,
            "moves": [{"x1": 0, "y1": 9, "x2": 0, "y2": 8}],  # 黑车着法，红方轮走
            "ply": 1,
        },
    )
    assert messages[0]["type"] == "error"
    assert messages[0]["message"]


def test_analyze_requires_input(client):
    messages = read_stream(client, {})
    assert messages[0]["type"] == "error"


def test_analyze_clamps_parameters(client):
    # start_depth=99 被钳到 16 并不超过 max_depth；time_limit=999999 钳到 30000。
    # 用 max_depth=6 限制时长，done 由 max_depth 触发（而非 time_limit）。
    messages = read_stream(
        client,
        {
            "fen": INITIAL_FEN,
            "start_depth": 99,
            "max_depth": 6,
            "time_limit_ms": 999999,
        },
    )
    results = _of_type(messages, "result")
    assert results and results[-1]["depth"] <= 16
    done = _of_type(messages, "done")[-1]
    assert done["reason"] == "max_depth"

    # `start_depth=Infinity`（Python `json.dumps` 默认 allow_nan=True 的字面量）
    # 回退默认值而非流内 error：与 threads 的 Infinity 用例属同一健壮性变更。
    messages = read_stream(
        client,
        {
            "fen": INITIAL_FEN,
            "start_depth": float("inf"),
            "max_depth": 6,
            "time_limit_ms": 5000,
        },
    )
    assert not _of_type(messages, "error")
    assert _of_type(messages, "result")


def test_analyze_pv_has_at_most_two_moves(client):
    messages = read_stream(
        client,
        {"fen": INITIAL_FEN, "start_depth": 4, "max_depth": 4, "time_limit_ms": 5000},
    )
    result = _of_type(messages, "result")[-1]
    assert 1 <= len(result["pv"]) <= 2


def test_analyze_done_reason(client):
    messages = read_stream(
        client,
        {"fen": INITIAL_FEN, "start_depth": 4, "max_depth": 4, "time_limit_ms": 5000},
    )
    done = _of_type(messages, "done")[-1]
    assert done["reason"] == "max_depth"
    assert done["depth"] >= 4

    # max_depth 未到、时限先到 → time_limit
    messages = read_stream(
        client,
        {"fen": INITIAL_FEN, "start_depth": 4, "max_depth": 16, "time_limit_ms": 100},
    )
    done = _of_type(messages, "done")[-1]
    assert done["reason"] == "time_limit"


def test_analyze_concurrent_lock(app):
    done_lines = []
    failures = []

    def worker():
        try:
            client = app.test_client()
            messages = read_stream(
                client,
                {
                    "fen": INITIAL_FEN,
                    "start_depth": 4,
                    "max_depth": 4,
                    "time_limit_ms": 5000,
                },
            )
            done_lines.append(_of_type(messages, "done")[-1])
        except Exception as exc:  # noqa: BLE001 - 线程内异常带回主线程断言
            failures.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not failures
    assert len(done_lines) == 2
    assert all(done["depth"] >= 4 for done in done_lines)


def test_ping_rows_during_wait(client):
    # max_depth=6 单次请求通常跨过 0.3s 的 ping 周期；允许不出现 ping，
    # 但出现时必须形如 {"type": "ping", "elapsed_ms": int} 且可被解析器忽略。
    messages = read_stream(
        client,
        {
            "fen": INITIAL_FEN,
            "start_depth": 4,
            "max_depth": 6,
            "time_limit_ms": 1500,
        },
    )
    for ping in _of_type(messages, "ping"):
        assert set(ping) == {"type", "elapsed_ms"}
        assert isinstance(ping["elapsed_ms"], int) and not isinstance(
            ping["elapsed_ms"], bool
        )
        assert ping["elapsed_ms"] >= 0

    results = _of_type(messages, "result")
    assert results and results[-1]["depth"] >= 4
    assert _of_type(messages, "done")


def test_client_disconnect_stops_analysis(client):
    # 先跑一次完整分析，确保 numba JIT 缓存就绪，计时断言只反映中断语义。
    read_stream(
        client,
        {"fen": INITIAL_FEN, "start_depth": 4, "max_depth": 4, "time_limit_ms": 1000},
    )

    resp = client.post(
        "/api/engine/analyze",
        json={
            "fen": INITIAL_FEN,
            "start_depth": 4,
            "max_depth": 16,
            "time_limit_ms": 10000,
        },
    )
    assert resp.status_code == 200
    # 只读第一行就关闭响应：模拟 WSGI 服务器发现客户端断开后 close 生成器。
    first_line = next(iter(resp.response), None)
    assert first_line
    resp.close()

    # 断开应立即置位停旗：第二个请求无需等第一次搜完，短时内完成。
    started = time.perf_counter()
    messages = read_stream(
        client,
        {"fen": INITIAL_FEN, "start_depth": 4, "max_depth": 4, "time_limit_ms": 1000},
    )
    elapsed = time.perf_counter() - started

    assert _of_type(messages, "done")
    assert elapsed < 10, f"断开后第二个请求耗时 {elapsed:.1f}s，搜索未被中断"


def test_concurrent_requests_are_serialized(app):
    # 模块级锁串行化：两次搜索不重叠，后完成者与先完成者的结束时刻之差
    # 约为一次完整搜索的耗时；若锁失效（并行）该差值趋近 0。
    # 先单独预热，避免 numba 首次 JIT 编译（不可中断）+ 排队干扰计时。
    hot = app.test_client()
    read_stream(
        hot,
        {"fen": INITIAL_FEN, "start_depth": 4, "max_depth": 4, "time_limit_ms": 1000},
    )

    completions = []
    failures = []
    barrier = threading.Barrier(2)

    def worker():
        try:
            client = app.test_client()
            barrier.wait(timeout=10)
            started = time.perf_counter()
            messages = read_stream(
                client,
                {
                    "fen": INITIAL_FEN,
                    "start_depth": 4,
                    "max_depth": 4,
                    "time_limit_ms": 5000,
                },
            )
            assert _of_type(messages, "done")
            completions.append((time.perf_counter(), time.perf_counter() - started))
        except Exception as exc:  # noqa: BLE001 - 线程内异常带回主线程断言
            failures.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert not failures
    assert len(completions) == 2
    completions.sort()
    first_end, first_duration = completions[0]
    second_end, second_duration = completions[1]
    assert second_end - first_end >= min(first_duration, second_duration) * 0.5


def test_analyze_threads_parameter(client):
    messages = read_stream(
        client,
        {
            "fen": INITIAL_FEN,
            "start_depth": 4,
            "max_depth": 4,
            "time_limit_ms": 5000,
            "threads": 2,
        },
    )
    assert _of_type(messages, "done")[0]["reason"] == "max_depth"


def test_analyze_threads_clamped_and_optional(client):
    # 越界夹逼不报错；非法类型与缺失时回退自动（测试环境 env=1）
    for threads in (999, "abc", None):
        payload = {
            "fen": INITIAL_FEN,
            "start_depth": 4,
            "max_depth": 4,
            "time_limit_ms": 5000,
        }
        if threads is not None:
            payload["threads"] = threads
        messages = read_stream(client, payload)
        assert _of_type(messages, "result")


def test_analyze_threads_infinity_falls_back(client):
    # JSON `Infinity` 解析为 float('inf')：不得抛错（_clamp_int 需捕获 OverflowError）。
    # 该字面量主要来自 Python 生态客户端：`json.dumps`（默认 allow_nan=True）
    # 会产出 `Infinity`，Flask/标准库 json 接受；浏览器 `JSON.stringify(Infinity)`
    # 产出 `null`，不会到达此处。
    messages = read_stream(
        client,
        {
            "fen": INITIAL_FEN,
            "start_depth": 4,
            "max_depth": 4,
            "time_limit_ms": 5000,
            "threads": float("inf"),
        },
    )
    assert _of_type(messages, "result")
