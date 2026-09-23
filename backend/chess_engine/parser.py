import re

from chess_engine.board import Board
from chess_engine.move import Move
from chess_engine.notation import parse_chinese

_ICCS_RE = re.compile(r"^[a-i][0-9][a-i][0-9]$")
_RESULT_TOKENS = ("*", "1-0", "0-1", "1/2-1/2")
_DOTS_RE = re.compile(r"^\.+$")


def _normalize_iccs(text):
    return text.strip().lower().replace("-", "")


def parse_iccs(text):
    normalized = _normalize_iccs(text)
    if not _ICCS_RE.match(normalized):
        raise ValueError(f"无效 ICCS 坐标：{text}")
    return Move(
        ord(normalized[0]) - ord("a"),
        int(normalized[1]),
        ord(normalized[2]) - ord("a"),
        int(normalized[3]),
    )


def _tokenize(text):
    text = re.sub(r"\{[^}]*\}", " ", text)
    text = re.sub(r";[^\n]*", " ", text)
    cleaned = re.sub(r"\d+\.(\.\.)?", " ", text)
    return [
        token for token in cleaned.split()
        if token and token not in _RESULT_TOKENS and not _DOTS_RE.match(token)
    ]


def parse_moves(board, text):
    moves = []
    working = board.clone()
    for index, token in enumerate(_tokenize(text), start=1):
        try:
            if _ICCS_RE.match(_normalize_iccs(token)):
                move = parse_iccs(token)
            else:
                move = parse_chinese(working, token)
        except ValueError as exc:
            raise ValueError(f"第 {index} 步「{token}」解析失败：{exc}") from exc
        if not working.is_legal(move):
            raise ValueError(f"第 {index} 步「{token}」不是合法着法")
        working.apply_move(move)
        moves.append(move)
    return moves


def parse_pgn(text):
    headers = {}
    body_lines = []
    for line in text.splitlines():
        stripped = line.strip()
        match = re.match(r'^\[(\w+)\s+"(.*)"\]$', stripped)
        if match:
            headers[match.group(1)] = match.group(2)
        elif stripped:
            body_lines.append(stripped)
    board = Board.initial()
    fen = headers.get("FEN")
    if fen:
        try:
            board.load_fen(fen)
        except ValueError as exc:
            raise ValueError(f"FEN 头无效：{exc}") from exc
    moves = parse_moves(board, "\n".join(body_lines))
    return {
        "title": headers.get("Title", ""),
        "event": headers.get("Event", ""),
        "red_player": headers.get("Red", ""),
        "black_player": headers.get("Black", ""),
        "result": headers.get("Result", ""),
        "initial_fen": board.to_fen(),
        "moves": moves,
    }
