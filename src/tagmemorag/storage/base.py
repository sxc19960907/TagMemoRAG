from __future__ import annotations

from abc import ABC, abstractmethod

import networkx as nx
import numpy as np

from tagmemorag.types import Anchor


class GraphStore(ABC):
    @abstractmethod
    def save(self, graph: nx.Graph) -> None:
        raise NotImplementedError

    @abstractmethod
    def load(self) -> nx.Graph:
        raise NotImplementedError

    def add_nodes(self, *args, **kwargs):
        raise NotImplementedError

    def remove_nodes(self, *args, **kwargs):
        raise NotImplementedError


class VectorStore(ABC):
    @abstractmethod
    def add(self, ids: np.ndarray, vecs: np.ndarray) -> None:
        raise NotImplementedError

    @abstractmethod
    def search(self, query_vec: np.ndarray, k: int) -> list[tuple[int, float]]:
        raise NotImplementedError

    @abstractmethod
    def get(self, node_id: int) -> np.ndarray:
        raise NotImplementedError

    def delete(self, *args, **kwargs):
        raise NotImplementedError

    def update(self, *args, **kwargs):
        raise NotImplementedError


class AnchorStore(ABC):
    @abstractmethod
    def save(self, anchors: list[Anchor]) -> None:
        raise NotImplementedError

    @abstractmethod
    def load(self) -> list[Anchor]:
        raise NotImplementedError

    @abstractmethod
    def reconcile(self, old_anchors, new_graph, new_vectors, embedder):
        raise NotImplementedError
