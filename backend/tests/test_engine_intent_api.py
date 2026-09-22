"""POST /api/engine/intent 端点测试（NDJSON 流式）。

事件序列 = intent_events 原样转发 + done/error；并发与 /analyze 互斥
（共用 _ANALYZE_LOCK）。首次运行含 numba JIT 预热（app 启动时后台触发，
测试进程内首个引擎请求约 20-35s）。
"""

import json
import time

from routes import engine as routes_engine

INITIAL = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"


def _post_intent(client, payload):
    resp = client.post("/api/engine/intent", json=payload)
    assert resp.status_code == 200
    assert resp.mimetype == "application/x-ndjson"
    return [
        json.loads(line)
        for line in resp.get_data(as_text=True).splitlines()
        if line.strip()
    ]


def test_intent_stream_event_sequence(client):
    events = _post_intent(
        client, {"fen": INITIAL, "max_baits": 1, "time_limit_ms": 5000}
    )
    # ping 保活行可在任意位置出现（JIT 预热或 rank 计算超过 0.3s 的
    # ping 周期时先产出），解析器应忽略：剥离 ping 后校验事件序列。
    substantive = [e for e in events if e["type"] != "ping"]
    kinds = [e["type"] for e in substantive]
    assert kinds[0] == "rank"
    assert "threat" in kinds
    assert kinds[-1] == "done"
    assert not any(e["type"] == "error" for e in events)
    rank = next(e for e in substantive if e["type"] == "rank")
    assert rank["best"]["chinese"] != ""
    done = events[-1]  # done 后 break，ping 不会再出现
    assert isinstance(done["time_ms"], int)


def test_intent_invalid_fen_yields_error_event(client):
    events = _post_intent(client, {"fen": "not-a-fen"})
    assert any(e["type"] == "error" for e in events)


def test_intent_requires_json_object(client):
    resp = client.post("/api/engine/intent")
    assert resp.status_code == 400


def test_intent_param_clamping(client):
    events = _post_intent(
        client, {"fen": INITIAL, "max_baits": 99, "time_limit_ms": 1}
    )
    baits = [e for e in events if e["type"] == "bait"]
    assert len(baits) <= 3  # 夹逼到 1..3
    # time_limit_ms=1 被夹逼到 500：各线最多 500ms，不失控
    assert any(e["type"] == "rank" for e in events)  # 夹逼到 500ms 才有 rank 事件；失效则空流


def test_intent_client_disconnect_releases_lock(client):
    # 先跑一次完整流，确保 numba JIT 缓存就绪，计时断言只反映中断语义。
    _post_intent(client, {"fen": INITIAL, "max_baits": 1, "time_limit_ms": 5000})

    resp = client.post(
        "/api/engine/intent", json={"fen": INITIAL, "time_limit_ms": 5000}
    )
    assert resp.status_code == 200
    # 只读首块就关闭响应：模拟 WSGI 服务器发现客户端断开后 close 生成器
    # （写法同 test_engine_api.test_client_disconnect_stops_analysis）。
    first_line = next(iter(resp.response), None)
    assert first_line
    resp.close()

    # 断开后生成器 finally 置位停旗并释放 _ANALYZE_LOCK：第二个请求无需
    # 等第一次推演跑完，短时内完成（实测约 1s；上限 10s 与 /analyze 的
    # 同类用例口径一致）。残留 worker 不持锁，至多再跑完当前推演线。
    started = time.perf_counter()
    events = _post_intent(
        client, {"fen": INITIAL, "max_baits": 1, "time_limit_ms": 5000}
    )
    elapsed = time.perf_counter() - started

    assert any(e["type"] == "done" for e in events)
    assert elapsed < 10, f"断开后第二个请求耗时 {elapsed:.1f}s，锁未被释放"


def test_intent_ping_rows_between_events(client, monkeypatch):
    # 预热（JIT）后再调小保活周期，避免预热期产出海量 ping 行。
    _post_intent(client, {"fen": INITIAL, "max_baits": 1, "time_limit_ms": 5000})

    # 把保活间隔压到 1ms 锁定「ping 夹在事件之间」：各线搜索（毫秒级以上）
    # 的等待期必产出 ping。test_engine_api.py 无 PING_INTERVAL_S patch 的
    # 既有模式，此处为 pytest 标准 monkeypatch.setattr。
    monkeypatch.setattr(routes_engine, "PING_INTERVAL_S", 0.001)
    events = _post_intent(
        client, {"fen": INITIAL, "max_baits": 1, "time_limit_ms": 5000}
    )

    # 结构断言照抄 test_engine_api.test_ping_rows_during_wait：可被解析器忽略。
    pings = [e for e in events if e["type"] == "ping"]
    assert pings  # 1ms 周期下流中必有 ping
    for ping in pings:
        assert set(ping) == {"type", "elapsed_ms"}
        assert isinstance(ping["elapsed_ms"], int) and not isinstance(
            ping["elapsed_ms"], bool
        )
        assert ping["elapsed_ms"] >= 0

    # 存在某条 ping 位于 rank 与下一个实质事件之间（等待 threat 计算的保活）。
    rank_idx = next(i for i, e in enumerate(events) if e["type"] == "rank")
    next_sub_idx = rank_idx + 1 + next(
        i for i, e in enumerate(events[rank_idx + 1:]) if e["type"] != "ping"
    )
    assert any(
        rank_idx < i < next_sub_idx
        for i, e in enumerate(events)
        if e["type"] == "ping"
    ), "rank 与后续事件之间未观察到 ping"
