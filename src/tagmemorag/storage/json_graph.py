from __future__ import annotations

from pathlib import Path
import json

import networkx as nx

from .atomic import atomic_write
from .base import GraphStore


class JsonGraphStore(GraphStore):
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def save(self, graph: nx.Graph) -> None:
        data = {
            "nodes": [{"id": int(node_id), "attrs": attrs} for node_id, attrs in graph.nodes(data=True)],
            "edges": [
                {"source": int(source), "target": int(target), "attrs": attrs}
                for source, target, attrs in graph.edges(data=True)
            ],
        }

        def write(tmp_path: Path) -> None:
            tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

        atomic_write(self.path, write)

    def load(self) -> nx.Graph:
        data = json.loads(self.path.read_text(encoding="utf-8"))
        graph = nx.Graph()
        for item in data.get("nodes", []):
            graph.add_node(int(item["id"]), **item.get("attrs", {}))
        for item in data.get("edges", []):
            graph.add_edge(int(item["source"]), int(item["target"]), **item.get("attrs", {}))
        return graph
