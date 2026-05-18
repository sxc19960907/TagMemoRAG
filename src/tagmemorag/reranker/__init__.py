"""Reranker first-class component (Architecture v2 § A3 / T3)."""

from .base import (
    RerankDoc,
    RerankResult,
    RerankResultItem,
    RerankSpec,
    Reranker,
    RerankerOutcome,
)
from .cache import RerankCache
from .calibration import (
    Calibrator,
    IdentityCalibrator,
    MinMaxCalibrator,
    SigmoidCalibrator,
    ZScoreCalibrator,
    build_calibrator,
)
from .circuit_breaker import CircuitBreaker
from .dispatcher import RerankerDispatcher
from .local_fallback import NoopReranker
from .siliconflow import (
    RerankerCircuitOpenError,
    RerankerClientError,
    RerankerVendorError,
    SFQwen3Reranker,
)

__all__ = [
    "Calibrator",
    "CircuitBreaker",
    "IdentityCalibrator",
    "MinMaxCalibrator",
    "NoopReranker",
    "RerankCache",
    "RerankDoc",
    "RerankResult",
    "RerankResultItem",
    "RerankSpec",
    "Reranker",
    "RerankerCircuitOpenError",
    "RerankerClientError",
    "RerankerDispatcher",
    "RerankerOutcome",
    "RerankerVendorError",
    "SFQwen3Reranker",
    "SigmoidCalibrator",
    "ZScoreCalibrator",
    "build_calibrator",
]
