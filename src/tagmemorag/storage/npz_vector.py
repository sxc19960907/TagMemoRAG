from __future__ import annotations

from pathlib import Path

import numpy as np

from .atomic import atomic_write
from .base import VectorStore


class NpzVectorStore(VectorStore):
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.ids: np.ndarray | None = None
        self.vecs: np.ndarray | None = None

    def add(self, ids: np.ndarray, vecs: np.ndarray) -> None:
        self.ids = np.asarray(ids, dtype=np.int64)
        self.vecs = np.asarray(vecs, dtype=np.float32)

        def write(tmp_path: Path) -> None:
            with tmp_path.open("wb") as fp:
                np.savez(fp, ids=self.ids, vecs=self.vecs)

        atomic_write(self.path, write)

    def load(self, ids: np.ndarray | list[int] | None = None) -> tuple[np.ndarray, np.ndarray]:
        with np.load(self.path) as data:
            self.ids = np.asarray(data["ids"], dtype=np.int64)
            self.vecs = np.asarray(data["vecs"], dtype=np.float32)
        if ids is not None:
            requested = np.asarray(ids, dtype=np.int64)
            positions = []
            for node_id in requested:
                matches = np.where(self.ids == node_id)[0]
                if len(matches) == 0:
                    raise KeyError(int(node_id))
                positions.append(int(matches[0]))
            return requested, self.vecs[positions]
        return self.ids, self.vecs

    def search(self, query_vec: np.ndarray, k: int) -> list[tuple[int, float]]:
        ids, vecs = self._ensure_loaded()
        if len(ids) == 0:
            return []
        sims = vecs @ query_vec
        count = min(k, len(sims))
        top = np.argpartition(-sims, count - 1)[:count]
        ranked = sorted(((int(ids[i]), float(sims[i])) for i in top), key=lambda item: (-item[1], item[0]))
        return ranked

    def get(self, node_id: int) -> np.ndarray:
        ids, vecs = self._ensure_loaded()
        matches = np.where(ids == node_id)[0]
        if len(matches) == 0:
            raise KeyError(node_id)
        return vecs[int(matches[0])]

    def _ensure_loaded(self) -> tuple[np.ndarray, np.ndarray]:
        if self.ids is None or self.vecs is None:
            return self.load()
        return self.ids, self.vecs
