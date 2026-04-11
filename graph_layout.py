from __future__ import annotations

import math
from typing import Dict, List, Sequence, Set

import networkx as nx
from networkx.algorithms.community import kernighan_lin_bisection


def _recursive_kl_partition(
    graph: nx.Graph,
    nodes: Sequence[str],
    *,
    min_size: int = 4,
    depth: int = 0,
    max_depth: int = 4,
) -> List[Set[str]]:
    node_list = list(dict.fromkeys(nodes))
    if len(node_list) <= min_size or depth >= max_depth:
        return [set(node_list)] if node_list else []

    subgraph = graph.subgraph(node_list).copy()
    if subgraph.number_of_nodes() < 2:
        return [set(node_list)]

    ordered = sorted(subgraph.nodes())
    midpoint = len(ordered) // 2
    initial_partition = (set(ordered[:midpoint]), set(ordered[midpoint:]))

    try:
        left, right = kernighan_lin_bisection(
            subgraph,
            partition=initial_partition,
            max_iter=8,
            weight="weight",
        )
    except Exception:
        return [set(node_list)]

    if not left or not right:
        return [set(node_list)]

    if min(len(left), len(right)) < max(2, min_size // 2):
        return [set(node_list)]

    results: List[Set[str]] = []
    results.extend(_recursive_kl_partition(graph, list(left), min_size=min_size, depth=depth + 1, max_depth=max_depth))
    results.extend(_recursive_kl_partition(graph, list(right), min_size=min_size, depth=depth + 1, max_depth=max_depth))
    return results


def _group_centers(count: int, radius: float = 6.0) -> List[tuple[float, float]]:
    if count <= 0:
        return []
    if count == 1:
        return [(0.0, 0.0)]
    cols = math.ceil(math.sqrt(count))
    rows = math.ceil(count / cols)
    centers: List[tuple[float, float]] = []
    for idx in range(count):
        col = idx % cols
        row = idx // cols
        x = (col - (cols - 1) / 2.0) * radius
        y = (row - (rows - 1) / 2.0) * radius
        centers.append((x, y))
    return centers


def compute_partitioned_layout(graph: nx.DiGraph) -> Dict[str, Dict[str, float | int]]:
    if graph.number_of_nodes() == 0:
        return {}
    if graph.number_of_nodes() == 1:
        node = next(iter(graph.nodes()))
        return {node: {"x": 0.0, "y": 0.0, "group": 0}}

    undirected = nx.Graph()
    undirected.add_nodes_from(graph.nodes(data=True))

    for u, v, data in graph.edges(data=True):
        weight = float(data.get("weight", 1.0))
        if undirected.has_edge(u, v):
            undirected[u][v]["weight"] += weight
        else:
            undirected.add_edge(u, v, weight=weight)

    partitions = _recursive_kl_partition(
        undirected,
        list(undirected.nodes()),
        min_size=4,
        max_depth=5,
    )
    if not partitions:
        partitions = [set(undirected.nodes())]

    partitions = sorted(partitions, key=lambda p: (-len(p), sorted(p)[0] if p else ""))
    centers = _group_centers(len(partitions), radius=7.5)

    positions: Dict[str, Dict[str, float | int]] = {}
    for group_index, part in enumerate(partitions):
        sub = undirected.subgraph(part).copy()
        if sub.number_of_nodes() == 1:
            only = next(iter(sub.nodes()))
            x0, y0 = centers[group_index]
            positions[only] = {"x": x0, "y": y0, "group": group_index}
            continue

        seed = 7 + group_index
        k = 1.2 / max(1, math.sqrt(sub.number_of_nodes()))
        local = nx.spring_layout(sub, seed=seed, weight="weight", k=k, iterations=80)
        x0, y0 = centers[group_index]
        scale = 2.6 + min(2.0, sub.number_of_nodes() * 0.12)

        for node, (x, y) in local.items():
            positions[node] = {
                "x": x0 + float(x) * scale,
                "y": y0 + float(y) * scale,
                "group": group_index,
            }

    for index, node in enumerate(graph.nodes()):
        if node not in positions:
            positions[node] = {
                "x": float(index),
                "y": 0.0,
                "group": len(partitions),
            }

    return positions
