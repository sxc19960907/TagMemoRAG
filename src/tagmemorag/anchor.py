from __future__ import annotations

from .errors import AnchorNotFoundError, ErrorCode, ServiceError
from .storage.json_anchor import JsonAnchorStore
from .types import Anchor, GraphState


class AnchorSystem:
    def __init__(self, state: GraphState, store: JsonAnchorStore | None = None):
        self.state = state
        self.store = store

    def list(self) -> list[Anchor]:
        return list(self.state.anchors.values())

    def add(self, node_id: int, label: str, boost: float = 2.0, propagation_boost: float = 1.0) -> Anchor:
        if node_id not in self.state.graph.nodes:
            raise ServiceError(
                ErrorCode.INVALID_INPUT,
                "node_id does not exist in current graph.",
                {"node_id": node_id},
            )
        node = self.state.graph.nodes[node_id]
        anchor = Anchor(
            anchor_key=str(node["anchor_key"]),
            label=label,
            boost=boost,
            propagation_boost=propagation_boost,
            node_id=node_id,
            old_text=str(node.get("text", "")),
        )
        self.state.anchors[node_id] = anchor
        self._persist()
        return anchor

    def delete(self, anchor_key: str) -> None:
        for node_id, anchor in list(self.state.anchors.items()):
            if anchor.anchor_key == anchor_key:
                del self.state.anchors[node_id]
                self._persist()
                return
        raise AnchorNotFoundError(anchor_key)

    def _persist(self) -> None:
        if self.store:
            self.store.save(self.list())
