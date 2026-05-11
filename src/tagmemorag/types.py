from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
from typing import Any

import networkx as nx
import numpy as np


def compute_anchor_key(path: tuple[str, ...] | list[str], header: str, text: str) -> str:
    raw = "|".join(path) + "|" + header + "|" + text[:80]
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


@dataclass(frozen=True)
class Chunk:
    text: str
    header: str
    path: tuple[str, ...]
    level: int
    start_line: int
    source_file: str


@dataclass
class Anchor:
    anchor_key: str
    label: str
    boost: float = 2.0
    propagation_boost: float = 1.0
    node_id: int | None = None
    old_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "anchor_key": self.anchor_key,
            "label": self.label,
            "boost": self.boost,
            "propagation_boost": self.propagation_boost,
            "node_id": self.node_id,
            "old_text": self.old_text,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Anchor":
        return cls(
            anchor_key=str(data["anchor_key"]),
            label=str(data.get("label", "")),
            boost=float(data.get("boost", 2.0)),
            propagation_boost=float(data.get("propagation_boost", 1.0)),
            node_id=data.get("node_id"),
            old_text=str(data.get("old_text", "")),
        )


@dataclass(frozen=True)
class Result:
    node_id: int
    score: float
    text: str
    header: str
    path: list[str]
    source_file: str
    start_line: int
    anchor_key: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "score": self.score,
            "text": self.text,
            "header": self.header,
            "path": self.path,
            "source_file": self.source_file,
            "start_line": self.start_line,
            "anchor_key": self.anchor_key,
        }


@dataclass
class GraphState:
    graph: nx.Graph
    vectors: np.ndarray
    anchors: dict[int, Anchor] = field(default_factory=dict)
    build_id: str = field(default_factory=lambda: datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f"))
    kb_name: str = "default"
    meta: dict[str, Any] = field(default_factory=dict)
    unresolved_anchors: list[Anchor] = field(default_factory=list)
