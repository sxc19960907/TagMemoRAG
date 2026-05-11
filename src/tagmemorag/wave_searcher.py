from __future__ import annotations

from collections import defaultdict
from typing import Literal

import networkx as nx
import numpy as np

from .types import Anchor, Result


def wave_search(
    query_vec: np.ndarray,
    graph: nx.Graph,
    vectors: np.ndarray,
    anchors: dict[int, Anchor] | None = None,
    top_k: int = 5,
    source_k: int = 3,
    steps: int = 3,
    decay: float = 0.7,
    amplitude_cutoff: float = 0.01,
    aggregate: Literal["max", "sum"] = "max",
) -> list[Result]:
    anchors = anchors or {}
    if aggregate not in {"max", "sum"}:
        raise ValueError("aggregate must be 'max' or 'sum'")
    if graph.number_of_nodes() == 0:
        return []
    if vectors.shape[0] != graph.number_of_nodes():
        raise ValueError("vectors row count must match graph nodes")

    sims = vectors @ query_vec
    count = min(source_k, len(sims))
    source_ids = np.argpartition(-sims, count - 1)[:count]

    amplitudes: defaultdict[int, float] = defaultdict(float)
    current_wave: dict[int, float] = {}
    for nid in source_ids:
        node_id = int(nid)
        amp = float(sims[node_id])
        if node_id in anchors:
            amp *= anchors[node_id].boost
        if aggregate == "max":
            amplitudes[node_id] = max(amplitudes[node_id], amp)
            current_wave[node_id] = max(current_wave.get(node_id, 0.0), amp)
        else:
            amplitudes[node_id] += amp
            current_wave[node_id] = current_wave.get(node_id, 0.0) + amp

    for _ in range(steps):
        next_wave: dict[int, float] = {}
        for node_id, amp in current_wave.items():
            if amp < amplitude_cutoff:
                continue
            prop_amp = amp
            if node_id in anchors:
                prop_amp *= anchors[node_id].propagation_boost
            for neighbor, attrs in graph[node_id].items():
                new_amp = prop_amp * float(attrs["weight"]) * decay
                if new_amp < amplitude_cutoff:
                    continue
                if aggregate == "max":
                    next_wave[neighbor] = max(next_wave.get(neighbor, 0.0), new_amp)
                else:
                    next_wave[neighbor] = next_wave.get(neighbor, 0.0) + new_amp
        for node_id, amp in next_wave.items():
            if aggregate == "max":
                amplitudes[node_id] = max(amplitudes[node_id], amp)
            else:
                amplitudes[node_id] += amp
        current_wave = next_wave

    ranked = sorted(amplitudes.items(), key=lambda item: (-item[1], item[0]))[:top_k]
    return [_make_result(graph, node_id, score) for node_id, score in ranked]


def _make_result(graph: nx.Graph, node_id: int, score: float) -> Result:
    node = graph.nodes[node_id]
    return Result(
        node_id=node_id,
        score=float(score),
        text=str(node.get("text", "")),
        header=str(node.get("header", "")),
        path=list(node.get("path", [])),
        source_file=str(node.get("source_file", "")),
        start_line=int(node.get("start_line", 0)),
        anchor_key=str(node.get("anchor_key", "")),
    )
