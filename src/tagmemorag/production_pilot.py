from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import tempfile
from typing import Any

from .config import load_config
from .config_validation import ConfigValidationReport, validate_config
from .eval.dataset import EvalSuiteError, EvalThresholds
from .eval.report import EvalReport
from .eval.runner import run_eval
from .provider_probe import ProviderProbeReport, run_provider_probe
from .readiness import SmokeReport, run_readiness_smoke

PILOT_SCHEMA_VERSION = "production_pilot.v1"
DEFAULT_PILOT_CONFIG = "examples/config/local-hashing-npz.yaml"
DEFAULT_PILOT_SUITE = "tests/fixtures/eval/coffee.jsonl"
DEFAULT_PILOT_DOCS = "tests/fixtures"
DEFAULT_PILOT_THRESHOLDS = EvalThresholds(min_recall_at_k=0.75, min_mrr=0.75, min_hit_at_k=0.8)


@dataclass(frozen=True)
class PilotStage:
    name: str
    status: str
    detail: dict[str, Any] = field(default_factory=dict)
    error: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name,
            "status": self.status,
            "detail": dict(self.detail),
        }
        if self.error is not None:
            payload["error"] = dict(self.error)
        return payload


@dataclass(frozen=True)
class ProductionPilotReport:
    status: str
    config_path: str
    suite_path: str
    docs_path: str | None
    workdir: str
    stages: list[PilotStage]
    next_steps: list[str]
    schema_version: str = PILOT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "config_path": self.config_path,
            "suite_path": self.suite_path,
            "docs_path": self.docs_path,
            "workdir": self.workdir,
            "stages": [stage.to_dict() for stage in self.stages],
            "next_steps": list(self.next_steps),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)

    def to_markdown(self) -> str:
        lines = [
            "# TagMemoRAG Production Pilot Report",
            "",
            f"- Status: `{self.status}`",
            f"- Config: `{self.config_path}`",
            f"- Suite: `{self.suite_path}`",
            f"- Docs: `{self.docs_path or ''}`",
            f"- Workdir: `{self.workdir}`",
            "",
            "| Stage | Status | Detail |",
            "| --- | --- | --- |",
        ]
        for stage in self.stages:
            detail = _compact_detail(stage.detail)
            if stage.error:
                detail = f"{detail}; error={stage.error.get('type', 'Error')}:{stage.error.get('reason', '')}".strip("; ")
            lines.append(f"| `{stage.name}` | `{stage.status}` | {detail} |")
        if self.next_steps:
            lines.extend(["", "## Next Steps"])
            lines.extend(f"- {step}" for step in self.next_steps)
        return "\n".join(lines) + "\n"


def run_production_pilot(
    *,
    config_path: str | Path = DEFAULT_PILOT_CONFIG,
    suite_path: str | Path = DEFAULT_PILOT_SUITE,
    docs_path: str | Path | None = DEFAULT_PILOT_DOCS,
    workdir: str | Path | None = None,
    top_k: int | None = None,
    source_k: int | None = None,
    thresholds: EvalThresholds = DEFAULT_PILOT_THRESHOLDS,
) -> ProductionPilotReport:
    pilot_workdir = _pilot_workdir(workdir)
    stages: list[PilotStage] = []

    config_report = validate_config(config_path)
    stages.append(_config_stage(config_report))

    provider_report = run_provider_probe(str(config_path), selected=["all"])
    stages.append(_provider_stage(provider_report))

    smoke_report = run_readiness_smoke(workdir=pilot_workdir / "readiness", keep_workdir=True)
    stages.append(_readiness_stage(smoke_report))

    try:
        cfg = load_config(config_path)
        eval_report = run_eval(
            cfg=cfg,
            suite_path=suite_path,
            docs_path=docs_path,
            top_k=top_k,
            source_k=source_k,
            eval_data_dir=pilot_workdir / "eval-data",
            thresholds=thresholds,
        )
        stages.append(_eval_stage(eval_report))
    except EvalSuiteError as exc:
        stages.append(
            PilotStage(
                "eval",
                "failed",
                {"suite": str(suite_path)},
                {"type": "EvalSuiteError", "reason": _safe_reason(str(exc))},
            )
        )
    except Exception as exc:  # noqa: BLE001
        stages.append(
            PilotStage(
                "eval",
                "failed",
                {"suite": str(suite_path)},
                {"type": type(exc).__name__, "reason": _safe_reason(str(exc))},
            )
        )

    status = _aggregate_status(stages)
    return ProductionPilotReport(
        status=status,
        config_path=str(config_path),
        suite_path=str(suite_path),
        docs_path=str(docs_path) if docs_path is not None else None,
        workdir=str(pilot_workdir),
        stages=stages,
        next_steps=_next_steps(status, stages),
    )


