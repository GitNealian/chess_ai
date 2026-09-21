"""引擎分析 NDJSON 流式接口（Task 13/14）。

`POST /api/engine/analyze`：接收 FEN，或 `initial_fen + moves + ply` 重放
得到局面，以 `application/x-ndjson` 逐行输出：

- `{"type": "result", ...}`：`depth >= start_depth` 的每完成一层；
- `{"type": "ping", "elapsed_ms": ...}`：等待搜索事件的保活行，约每 0.3s
  一条（前端与既有解析器应忽略未知 `type`）；
- `{"type": "done", ...}`：正常结束，含 `depth` / `time_ms` / `reason`；
- `{"type": "error", "message": ...}`：参数、FEN 或着法错误（流内错误行，
  客户端只需处理一种错误路径；仅 Content-Type 非 JSON、body 非对象时
  在流开始前返回 400 JSON）。

并发与中断（Task 14）：
- 模块级 `threading.Lock` 串行化整个分析过程（单用户场景），第二个请求
  排队等待；
- 搜索在工作线程（daemon，`engine-analyze`）中执行，主生成器只从事件
  队列转发结果；主生成器每 `PING_INTERVAL_S` 秒至少 yield 一次保活行，
  让 WSGI 服务器在写失败时能及时 `close` 生成器（真实客户端断开检测的
  关键）；生成器 `finally` 置位停旗，配合 nogil 搜索在毫秒级退出。
- `time_limit_ms` 是**层边界软时限**：完成一层后按累计耗时检查，并按
  「上一层耗时 × 1.5」外推下一层预算，预判超支即不再开始下一层（done 的
  `reason` 仍为 `time_limit`）；不保证在时限到达时立即返回；客户端断开后
  则在下一个 ping 周期内停止搜索并释放锁。
"""

import json
import queue
import threading
import time

import numpy as np
from flask import Blueprint, Response, jsonify, request, stream_with_context

from chess_engine.board import INITIAL_FEN, Board
from chess_engine.move import Move
from chess_engine.notation import move_to_chinese
from engine import analyze
from engine import constants as EC

engine_bp = Blueprint("engine", __name__)

# 整个分析过程（含流式产出）持锁：第二个请求排队等待。
_ANALYZE_LOCK = threading.Lock()

# 保活行间隔（秒）：等待事件超时即产出 ping，为 WSGI 服务器提供
# 周期性写机会以检测客户端断开。
PING_INTERVAL_S = 0.3

# 参数范围：越界夹逼而非报错，缺省用引擎默认值。
MIN_DEPTH = EC.ROOT_START_DEPTH  # 4
MAX_DEPTH = 16
MIN_TIME_LIMIT_MS = 100
MAX_TIME_LIMIT_MS = 30000

# 对外的 PV 长度（当前方最佳着法 + 对方应着）。
PV_LIMIT = 2

_SIDE_NAMES = {EC.RED: "red", EC.BLACK: "black"}


class _RequestError(Exception):
    """请求参数错误（转为流内 error 行）。"""


def _encode(payload):
    return json.dumps(payload, ensure_ascii=False) + "\n"


def _clamp_int(raw, default, minimum, maximum):
    if raw is None or isinstance(raw, bool):
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, value))


def _valid_move_dict(raw):
    if not isinstance(raw, dict):
        return False
    keys = ("x1", "y1", "x2", "y2")
    return all(
        isinstance(raw.get(key), int) and not isinstance(raw.get(key), bool)
        for key in keys
    )


def _load_board(fen, label):
    board = Board()
    try:
        board.load_fen(fen)
    except ValueError as exc:
        raise _RequestError(f"{label} 无效：{exc}") from exc
    return board


def _resolve_fen(data):
    """把请求体规范化为引擎可用的 FEN；非法输入抛 `_RequestError`。"""
    if "fen" in data:
        raw_fen = data["fen"]
        if not isinstance(raw_fen, str) or not raw_fen.strip():
            raise _RequestError("fen 必须是非空字符串")
        return _load_board(raw_fen, "FEN").to_fen()

    if "initial_fen" not in data and "moves" not in data:
        raise _RequestError("缺少局面：请提供 fen，或 initial_fen + moves")

    initial_fen = data.get("initial_fen", INITIAL_FEN)
    if not isinstance(initial_fen, str):
        raise _RequestError("initial_fen 必须是字符串")
    moves = data.get("moves", [])
    if not isinstance(moves, list):
        raise _RequestError("moves 必须是数组")
    ply = data.get("ply", len(moves))
    if isinstance(ply, bool) or not isinstance(ply, int):
        raise _RequestError("ply 必须是整数")
    if ply < 0 or ply > len(moves):
        raise _RequestError(f"ply 超出范围：0..{len(moves)}")

    board = _load_board(initial_fen, "initial_fen")
    for index, raw in enumerate(moves[:ply], start=1):
        if not _valid_move_dict(raw):
            raise _RequestError(f"第 {index} 步着法格式错误")
        move = Move.from_dict(raw)
        piece = board.piece_at(move.x1, move.y1)
        if piece is None or piece[0] != board.side_to_move:
            raise _RequestError(f"第 {index} 步不是合法着法")
        if move not in board.pseudo_moves_from(move.x1, move.y1):
            raise _RequestError(f"第 {index} 步不是合法着法")
        board.apply_move(move)
    return board.to_fen()


