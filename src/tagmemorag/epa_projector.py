from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .epa_basis import EPABasis, load_epa_basis


@dataclass(frozen=True)
class EPAProjector:
    basis: EPABasis

    @classmethod
    def from_path(cls, path: str | Path) -> "EPAProjector":
        basis = load_epa_basis(Path(path))
        if basis is None:
            raise FileNotFoundError(path)
        return cls(basis)

    def project(self, query_vec: np.ndarray) -> dict[str, Any]:
        vector = np.asarray(query_vec, dtype=np.float32)
        if vector.shape != (self.basis.dim,):
            raise ValueError(f"query vector shape must be ({self.basis.dim},), got {vector.shape}")

        centered = vector - self.basis.basisMean
        projections = self.basis.orthoBasis @ centered
        energy = projections.astype(np.float64) ** 2
        total_energy = float(energy.sum())
        if total_energy < 1e-12:
            return {
                "projections": projections,
                "probabilities": np.zeros(self.basis.K, dtype=np.float32),
                "entropy": 0.0,
                "logicDepth": 0.0,
                "dominantAxes": [],
            }

        probabilities = (energy / total_energy).astype(np.float32)
        entropy = -float((probabilities * np.log2(probabilities + 1e-12)).sum())
        normalized_entropy = entropy / np.log2(self.basis.K) if self.basis.K > 1 else 0.0
        dominant_axes = sorted(
            [
                {
                    "index": index,
                    "label": self.basis.basisLabels[index],
                    "energy": float(probabilities[index]),
                    "projection": float(projections[index]),
                }
                for index in range(self.basis.K)
                if float(probabilities[index]) > 0.05
            ],
            key=lambda axis: -float(axis["energy"]),
        )
        return {
            "projections": projections,
            "probabilities": probabilities,
            "entropy": normalized_entropy,
            "logicDepth": 1.0 - normalized_entropy,
            "dominantAxes": dominant_axes,
        }
