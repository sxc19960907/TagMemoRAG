from __future__ import annotations

import networkx as nx
import numpy as np

from .config import GraphConfig
from .types import Chunk, compute_anchor_key


def build_graph(chunks: list[Chunk], embeddings: np.ndarray, cfg: GraphConfig | None = None) -> nx.Graph:
    cfg = cfg or GraphConfig()
    graph = nx.Graph()
    for idx, chunk in enumerate(chunks):
        graph.add_node(
            idx,
            text=chunk.text,
            header=chunk.header,
            path=list(chunk.path),
            level=chunk.level,
            start_line=chunk.start_line,
            source_file=chunk.source_file,
            anchor_key=compute_anchor_key(chunk.path, chunk.header, chunk.text),
        )

    if len(chunks) == 0:
        return graph

    if embeddings.shape[0] != len(chunks):
        raise ValueError("embeddings row count must match chunks")

    sims = embeddings @ embeddings.T
    for i in range(len(chunks)):
        for j in range(i + 1, len(chunks)):
            score = float(sims[i, j])
            if score > cfg.sim_threshold:
                _merge_edge(graph, i, j, score, "semantic")

    for i in range(len(chunks) - 1):
        _merge_edge(graph, i, i + 1, cfg.consecutive_bonus, "consecutive", additive=True)

    for i in range(len(chunks)):
        for j in range(i + 1, len(chunks)):
            path_i = chunks[i].path
            path_j = chunks[j].path
            if _is_parent_child(path_i, path_j):
                _merge_edge(graph, i, j, cfg.parent_child_bonus, "parent_child", additive=True)
            elif len(path_i) > 1 and len(path_i) == len(path_j) and path_i[:-1] == path_j[:-1] and path_i != path_j:
                _merge_edge(graph, i, j, cfg.sibling_bonus, "sibling", additive=True)

    return graph


def _merge_edge(graph: nx.Graph, i: int, j: int, weight: float, kind: str, additive: bool = False) -> None:
    if graph.has_edge(i, j):
        existing = float(graph[i][j]["weight"])
        new_weight = min(1.0, existing + weight) if additive else max(existing, weight)
        existing_kind = graph[i][j].get("kind", kind)
        graph[i][j].update(weight=new_weight, kind=kind if weight >= existing else existing_kind)
    else:
        graph.add_edge(i, j, weight=min(1.0, float(weight)), kind=kind)


def _is_parent_child(a: tuple[str, ...], b: tuple[str, ...]) -> bool:
    if abs(len(a) - len(b)) != 1:
        return False
    shorter, longer = (a, b) if len(a) < len(b) else (b, a)
    return longer[: len(shorter)] == shorter
