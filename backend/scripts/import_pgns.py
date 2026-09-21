#!/usr/bin/env python3
"""批量导入 .pgns 多局棋谱集。

用法：
    .venv/bin/python scripts/import_pgns.py FILE --source dpxq
    .venv/bin/python scripts/import_pgns.py FILE --source wxf --dry-run --limit 500

分类规则：按来源内棋手出现频次取前 N 名，红方优先、黑方兜底，其余归「其他棋手」。
重复导入安全：按来源 + 棋手 + 赛事 + 结果 + 着法生成指纹，已入库的棋谱自动跳过。
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import select

from app import create_app
from chess_engine.parser import parse_pgn
from models import Game, db

UNESCAPE_RE = re.compile(r"\\u([0-9a-fA-F]{4})")
PLAYER_RE = re.compile(r'^\[(Red|Black) "(.*)"\]$')
OTHER_CATEGORY = "其他棋手"
BATCH_SIZE = 500


def unescape(text):
    return UNESCAPE_RE.sub(lambda match: chr(int(match.group(1), 16)), text)


def split_games(text):
    return ["[Game " + part for part in text.split("[Game ") if part.strip()]


def collect_players(games):
    counter = Counter()
    for game in games:
        for line in game.splitlines():
            match = PLAYER_RE.match(line.strip())
            if match:
                counter[unescape(match.group(2)).strip()] += 1
    return counter


def pick_category(red, black, top_players):
    if red in top_players:
        return red
    if black in top_players:
        return black
    return OTHER_CATEGORY


def build_hash(source, event, red, black, result, moves):
    payload = "|".join(
        [source, event, red, black, result, json.dumps(moves, separators=(",", ":"))]
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", help=".pgns 文件路径")
    parser.add_argument("--source", required=True, help="来源标记，如 dpxq / wxf")
    parser.add_argument("--top", type=int, default=100, help="棋手频次前 N 名单独分类")
    parser.add_argument("--limit", type=int, default=None, help="只处理前 N 局（调试用）")
    parser.add_argument("--dry-run", action="store_true", help="只解析统计，不写数据库")
    args = parser.parse_args()

    with open(args.file, encoding="utf-8-sig") as handle:
        text = handle.read()
    games = split_games(text)
    if args.limit:
        games = games[: args.limit]

    print(f"[{args.source}] {args.file}")
    print(f"共 {len(games)} 局，统计棋手频次…")
    players = collect_players(games)
    top_players = {name for name, _ in players.most_common(args.top)}
    print(f"不同棋手 {len(players)} 名，前 {args.top} 名入选分类")

    app = create_app()
    with app.app_context():
        existing = set()
        if not args.dry_run:
            existing = {
                row[0]
                for row in db.session.execute(
                    select(Game.source_hash).where(Game.source_hash.is_not(None))
                )
            }
            print(f"库中已有 {len(existing)} 条来源指纹")

        stats = {"imported": 0, "duplicate": 0, "failed": 0}
        failed_samples = []
        rows = []
        now = datetime.now(timezone.utc)
        table = Game.__table__
        started = time.time()

        for index, raw in enumerate(games, start=1):
            try:
                parsed = parse_pgn(unescape(raw))
            except ValueError as exc:
                stats["failed"] += 1
                if len(failed_samples) < 5:
                    failed_samples.append(str(exc)[:120])
                continue

            red = parsed["red_player"].strip()
            black = parsed["black_player"].strip()
            event = parsed["event"].strip()
            moves = [move.as_dict() for move in parsed["moves"]]
            digest = build_hash(args.source, event, red, black, parsed["result"], moves)
            if digest in existing:
                stats["duplicate"] += 1
                continue
            existing.add(digest)
            stats["imported"] += 1
            if args.dry_run:
                continue

            rows.append(
                {
                    "name": f"{red or '红方'} vs {black or '黑方'}",
                    "category": pick_category(red, black, top_players),
                    "red_player": red,
                    "black_player": black,
                    "event": event,
                    "result": parsed["result"],
                    "initial_fen": parsed["initial_fen"],
                    "moves": json.dumps(moves),
                    "practice_side": "both",
                    "source": args.source,
                    "source_hash": digest,
                    "created_at": now,
                    "updated_at": now,
                }
            )
            if len(rows) >= BATCH_SIZE:
                db.session.execute(table.insert(), rows)
                db.session.commit()
                rows = []
                rate = index / max(time.time() - started, 1e-6)
                print(
                    f"  已处理 {index}/{len(games)}，导入 {stats['imported']}，"
                    f"{rate:.0f} 局/秒",
                    flush=True,
                )

        if rows:
            db.session.execute(table.insert(), rows)
            db.session.commit()

        elapsed = time.time() - started
        print(
            f"完成：导入 {stats['imported']}，重复跳过 {stats['duplicate']}，"
            f"解析失败 {stats['failed']}，耗时 {elapsed:.1f}s"
        )
        for sample in failed_samples:
            print(f"  失败样例：{sample}")


if __name__ == "__main__":
    main()
