from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from .dataset import EvalThresholds, ExpectedResult
from .metrics import RankingMetrics


@dataclass(frozen=True)
class EvalSummary:
    cases: int
    passed: bool
    metrics: RankingMetrics

    def to_dict(self) -> dict[str, Any]:
        return {"cases": self.cases, "passed": self.passed, **self.metrics.to_dict()}


@dataclass(frozen=True)
class EvalCaseReport:
    id: str
    query: str
    kb_name: str
    top_k: int
    passed: bool
    metrics: RankingMetrics
    thresholds: EvalThresholds
    expected: list[dict[str, Any]]
    actual_top_k: list[dict[str, Any]]
    failures: list[str]
    search_strategy: str = ""
    ann_candidate_count: int = 0
    ann_fallback_reason: str = ""
    negatives: list[dict[str, Any]] = field(default_factory=list)
    negative_hits: list[dict[str, int | str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = {
            "id": self.id,
            "query": self.query,
            "kb_name": self.kb_name,
            "top_k": self.top_k,
            "passed": self.passed,
            "metrics": self.metrics.to_dict(),
            "thresholds": self.thresholds.to_dict(),
            "expected": self.expected,
            "actual_top_k": self.actual_top_k,
            "failures": self.failures,
        }
        if self.search_strategy:
            data["search_strategy"] = self.search_strategy
            data["ann_candidate_count"] = self.ann_candidate_count
            data["ann_fallback_reason"] = self.ann_fallback_reason
        if self.negatives:
            data["negatives"] = self.negatives
        if self.negative_hits:
            data["negative_hits"] = self.negative_hits
        return data


@dataclass(frozen=True)
class EvalReport:
    suite: str
    docs: str | None
    kb_names: list[str]
    top_k: int
    thresholds: EvalThresholds
    summary: EvalSummary
    cases: list[EvalCaseReport]
    config_snapshot: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "suite": self.suite,
            "docs": self.docs,
            "kb_names": self.kb_names,
            "top_k": self.top_k,
            "thresholds": self.thresholds.to_dict(),
            "summary": self.summary.to_dict(),
            "cases": [case.to_dict() for case in self.cases],
            "config_snapshot": self.config_snapshot,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)

    def write_json(self, path: str | Path) -> None:
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(self.to_json() + "\n", encoding="utf-8")


def expected_to_dict(expectation: ExpectedResult, fallback_id: str) -> dict[str, Any]:
    data: dict[str, Any] = {"id": expectation.id or fallback_id, "weight": expectation.weight}
    if expectation.source_file:
        data["source_file"] = expectation.source_file
    if expectation.header:
        data["header"] = expectation.header
    if expectation.anchor_key:
        data["anchor_key"] = expectation.anchor_key
    if expectation.text_contains:
        data["text_contains"] = list(expectation.text_contains)
    if expectation.metadata:
        data["metadata"] = dict(expectation.metadata)
    return data
