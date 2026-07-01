# ============ 图谱指标计算（与前端 metrics.js 完全对齐）============
import math
from typing import Dict, Any, List


def compute_metrics_from_graph(graph: Dict[str, Any]) -> Dict[str, Any]:
    """从图谱数据计算全部指标，算法与前端 computeMetrics() 完全一致"""
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    n = len(nodes)
    e = len(edges)
    if n == 0:
        return {}

    # 邻接表
    adj: Dict[int, List[int]] = {}
    for nd in nodes:
        adj[nd["id"]] = []
    for ed in edges:
        fid, tid = ed["from"], ed["to"]
        if fid not in adj:
            adj[fid] = []
        if tid not in adj:
            adj[tid] = []
        adj[fid].append(tid)
        adj[tid].append(fid)

    # 连通度
    visited = set()
    max_comp = 0
    for nd in nodes:
        if nd["id"] in visited:
            continue
        stack = [nd["id"]]
        size = 0
        while stack:
            nid = stack.pop()
            if nid in visited:
                continue
            visited.add(nid)
            size += 1
            for neighbor in adj.get(nid, []):
                if neighbor not in visited:
                    stack.append(neighbor)
        if size > max_comp:
            max_comp = size
    connectivity = max_comp / n

    # 度数
    degrees = [len(adj.get(nd["id"], [])) for nd in nodes]
    avg_deg = sum(degrees) / n if n > 0 else 0

    # 聚类系数
    cc_list = []
    for nd in nodes:
        neigh = adj.get(nd["id"], [])
        k = len(neigh)
        if k < 2:
            continue
        tri = 0
        for i in range(k):
            for j in range(i + 1, k):
                if neigh[j] in adj.get(neigh[i], []):
                    tri += 1
        cc_list.append((2 * tri) / (k * (k - 1)))
    clustering = sum(cc_list) / len(cc_list) if cc_list else 0

    # 自我中心度
    self_node = next((nd for nd in nodes if nd.get("type") == "self"), None)
    self_deg = len(adj.get(self_node["id"], [])) if self_node else 0
    centrality = self_deg / (n - 1) if n > 1 else 0

    # 关系类型熵
    type_counts: Dict[str, int] = {}
    for ed in edges:
        t = ed.get("type", "custom")
        type_counts[t] = type_counts.get(t, 0) + 1
    entropy = 0.0
    for cnt in type_counts.values():
        p = cnt / e
        entropy -= p * math.log2(p) if p > 0 else 0
    entropy_norm = entropy / math.log2(4) if e > 0 else 0

    # 密度
    density = (2 * e) / (n * (n - 1)) if n > 1 else 0

    # 最短路径（BFS 全源）
    sum_dist = 0
    dist_count = 0
    eff_sum = 0.0
    for src in nodes:
        dist = {nd["id"]: float("inf") for nd in nodes}
        dist[src["id"]] = 0
        queue = [src["id"]]
        qi = 0
        while qi < len(queue):
            u = queue[qi]
            qi += 1
            for v in adj.get(u, []):
                if dist[v] == float("inf"):
                    dist[v] = dist[u] + 1
                    queue.append(v)
        for nd in nodes:
            d = dist[nd["id"]]
            if d != float("inf") and d > 0:
                sum_dist += d
                dist_count += 1
                eff_sum += 1.0 / d
    avg_path_len = sum_dist / dist_count if dist_count > 0 else 0
    global_eff = eff_sum / (n * (n - 1)) if n > 1 else 0

    # 小世界系数
    rand_cc = avg_deg / n if avg_deg > 1 else 0
    rand_pl = math.log(n) / math.log(avg_deg) if avg_deg > 1 and n > 1 else 0
    if rand_cc > 0 and rand_pl > 0 and avg_path_len > 0:
        small_world = (clustering / rand_cc) / (avg_path_len / rand_pl)
    else:
        small_world = 0

    anon_count = sum(1 for nd in nodes if nd.get("isAnon") or nd.get("type") == "anon")

    return {
        "connectivity": connectivity,
        "clustering": clustering,
        "centrality": centrality,
        "entropy": entropy_norm,
        "density": density,
        "avgPathLen": avg_path_len,
        "globalEff": global_eff,
        "smallWorld": small_world,
        "nodeCount": n,
        "edgeCount": e,
        "anonCount": anon_count,
        "typeCounts": type_counts,
    }
