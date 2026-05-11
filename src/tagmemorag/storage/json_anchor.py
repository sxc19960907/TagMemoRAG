from __future__ import annotations

from pathlib import Path
import json

import networkx as nx
import numpy as np

from tagmemorag.types import Anchor, compute_anchor_key

from .atomic import atomic_write
from .base import AnchorStore


class JsonAnchorStore(AnchorStore):
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def save(self, anchors: list[Anchor]) -> None:
        data = {"anchors": [anchor.to_dict() for anchor in anchors]}

        def write(tmp_path: Path) -> None:
            tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

        atomic_write(self.path, write)

    def load(self) -> list[Anchor]:
        if not self.path.exists():
            return []
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return [Anchor.from_dict(item) for item in data.get("anchors", [])]

    def reconcile(
        self,
        old_anchors: list[Anchor],
        new_graph: nx.Graph,
        new_vectors: np.ndarray,
        embedder,
        similarity_threshold: float = 0.85,
    ) -> tuple[list[Anchor], list[Anchor]]:
        key_to_node = {attrs.get("anchor_key"): node_id for node_id, attrs in new_graph.nodes(data=True)}
        remapped: list[Anchor] = []
        unresolved: list[Anchor] = []

        for anchor in old_anchors:
            if anchor.anchor_key in key_to_node:
                anchor.node_id = int(key_to_node[anchor.anchor_key])
                remapped.append(anchor)
                continue
            if not anchor.old_text:
                anchor.node_id = None
                unresolved.append(anchor)
                continue
            old_vec = embedder.encode_query(anchor.old_text)
            sims = new_vectors @ old_vec
            if len(sims) == 0:
                anchor.node_id = None
                unresolved.append(anchor)
                continue
            best = int(np.argmax(sims))
            if float(sims[best]) >= similarity_threshold:
                node = new_graph.nodes[best]
                anchor.anchor_key = compute_anchor_key(node.get("path", []), node.get("header", ""), node.get("text", ""))
                anchor.node_id = best
                remapped.append(anchor)
            else:
                anchor.node_id = None
                unresolved.append(anchor)
        return remapped, unresolved