def write_pilot_report(report: ProductionPilotReport, path: str | Path, *, fmt: str = "json") -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "json":
        text = report.to_json()
    elif fmt == "markdown":
        text = report.to_markdown()
    else:
        raise ValueError("fmt must be 'json' or 'markdown'")
    output_path.write_text(text + ("" if text.endswith("\n") else "\n"), encoding="utf-8")


def _pilot_workdir(workdir: str | Path | None) -> Path:
    if workdir is not None:
        path = Path(workdir).expanduser().resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path
    return Path(tempfile.mkdtemp(prefix="tagmemorag-pilot-")).resolve()


def _config_stage(report: ConfigValidationReport) -> PilotStage:
    checks = _count_statuses([check.status for check in report.checks])
    return PilotStage(
        "config_validate",
        report.status,
        {
            "profile": dict(report.profile),
            "checks": checks,
        },
    )


def _provider_stage(report: ProviderProbeReport) -> PilotStage:
    return PilotStage(
        "provider_probe",
        report.status,
        {
            "probes": _count_statuses([probe.status for probe in report.probes]),
            "names": [probe.name for probe in report.probes],
        },
    )


def _readiness_stage(report: SmokeReport) -> PilotStage:
    return PilotStage(
        "readiness_smoke",
        report.status,
        {
            "checks": _count_statuses([check.status for check in report.checks]),
            "workdir": report.workdir,
        },
        _first_error([check.to_dict() for check in report.checks]),
    )


def _eval_stage(report: EvalReport) -> PilotStage:
    summary = report.summary
    return PilotStage(
        "eval",
        "passed" if summary.passed else "failed",
        {
            "suite": Path(report.suite).name,
            "cases": summary.cases,
            "top_k": report.top_k,
            "thresholds": report.thresholds.to_dict(),
            "metrics": summary.metrics.to_dict(),
            "failed_cases": [case.id for case in report.cases if not case.passed],
            "kb_names": list(report.kb_names),
        },
        _first_error([{"error": {"type": "EvalThreshold", "reason": "; ".join(case.failures)}} for case in report.cases if case.failures]),
    )


def _aggregate_status(stages: list[PilotStage]) -> str:
    statuses = {stage.status for stage in stages}
    if "failed" in statuses:
        return "failed"
    if "warning" in statuses:
        return "warning"
    return "passed"


def _next_steps(status: str, stages: list[PilotStage]) -> list[str]:
    if status == "failed":
        failed = ", ".join(stage.name for stage in stages if stage.status == "failed")
        return [
            f"Investigate failed stage(s): {failed}.",
            "Rerun the individual command for the failing stage with the same config before opening pilot traffic.",
        ]
    if status == "warning":
        return [
            "Review warning stages and decide whether they are acceptable for this pilot profile.",
            "Retain the pilot report and workdir artifacts with the rollout record.",
        ]
    return [
        "Retain the pilot report and workdir artifacts with the rollout record.",
        "Run profile-specific live provider probes before using remote embedding, reranker, answer, Qdrant, or S3 services.",
        "Use eval baseline gates for stricter retrieval regression checks.",
    ]


def _count_statuses(statuses: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for status in statuses:
        counts[status] = counts.get(status, 0) + 1
    return counts


def _first_error(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    for item in items:
        error = item.get("error")
        if isinstance(error, dict):
            return {"type": str(error.get("type") or "Error"), "reason": _safe_reason(str(error.get("reason") or ""))}
    return None


def _safe_reason(reason: str) -> str:
    value = " ".join(str(reason or "").split())
    return value[:160] or "production_pilot_failed"


def _compact_detail(detail: dict[str, Any]) -> str:
    parts = []
    for key, value in detail.items():
        if isinstance(value, dict):
            rendered = json.dumps(value, ensure_ascii=False, sort_keys=True)
        elif isinstance(value, list):
            rendered = ", ".join(str(item) for item in value)
        else:
            rendered = str(value)
        parts.append(f"{key}={rendered}")
    return "<br>".join(parts)


__all__ = [
    "DEFAULT_PILOT_CONFIG",
    "DEFAULT_PILOT_DOCS",
    "DEFAULT_PILOT_SUITE",
    "DEFAULT_PILOT_THRESHOLDS",
    "PILOT_SCHEMA_VERSION",
    "PilotStage",
    "ProductionPilotReport",
    "run_production_pilot",
    "write_pilot_report",
]
