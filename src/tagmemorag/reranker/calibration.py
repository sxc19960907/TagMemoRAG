"""Score calibration for reranker outputs (Architecture v2 § A3 / Decision D2).

`relevance_score` from vendors is NOT guaranteed normalized — could be 0..1,
could be ±10, could be unbounded. Calibration maps raw scores to a comparable
range (typically [0, 1]) so:

- Item ordering within a result is preserved (calibration is monotonic).
- Plan log can store comparable values across requests for offline analysis.
- Future hybrid fusion (T2.5) can plug in without changing the dispatcher
  contract.

Edge cases (handled identically across implementations):
- Empty list → empty list.
- Single element → [0.5].
- All elements equal → list of 0.5s ("no information; mid-point").
"""

from __future__ import annotations

import math
from typing import Literal, Protocol


class Calibrator(Protocol):
    name: str
    def calibrate(self, raw_scores: list[float]) -> list[float]: ...


def _degenerate_outputs(raw_scores: list[float]) -> list[float] | None:
    """Return mid-point list for degenerate cases; None when normal calibration applies."""
    n = len(raw_scores)
    if n == 0:
        return []
    if n == 1:
        return [0.5]
    if max(raw_scores) == min(raw_scores):
        return [0.5] * n
    return None


class MinMaxCalibrator:
    """Linear map to [0, 1] using batch min/max. Default per D2."""

    name: str = "minmax"

    def calibrate(self, raw_scores: list[float]) -> list[float]:
        degenerate = _degenerate_outputs(raw_scores)
        if degenerate is not None:
            return degenerate
        lo = min(raw_scores)
        hi = max(raw_scores)
        span = hi - lo
        return [(s - lo) / span for s in raw_scores]


class ZScoreCalibrator:
    """Standard score (mean=0, std=1). Returns z-scores; downstream may
    rescale if it expects [0, 1]. Plan log records the value as-is."""

    name: str = "zscore"

    def calibrate(self, raw_scores: list[float]) -> list[float]:
        degenerate = _degenerate_outputs(raw_scores)
        if degenerate is not None:
            return degenerate
        n = len(raw_scores)
        mean = sum(raw_scores) / n
        var = sum((s - mean) ** 2 for s in raw_scores) / n
        std = math.sqrt(var) if var > 0 else 1.0
        return [(s - mean) / std for s in raw_scores]


class SigmoidCalibrator:
    """Pass through sigmoid; bounded to (0, 1). Treats raw scores as logits."""

    name: str = "sigmoid"

    def calibrate(self, raw_scores: list[float]) -> list[float]:
        degenerate = _degenerate_outputs(raw_scores)
        if degenerate is not None:
            return degenerate
        out: list[float] = []
        for s in raw_scores:
            # Avoid overflow for very large/small s
            if s >= 0:
                ez = math.exp(-s)
                out.append(1.0 / (1.0 + ez))
            else:
                ez = math.exp(s)
                out.append(ez / (1.0 + ez))
        return out


class IdentityCalibrator:
    """Passthrough; preserves vendor scores. Useful for debugging or when
    downstream prefers raw values."""

    name: str = "identity"

    def calibrate(self, raw_scores: list[float]) -> list[float]:
        return list(raw_scores)


_REGISTRY: dict[str, type] = {
    "minmax": MinMaxCalibrator,
    "zscore": ZScoreCalibrator,
    "sigmoid": SigmoidCalibrator,
    "identity": IdentityCalibrator,
}


def build_calibrator(name: Literal["minmax", "zscore", "sigmoid", "identity"]) -> Calibrator:
    cls = _REGISTRY.get(name)
    if cls is None:
        raise ValueError(f"Unknown calibrator: {name}")
    return cls()


__all__ = [
    "Calibrator",
    "IdentityCalibrator",
    "MinMaxCalibrator",
    "SigmoidCalibrator",
    "ZScoreCalibrator",
    "build_calibrator",
]
