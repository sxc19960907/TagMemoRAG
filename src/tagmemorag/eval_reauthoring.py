from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "eval_reauthoring_diagnosis.v1"
METRIC_NAMES = ("precision_at_k", "recall_at_k", "mrr", "hit_at_k")


@dataclass(frozen=True)
class SuiteDiagnosis:
    suite: str
    status: str
    severity: int
    hashing: dict[str, float] = field(default_factory=dict)
    production: dict[str, float] = field(default_factory=dict)
    delta: dict[str, float] = field(default_factory=dict)
    recommendation: str = ""
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "suite": self.suite,
            "status": self.status,
            "severity": self.severity,
            "hashing": dict(self.hashing),
            "production": dict(self.production),
            "delta": dict(self.delta),
            "recommendation": self.recommendation,
            "reasons": list(self.reasons),
        }

    def to_summary_dict(self) -> dict[str, Any]:
        return {
            "suite": self.suite,
            "status": self.status,
            "severity": self.severity,
            "recommendation": self.recommendation,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class DiagnosisReport:
    hashing_baseline: str
    production_baseline: str
    hashing_embedder: str
    production_embedder: str
    suites: list[SuiteDiagnosis]
    schema_version: str = SCHEMA_VERSION

    def summary(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for suite in self.suites:
            counts[suite.status] = counts.get(suite.status, 0) + 1
        return {
            "suite_count": len(self.suites),
            "status_counts": counts,
            "highest_severity": max((suite.severity for suite in self.suites), default=0),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "hashing_baseline": self.hashing_baseline,
            "production_baseline": self.production_baseline,
            "hashing_embedder": self.hashing_embedder,
            "production_embedder": self.production_embedder,
            "summary": self.summary(),
            "suites": [suite.to_dict() for suite in self.suites],
        }

    def to_stage_detail(self, *, limit: int = 5) -> dict[str, Any]:
        summary = self.summary()
        return {
            "schema_version": self.schema_version,
            "hashing_embedder": self.hashing_embedder,
            "production_embedder": self.production_embedder,
            "suite_count": summary["suite_count"],
            "status_counts": dict(summary["status_counts"]),
            "highest_severity": summary["highest_severity"],
            "top_suites": [suite.to_summary_dict() for suite in self.suites[:limit]],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)

    def to_markdown(self) -> str:
        lines = [
            "# Eval Reauthoring Diagnosis",
            "",
            f"- Hashing baseline: `{self.hashing_baseline}`",
            f"- Production baseline: `{self.production_baseline}`",
            f"- Embedder comparison: `{self.production_embedder}` minus `{self.hashing_embedder}`",
            "",
            "| Suite | Status | Severity | Recall Δ | MRR Δ | Hit Δ | Recommendation |",
            "| --- | --- | ---: | ---: | ---: | ---: | --- |",
        ]
        for suite in self.suites:
            lines.append(
                "| "
                f"`{suite.suite}` | "
                f"`{suite.status}` | "
                f"{suite.severity} | "
                f"{_format_delta(suite.delta.get('recall_at_k'))} | "
                f"{_format_delta(suite.delta.get('mrr'))} | "
                f"{_format_delta(suite.delta.get('hit_at_k'))} | "
                f"{suite.recommendation} |"
            )
        return "\n".join(lines) + "\n"


class DiagnosisInputError(ValueError):
    """Raised when a baseline cannot produce a valid diagnosis."""


def diagnose_reauthoring(
    hashing_baseline: str | Path,
    production_baseline: str | Path,
) -> DiagnosisReport:
    hashing_path = Path(hashing_baseline)
    production_path = Path(production_baseline)
    hashing_payload = _load_baseline(hashing_path)
    production_payload = _load_baseline(production_path)
    hashing_suites = _suite_metrics(hashing_payload, hashing_path)
    production_suites = _suite_metrics(production_payload, production_path)
    suite_names = sorted(set(hashing_suites) | set(production_suites))
    diagnoses = [
        classify_suite(
            suite,
            hashing_suites.get(suite),
            production_suites.get(suite),
        )
        for suite in suite_names
    ]
    diagnoses.sort(key=lambda item: (-item.severity, item.suite))
    return DiagnosisReport(
        hashing_baseline=str(hashing_path),
        production_baseline=str(production_path),
        hashing_embedder=str(hashing_payload.get("embedder") or "hashing"),
        production_embedder=str(production_payload.get("embedder") or "production"),
        suites=diagnoses,
    )


def classify_suite(
    suite: str,
    hashing_metrics: dict[str, float] | None,
    production_metrics: dict[str, float] | None,
) -> SuiteDiagnosis:
    if hashing_metrics is None:
        return SuiteDiagnosis(
            suite=suite,
            status="investigate",
            severity=3,
            production=_round_metrics(production_metrics or {}),
            recommendation="Add this suite to the hashing baseline or explain why it is production-only.",
            reasons=["suite_missing_from_hashing_baseline"],
        )
    if production_metrics is None:
        return SuiteDiagnosis(
            suite=suite,
            status="investigate",
            severity=3,
            hashing=_round_metrics(hashing_metrics),
            recommendation="Refresh the production baseline so this suite is represented.",
            reasons=["suite_missing_from_production_baseline"],
        )
    hashing = _round_metrics(hashing_metrics)
    production = _round_metrics(production_metrics)
    missing = [metric for metric in METRIC_NAMES if metric not in hashing or metric not in production]
    if missing:
        return SuiteDiagnosis(
            suite=suite,
            status="investigate",
            severity=3,
            hashing=hashing,
            production=production,
            recommendation="Regenerate baselines; required metric fields are missing.",
            reasons=[f"missing_metric:{metric}" for metric in missing],
        )

    delta = _round_metrics({metric: production[metric] - hashing[metric] for metric in METRIC_NAMES})
    status, severity, recommendation, reasons = _classify_metrics(production, delta)
    return SuiteDiagnosis(
        suite=suite,
        status=status,
        severity=severity,
        hashing=hashing,
        production=production,
        delta=delta,
        recommendation=recommendation,
        reasons=reasons,
    )


def _classify_metrics(production: dict[str, float], delta: dict[str, float]) -> tuple[str, int, str, list[str]]:
    reasons: list[str] = []
    if production["hit_at_k"] < 0.5:
        reasons.append("production_hit_at_k_below_0.5")
    if production["recall_at_k"] < 0.5:
        reasons.append("production_recall_at_k_below_0.5")
    if reasons:
        return (
            "investigate",
            3,
            "Investigate retrieval/model mismatch before reauthoring fixture expectations.",
            reasons,
        )

    if delta["recall_at_k"] <= -0.25:
        reasons.append("recall_delta_lte_-0.25")
    if delta["mrr"] <= -0.25:
        reasons.append("mrr_delta_lte_-0.25")
    if reasons:
        return (
            "reauthor",
            2,
            "Review expected chunks against production-embedder rankings and reauthor fixture cases if justified.",
            reasons,
        )

    if delta["recall_at_k"] <= -0.10:
        reasons.append("recall_delta_lte_-0.10")
    if delta["mrr"] <= -0.10:
        reasons.append("mrr_delta_lte_-0.10")
    if reasons:
        return (
            "monitor",
            1,
            "Monitor divergence; reauthor only if case-level inspection confirms stale expectations.",
            reasons,
        )

    return (
        "ok",
        0,
        "No immediate fixture reauthoring indicated by aggregate baseline metrics.",
        ["production_metrics_close_to_hashing"],
    )


def _load_baseline(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise DiagnosisInputError(f"baseline file not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DiagnosisInputError(f"baseline file {path} is not valid JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise DiagnosisInputError(f"baseline file {path} must contain a JSON object")
    return payload


def _suite_metrics(payload: dict[str, Any], path: Path) -> dict[str, dict[str, float]]:
    suites = payload.get("suites")
    if not isinstance(suites, dict):
        raise DiagnosisInputError(f"baseline file {path} is missing the 'suites' object")
    parsed: dict[str, dict[str, float]] = {}
    for suite, metrics in suites.items():
        if not isinstance(metrics, dict):
            raise DiagnosisInputError(f"baseline file {path} suite {suite!r} metrics must be an object")
        parsed[str(suite)] = {str(metric): float(value) for metric, value in metrics.items()}
    return parsed


def _round_metrics(metrics: dict[str, float]) -> dict[str, float]:
    return {key: round(float(value), 6) for key, value in metrics.items()}


def _format_delta(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{float(value):+.6f}"
