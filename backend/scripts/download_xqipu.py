#!/usr/bin/env python3
"""从 xqipu.com 下载棋谱并导出为 PGN（网站官方格式）。

数据来源：
    列表：GET https://www.xqipu.com/{list}?page=N   （如 qipus / eventqipu/27688）
    详情：GET https://www.xqipu.com/jsonqipu/{uuid}  （JSON，无需登录）

用法：
    python scripts/download_xqipu.py --list qipus --limit 5 --out data/xqipu_qipus.pgns
    python scripts/download_xqipu.py --list qipus --out data/xqipu_qipus.pgns \\
        --per-game-dir data/xqipu_pgn

输出的 .pgns 为多局合并文件，每局以 [Game "Chinese Chess"] 开头，
可直接用 scripts/import_pgns.py --source xqipu 导入。
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

BASE = "https://www.xqipu.com"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/json,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Cookie": "has_js=1",
}
UUID_RE = re.compile(
    r"/qipu/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"
)
SAFE_RE = re.compile(r'[\\/:*?"<>|\r\n\t]+')


def fetch(url, retries=4, timeout=20):
    last = None
    for attempt in range(retries):
        try:
            request = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            if exc.code < 500:
                raise RuntimeError(f"HTTP {exc.code}: {url}") from exc
            last = exc
            time.sleep(1.5 * (attempt + 1))
        except Exception as exc:  # noqa: BLE001 - 网络异常统一重试
            last = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"请求失败 {url}: {last}")


def collect_uuids(list_path, max_pages=500, quiet=False):
    uuids = []
    seen = set()
    for page in range(max_pages):
        try:
            html = fetch(f"{BASE}/{list_path}?page={page}").decode("utf-8", "replace")
        except RuntimeError:
            if not quiet:
                print(f"  page={page:>3} 列表结束", flush=True)
            break
        found = UUID_RE.findall(html)
        fresh = [uuid for uuid in found if uuid not in seen]
        for uuid in fresh:
            seen.add(uuid)
            uuids.append(uuid)
        if not quiet:
            print(f"  page={page:>3} 新增 {len(fresh):>3} 条，累计 {len(uuids)} 条", flush=True)
        if not fresh:
            break
    return uuids


def collect_sub_ids(list_path, prefix, max_pages=400):
    """收集分类页下的子列表 id，如 /canjugupu 下的书籍 id。"""
    ids, seen = [], set()
    pattern = re.compile(rf"/{re.escape(prefix)}/(\d+)")
    for page in range(max_pages):
        try:
            html = fetch(f"{BASE}/{list_path}?page={page}").decode("utf-8", "replace")
        except RuntimeError:
            break
        found = pattern.findall(html)
        fresh = [x for x in found if x not in seen]
        for x in fresh:
            seen.add(x)
            ids.append(x)
        if not fresh:
            break
    return ids


def collect_expanded_uuids(list_path, prefix):
    """展开分类（如 canjugupu）下所有子列表的棋谱 uuid，去重保序。"""
    sub_ids = collect_sub_ids(list_path, prefix)
    print(f"  {list_path} 下共 {len(sub_ids)} 个子列表", flush=True)
    uuids, seen = [], set()
    for index, sub in enumerate(sub_ids, start=1):
        for uuid in collect_uuids(f"{prefix}/{sub}", quiet=True):
            if uuid not in seen:
                seen.add(uuid)
                uuids.append(uuid)
        if index % 10 == 0 or index == len(sub_ids):
            print(f"  子列表 {index}/{len(sub_ids)}，累计棋谱 {len(uuids)}", flush=True)
    return uuids


def fetch_qipu(uuid):
    raw = fetch(f"{BASE}/jsonqipu/{uuid}")
    data = json.loads(raw.decode("utf-8"))
    return data[0] if data else None


def build_moves(moves, fen):
    total = len(moves) // 4
    is_red = " b" not in fen
    parts = []
    for step in range(1, total + 1):
        move = moves[(step - 1) * 4 : step * 4].upper()
        move = f"{move[:2]}-{move[2:4]}"
        round_num = (step - 1) // 2 + 1
        if is_red:
            if step % 2 == 0:
                parts.append(move + "\n")
            else:
                parts.append(f"{round_num}. {move} ")
        else:
            if step == 1:
                parts.append(f"1. ..... {move}\n")
            elif step % 2 == 0:
                parts.append(f"{round_num}. {move} ")
            else:
                parts.append(move + "\n")
    parts.append(" *")
    return "".join(parts)


def build_pgn(qipu):
    fen = (qipu.get("fen") or "").strip()
    moves = qipu.get("moves") or ""
    fields = [
        ("Title", qipu.get("title", "")),
        ("Event", qipu.get("event") or qipu.get("field_event") or ""),
        ("Red", qipu.get("red", "")),
        ("RedTeam", qipu.get("red_team", "")),
        ("Black", qipu.get("black", "")),
        ("BlackTeam", qipu.get("black_team", "")),
        ("Opening", qipu.get("opening", "")),
        ("Date", qipu.get("日期") or qipu.get("date") or ""),
        ("Site", qipu.get("site", "")),
        ("Round", qipu.get("round", "")),
        ("Result", qipu.get("result", "")),
    ]
    lines = ['[Game "Chinese Chess"]']
    lines += [f'[{key} "{value}"]' for key, value in fields if value]
    if fen:
        lines.append(f'[FEN "{fen}"]')
    lines.append('[Format "ICCS"]')
    return "\n".join(lines) + "\n" + build_moves(moves, fen) + "\n"


def safe_filename(qipu, uuid):
    title = SAFE_RE.sub("_", (qipu.get("title") or "").strip()).strip("_")
    title = title[:80] or uuid
    return f"{title}_{uuid[:8]}.pgn"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", default="qipus", help="列表路径，如 qipus 或 eventqipu/27688")
    parser.add_argument("--expand", default=None, help="展开分类的子列表前缀，如 canjugupu")
    parser.add_argument("--out", default="data/xqipu_qipus.pgns", help="合并输出文件")
    parser.add_argument("--per-game-dir", default=None, help="同时按局输出单独 .pgn 的目录")
    parser.add_argument("--uuids-cache", default=None, help="uuid 列表缓存文件，避免重复枚举")
    parser.add_argument("--offset", type=int, default=0, help="从第 N 局开始（配合缓存分批）")
    parser.add_argument("--limit", type=int, default=None, help="只下载 N 局")
    parser.add_argument("--append", action="store_true", help="追加写入输出文件（分批下载用）")
    parser.add_argument("--delay", type=float, default=0.5, help="每局请求间隔秒数")
    args = parser.parse_args()

    print(f"[1/3] 收集棋谱列表：/{args.list}")
    if args.uuids_cache and os.path.exists(args.uuids_cache):
        with open(args.uuids_cache, encoding="utf-8") as handle:
            uuids = json.load(handle)
        print(f"      从缓存读取 {len(uuids)} 个 uuid")
    else:
        if args.expand:
            uuids = collect_expanded_uuids(args.list, args.expand)
        else:
            uuids = collect_uuids(args.list)
        if args.uuids_cache:
            with open(args.uuids_cache, "w", encoding="utf-8") as handle:
                json.dump(uuids, handle)
            print(f"      uuid 列表已缓存到 {args.uuids_cache}")

    start = args.offset
    end = start + args.limit if args.limit else None
    uuids = uuids[start:end]
    print(f"      本次待下载 {len(uuids)} 局（offset={start}）")

    if args.per_game_dir:
        os.makedirs(args.per_game_dir, exist_ok=True)
    out_dir = os.path.dirname(os.path.abspath(args.out))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    print("[2/3] 下载棋谱数据")
    mode = "a" if args.append else "w"
    success = failed = 0
    with open(args.out, mode, encoding="utf-8") as handle:
        for index, uuid in enumerate(uuids, start=1):
            try:
                qipu = fetch_qipu(uuid)
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print(f"  [{index}/{len(uuids)}] 失败 {uuid}: {exc}", flush=True)
                time.sleep(args.delay)
                continue
            if not qipu:
                failed += 1
                continue
            pgn = build_pgn(qipu)
            handle.write(pgn + "\n")
            handle.flush()
            success += 1
            if args.per_game_dir:
                path = os.path.join(args.per_game_dir, safe_filename(qipu, uuid))
                with open(path, "w", encoding="utf-8") as game_handle:
                    game_handle.write(pgn)
            if index % 50 == 0 or index == len(uuids):
                print(f"  [{index}/{len(uuids)}] 已下载，成功 {success} 失败 {failed}", flush=True)
            time.sleep(args.delay)

    print(f"[3/3] 完成：成功 {success}，失败 {failed}，输出 {args.out}")


if __name__ == "__main__":
    sys.exit(main())
