from chess_engine.board import INITIAL_FEN, Board
from chess_engine.move import Move

COLLECTION = "测试集"
CATEGORY = f"古谱 · {COLLECTION}"

# 共享前五着（红黑交替）
SHARED5 = [
    {"x1": 1, "y1": 2, "x2": 4, "y2": 2},  # 炮二平五
    {"x1": 7, "y1": 9, "x2": 6, "y2": 7},  # 马8进7
    {"x1": 7, "y1": 0, "x2": 6, "y2": 2},  # 马二进三
    {"x1": 1, "y1": 9, "x2": 2, "y2": 7},  # 马2进3
    {"x1": 8, "y1": 0, "x2": 7, "y2": 0},  # 车一平二
]
BLACK_FORK_A = {"x1": 2, "y1": 6, "x2": 2, "y2": 5}  # 卒3进1
BLACK_FORK_B = {"x1": 6, "y1": 6, "x2": 6, "y2": 5}  # 卒7进1


def fen_after(moves, ply):
    board = Board()
    board.load_fen(INITIAL_FEN)
    for raw in moves[:ply]:
        board.apply_move(Move.from_dict(raw))
    return board.to_fen()


def create_game(client, name, moves, category=CATEGORY):
    resp = client.post(
        "/api/games", json={"name": name, "category": category, "moves": moves}
    )
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["id"]


def children(client, fen, collection=COLLECTION):
    resp = client.post(
        "/api/games/collections/children", json={"collection": collection, "fen": fen}
    )
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()


def test_fork_after_five_plies_branchable(client):
    create_game(client, "甲", SHARED5 + [BLACK_FORK_A])
    create_game(client, "乙", SHARED5 + [BLACK_FORK_B])
    body = children(client, fen_after(SHARED5, 5))
    assert body["branchable"] is True
    assert len(body["branches"]) == 2
    assert body["plies"] == {"min": 5, "max": 5}


def test_fork_within_four_plies_not_branchable(client):
    create_game(client, "甲", SHARED5[:3] + [BLACK_FORK_A])
    create_game(client, "乙", SHARED5[:3] + [BLACK_FORK_B])
    body = children(client, fen_after(SHARED5, 3))
    assert body["branchable"] is False
    assert len(body["branches"]) == 2


def test_exact_four_plies_not_branchable(client):
    red_fork_a = {"x1": 8, "y1": 0, "x2": 7, "y2": 0}
    red_fork_b = {"x1": 2, "y1": 3, "x2": 2, "y2": 4}
    create_game(client, "甲", SHARED5[:4] + [red_fork_a])
    create_game(client, "乙", SHARED5[:4] + [red_fork_b])
    body = children(client, fen_after(SHARED5, 4))
    assert body["plies"] == {"min": 4, "max": 4}
    assert body["branchable"] is False


def test_transposition_merges_same_node(client):
    t1 = [
        {"x1": 2, "y1": 3, "x2": 2, "y2": 4},  # 兵三进一
        {"x1": 2, "y1": 6, "x2": 2, "y2": 5},  # 卒3进1
        {"x1": 6, "y1": 3, "x2": 6, "y2": 4},  # 兵七进一
        {"x1": 6, "y1": 6, "x2": 6, "y2": 5},  # 卒7进1
        {"x1": 1, "y1": 2, "x2": 4, "y2": 2},  # 炮二平五
    ]
    t2 = [
        {"x1": 6, "y1": 3, "x2": 6, "y2": 4},
        {"x1": 6, "y1": 6, "x2": 6, "y2": 5},
        {"x1": 2, "y1": 3, "x2": 2, "y2": 4},
        {"x1": 2, "y1": 6, "x2": 2, "y2": 5},
        {"x1": 1, "y1": 2, "x2": 4, "y2": 2},
    ]
    assert fen_after(t1, 4) == fen_after(t2, 4)
    create_game(client, "转置甲", t1)
    create_game(client, "转置乙", t2)
    body = children(client, fen_after(t1, 4))
    assert len(body["branches"]) == 1
    assert len(body["branches"][0]["games"]) == 2


def test_cross_collection_isolated(client):
    create_game(client, "甲", SHARED5 + [BLACK_FORK_A])
    create_game(client, "乙", SHARED5 + [BLACK_FORK_B], category="古谱 · 另一个")
    body = children(client, fen_after(SHARED5, 5))
    assert len(body["branches"]) == 1


def test_single_game_not_branchable(client):
    create_game(client, "独苗", SHARED5 + [BLACK_FORK_A])
    body = children(client, fen_after(SHARED5, 5))
    assert body["branchable"] is False
    assert len(body["branches"]) == 1


def test_non_collection_not_indexed(client):
    create_game(client, "甲", SHARED5 + [BLACK_FORK_A], category="中炮")
    create_game(client, "乙", SHARED5 + [BLACK_FORK_B], category="中炮")
    body = children(client, fen_after(SHARED5, 5), collection="中炮")
    assert body["branches"] == []


def test_index_sync_on_update_and_delete(client):
    a_id = create_game(client, "甲", SHARED5 + [BLACK_FORK_A])
    b_id = create_game(client, "乙", SHARED5 + [BLACK_FORK_B])
    assert len(children(client, fen_after(SHARED5, 5))["branches"]) == 2

    resp = client.put(f"/api/games/{a_id}", json={"moves": SHARED5})
    assert resp.status_code == 200
    body = children(client, fen_after(SHARED5, 5))
    assert body["branchable"] is False
    assert len(body["branches"]) == 1

    assert client.delete(f"/api/games/{b_id}").status_code == 204
    assert children(client, fen_after(SHARED5, 5))["branches"] == []
