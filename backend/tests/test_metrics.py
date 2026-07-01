"""图谱指标计算测试"""
from app.services.metrics import compute_metrics_from_graph


def test_empty_graph():
    """空图应返回空 dict"""
    result = compute_metrics_from_graph({"nodes": [], "edges": []})
    assert result == {}


def test_single_node():
    """单节点：connectivity=1，density=0"""
    graph = {
        "nodes": [{"id": 1, "label": "A", "type": "person"}],
        "edges": [],
    }
    m = compute_metrics_from_graph(graph)
    assert m["connectivity"] == 1.0
    assert m["density"] == 0.0
    assert m["nodeCount"] == 1
    assert m["edgeCount"] == 0


def test_two_nodes_connected():
    """两节点一连边：connectivity=1，density=1"""
    graph = {
        "nodes": [
            {"id": 1, "label": "A", "type": "person"},
            {"id": 2, "label": "B", "type": "person"},
        ],
        "edges": [{"from": 1, "to": 2, "type": "friend"}],
    }
    m = compute_metrics_from_graph(graph)
    assert m["connectivity"] == 1.0
    assert m["density"] == 1.0


def test_two_nodes_disconnected():
    """两节点无边：最大连通分量只有 1，connectivity=0.5"""
    graph = {
        "nodes": [
            {"id": 1, "label": "A", "type": "person"},
            {"id": 2, "label": "B", "type": "person"},
        ],
        "edges": [],
    }
    m = compute_metrics_from_graph(graph)
    assert m["connectivity"] == 0.5


def test_triangle():
    """三角形：每个节点的邻居彼此相连，clustering=1"""
    graph = {
        "nodes": [
            {"id": 1, "label": "A", "type": "person"},
            {"id": 2, "label": "B", "type": "person"},
            {"id": 3, "label": "C", "type": "person"},
        ],
        "edges": [
            {"from": 1, "to": 2, "type": "friend"},
            {"from": 2, "to": 3, "type": "friend"},
            {"from": 1, "to": 3, "type": "friend"},
        ],
    }
    m = compute_metrics_from_graph(graph)
    assert m["clustering"] == 1.0


def test_self_node_centrality():
    """自我节点中心度 = self 节点度数 / (n-1)"""
    # 4 个节点，self 连了 2 个邻居，centrality = 2 / 3
    graph = {
        "nodes": [
            {"id": 1, "label": "我", "type": "self"},
            {"id": 2, "label": "A", "type": "person"},
            {"id": 3, "label": "B", "type": "person"},
            {"id": 4, "label": "C", "type": "person"},
        ],
        "edges": [
            {"from": 1, "to": 2, "type": "family"},
            {"from": 1, "to": 3, "type": "friend"},
        ],
    }
    m = compute_metrics_from_graph(graph)
    assert abs(m["centrality"] - 2 / 3) < 1e-6


def test_anon_count():
    """isAnon 或 type=anon 的节点应计入 anonCount"""
    graph = {
        "nodes": [
            {"id": 1, "label": "A", "type": "person"},
            {"id": 2, "label": "陌生人", "type": "person", "isAnon": True},
            {"id": 3, "label": "匿名", "type": "anon"},
        ],
        "edges": [],
    }
    m = compute_metrics_from_graph(graph)
    assert m["anonCount"] == 2
