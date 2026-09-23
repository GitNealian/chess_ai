#!/usr/bin/env python3
"""校正 xqipu 导出的 PGN：修正 FEN 行棋方标记，并剔除源数据错误的棋谱。

xqipu 部分古谱的 FEN 把行棋方标错（标红先，实际黑先）。本脚本用规则引擎
试走着法，自动判定正确的行棋方并重建 PGN；对无法走通的棋谱单独输出。

用法：
    python scripts/fix_xqipu_pgn.py 输入.pgns 输出.pgns --bad 坏局.pgns
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from chess_engine.board import Board  # noqa: E402
from chess_engine.parser import parse_iccs  # noqa: E402
from scripts.download_xqipu import build_pgn  # noqa: E402

HEADER_RE = re.compile(r'^\[(\w+)\s+"(.*)"\]$', re.M)
MOVE_RE = re.compile(r"[A-Ia-i][0-9]-[A-Ia-i][0-9]")


def split_games(text):
    return ["[Game " + part for part in text.split("[Game ") if part.strip()]


def playable(fen_body, moves, side):
    board = Board.initial()
    try:
        if fen_body:
            board.load_fen(f"{fen_body} {side}")
        for token in moves:
            move = parse_iccs(token)
            if not board.is_legal(move):
                return False
            board.apply_move(move)
        return True
    except Exception:  # noqa: BLE001 - 任何解析/规则异常都视为不可走
        return False


def fix_game(game):
    headers = dict(HEADER_RE.findall(game))
    body = game.split('[Format "ICCS"]', 1)[-1]
    moves = [token.replace("-", "").lower() for token in MOVE_RE.findall(body)]
    fen = headers.get("FEN", "").strip()

    if fen:
        parts = fen.rsplit(" ", 1)
        fen_body = parts[0]
        side = parts[1] if len(parts) == 2 and parts[1] in ("w", "b") else "w"
    else:
        fen_body, side = "", "w"

    status = "ok"
    if not playable(fen_body, moves, side):
        alt = "b" if side == "w" else "w"
        if fen_body and playable(fen_body, moves, alt):
            side, status = alt, "fixed"
        else:
            return None, "unfixable"

    qipu = {
        "title": headers.get("Title", ""),
        "event": headers.get("Event", ""),
        "red": headers.get("Red", ""),
        "red_team": headers.get("RedTeam", ""),
        "black": headers.get("Black", ""),
        "black_team": headers.get("BlackTeam", ""),
        "opening": headers.get("Opening", ""),
        "日期": headers.get("Date", ""),
        "site": headers.get("Site", ""),
        "round": headers.get("Round", ""),
        "result": headers.get("Result", ""),
        "fen": f"{fen_body} {side}" if fen_body else "",
        "moves": "".join(moves),
    }
    return build_pgn(qipu), status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("src", help="输入 .pgns")
    parser.add_argument("dst", help="输出 .pgns")
    parser.add_argument("--bad", default=None, help="无法修复的棋谱写入此文件")
    args = parser.parse_args()

    with open(args.src, encoding="utf-8") as handle:
        games = split_games(handle.read())

    stats = {"ok": 0, "fixed": 0, "unfixable": 0}
    good, bad = [], []
    for game in games:
        pgn, status = fix_game(game)
        stats[status] += 1
        (good if pgn else bad).append(pgn or game)

    with open(args.dst, "w", encoding="utf-8") as handle:
        handle.write("\n".join(good))
    if args.bad:
        with open(args.bad, "w", encoding="utf-8") as handle:
            handle.write("\n".join(bad))

    print(
        f"总 {len(games)}：正常 {stats['ok']}，"
        f"修正行棋方 {stats['fixed']}，无法修复 {stats['unfixable']}"
    )
    print(f"输出 {args.dst}")


if __name__ == "__main__":
    main()