def _move_to_xy(packed):
    packed = int(packed)
    x1, y1 = EC.site_to_xy(packed & 127)
    x2, y2 = EC.site_to_xy(packed >> 7)
    return x1, y1, x2, y2


def _pv_payload(pv, base_board):
    """PV 前 `PV_LIMIT` 步转坐标 + ICCS + 中文记谱（失败回退 ICCS）。"""
    items = []
    board = base_board.clone()
    for packed in pv[:PV_LIMIT]:
        x1, y1, x2, y2 = _move_to_xy(packed)
        move = Move(x1, y1, x2, y2)
        iccs = f"{chr(97 + x1)}{y1}{chr(97 + x2)}{y2}"
        chinese = iccs
        if board is not None:
            try:
                chinese = move_to_chinese(board, move)
            except ValueError:
                chinese = iccs
            try:
                board.apply_move(move)
            except ValueError:
                board = None
        items.append(
            {
                "x1": x1,
                "y1": y1,
                "x2": x2,
                "y2": y2,
                "iccs": iccs,
                "chinese": chinese,
            }
        )
    return items


def _done_reason(last, max_depth, time_limit_ms, stop):
    if last is None:
        return "stop" if stop[0] != 0 else "max_depth"
    if last.depth >= max_depth:
        return "max_depth"
    if last.time_ms >= time_limit_ms:
        return "time_limit"
    if stop[0] != 0:
        return "stop"
    # last.depth < max_depth 且累计耗时未到时限，只可能是「时间预算外推」
    # 预判下一层超支而提前停止（见 analysis.analyze），故仍为 time_limit。
    return "time_limit"


@engine_bp.post("/analyze")
def analyze_position():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "请求体必须是 JSON 对象"}), 400

    def generate():
        try:
            fen = _resolve_fen(data)
            start_depth = _clamp_int(
                data.get("start_depth"),
                EC.DEFAULT_START_DEPTH,
                MIN_DEPTH,
                MAX_DEPTH,
            )
            max_depth = _clamp_int(
                data.get("max_depth"),
                EC.DEFAULT_MAX_DEPTH,
                MIN_DEPTH,
                MAX_DEPTH,
            )
            # 保证至少有一层产出（夹逼语义的一部分）。
            start_depth = min(start_depth, max_depth)
            time_limit_ms = _clamp_int(
                data.get("time_limit_ms"),
                EC.DEFAULT_TIME_LIMIT_MS,
                MIN_TIME_LIMIT_MS,
                MAX_TIME_LIMIT_MS,
            )
            base_board = Board().load_fen(fen)
        except Exception as exc:  # noqa: BLE001 - 兜底转流内 error 行
            yield _encode({"type": "error", "message": str(exc)})
            return

        stop = np.zeros(1, dtype=np.int8)
        events = queue.Queue()

        def worker():
            try:
                for result in analyze(
                    fen,
                    start_depth=start_depth,
                    max_depth=max_depth,
                    time_limit_ms=time_limit_ms,
                    stop=stop,
                ):
                    events.put(("result", result))
                events.put(("done", None))
            except Exception as exc:  # noqa: BLE001 - 转流内 error 行
                events.put(("error", exc))

        with _ANALYZE_LOCK:
            t0 = time.perf_counter()
            threading.Thread(
                target=worker, name="engine-analyze", daemon=True
            ).start()
            last = None
            try:
                while True:
                    try:
                        kind, payload = events.get(timeout=PING_INTERVAL_S)
                    except queue.Empty:
                        # 保活：让主生成器周期性 yield，WSGI 服务器才能
                        # 在写失败时 close 本生成器（进而置位停旗）。
                        yield _encode(
                            {
                                "type": "ping",
                                "elapsed_ms": int(
                                    (time.perf_counter() - t0) * 1000
                                ),
                            }
                        )
                        continue
                    if kind == "result":
                        last = payload
                        yield _encode(
                            {
                                "type": "result",
                                "depth": last.depth,
                                "score_red": last.score_red,
                                "score_stm": last.score_stm,
                                "mate": last.mate,
                                "pv": _pv_payload(last.pv, base_board),
                                "time_ms": last.time_ms,
                                "nodes": last.nodes,
                                "side_to_move": _SIDE_NAMES[last.side_to_move],
                            }
                        )
                    elif kind == "done":
                        yield _encode(
                            {
                                "type": "done",
                                "depth": last.depth if last is not None else 0,
                                "time_ms": int((time.perf_counter() - t0) * 1000),
                                "reason": _done_reason(
                                    last, max_depth, time_limit_ms, stop
                                ),
                            }
                        )
                        break
                    else:
                        yield _encode({"type": "error", "message": str(payload)})
                        break
            finally:
                # 生成器 close（客户端断开）或正常结束时立即停止后台搜索；
                # 工作线程为 daemon，置位后自行在毫秒级退出，无需 join。
                stop[0] = 1

    return Response(stream_with_context(generate()), mimetype="application/x-ndjson")
