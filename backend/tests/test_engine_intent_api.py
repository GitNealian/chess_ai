"""POST /api/engine/intent 端点测试（NDJSON 流式）。

事件序列 = intent_events 原样转发 + done/error；并发与 /analyze 互斥
（共用 _ANALYZE_LOCK）。首次运行含 numba JIT 预热（app 启动时后台触发，
测试进程内首个引擎请求约 20-35s）。
"""

import json

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
