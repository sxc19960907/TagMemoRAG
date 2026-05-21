from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


REPLAY_REPORT_SCHEMA_VERSION = "replay_report.v1"


@dataclass(frozen=True)
class SkippedReplayRow:
    """A persisted plan row that could not or should not be replayed."""

    plan_id: str
    reason: str

    def to_dict(self) -> dict[str, str]:
        return {"plan_id": self.plan_id, "reason": self.reason}


@dataclass(frozen=True)
class ReplayPlan:
    """Replayable subset of a persisted QueryPlan row."""

    plan_id: str
    kb_name: str
    query: str
    created_at: str
    intent: str
    filters: dict[str, Any]
    budget: dict[str, Any]
    stored_evidence_ids: tuple[str, ...] = ()
    cache_status: str = ""
    rerank: dict[str, Any] | None = None
    warnings: tuple[str, ...] = ()

    def to_dict(self, *, include_query: bool = False) -> dict[str, Any]:
        data: dict[str, Any] = {
            "plan_id": self.plan_id,
            "kb_name": self.kb_name,
            "created_at": self.created_at,
            "intent": self.intent,
            "filters": dict(self.filters),
            "budget": dict(self.budget),
            "stored_evidence_ids": list(self.stored_evidence_ids),
            "cache_status": self.cache_status,
            "rerank": self.rerank,
            "warnings": list(self.warnings),
        }
        if include_query:
            data["query"] = self.query
        return data


@dataclass(frozen=True)
class ReplayCaseResult:
    """Result of replaying one plan against one generation."""

    plan_id: str
    generation: int
    query_replayed: bool
    result_count: int = 0
    top_chunk_id: str = ""
    top_evidence_id: str = ""
    chunk_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    latency_ms: float = 0.0
    warnings: tuple[str, ...] = ()
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "generation": self.generation,
            "query_replayed": self.query_replayed,
            "result_count": self.result_count,
            "top_chunk_id": self.top_chunk_id,
            "top_evidence_id": self.top_evidence_id,
            "chunk_ids": list(self.chunk_ids),
            "evidence_ids": list(self.evidence_ids),
            "latency_ms": round(float(self.latency_ms), 3),
            "warnings": list(self.warnings),
            "error": self.error,
        }


@dataclass(frozen=True)
class ReplayRunMetrics:
    """Aggregate metrics for a set of replay case results."""

    queries_replayed: int = 0
    any_hit_rate: float = 0.0
    evidence_overlap_at_k: float = 0.0
    evidence_overlap_cases: int = 0
    top1_stability: float = 0.0
    top1_stability_cases: int = 0
    latency_ms_p50: float = 0.0
    latency_ms_p95: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "queries_replayed": int(self.queries_replayed),
            "any_hit_rate": _round(self.any_hit_rate),
            "evidence_overlap_at_k": _round(self.evidence_overlap_at_k),
            "evidence_overlap_cases": int(self.evidence_overlap_cases),
            "top1_stability": _round(self.top1_stability),
            "top1_stability_cases": int(self.top1_stability_cases),
            "latency_ms_p50": round(float(self.latency_ms_p50), 3),
            "latency_ms_p95": round(float(self.latency_ms_p95), 3),
        }


@dataclass(frozen=True)
class ReplayReport:
    """Serializable top-level replay report."""

    kb: str
    filters: dict[str, Any]
    metrics_requested: tuple[str, ...]
    row_counts: dict[str, int]
    target: dict[str, Any]
    baseline: dict[str, Any] | None = None
    deltas: dict[str, float] = field(default_factory=dict)
    rerank_summary: dict[str, Any] = field(default_factory=dict)
    skipped_rows: tuple[SkippedReplayRow, ...] = ()
    regression_detected: bool = False
    forced_mode: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "schema_version": REPLAY_REPORT_SCHEMA_VERSION,
            "kb": self.kb,
            "filters": dict(self.filters),
            "metrics_requested": list(self.metrics_requested),
            "row_counts": dict(self.row_counts),
            "target": self.target,
            "deltas": dict(self.deltas),
            "rerank_summary": dict(self.rerank_summary),
            "skipped_rows": [row.to_dict() for row in self.skipped_rows],
            "regression_detected": bool(self.regression_detected),
        }
        if self.forced_mode is not None:
            data["forced_mode"] = self.forced_mode
        if self.baseline is not None:
            data["baseline"] = self.baseline
        return data


def _round(value: float) -> float:
    return round(float(value), 6)
