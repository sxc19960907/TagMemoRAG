"""Run a bounded production-environment verification report.

The default mode is deterministic/local: config validation, readiness smoke,
and pilot report. Live provider probes run only when explicitly requested with
`--probe`.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tagmemorag.config_validation import validate_config  # noqa: E402
from tagmemorag.eval.dataset import EvalThresholds  # noqa: E402
from tagmemorag.production_pilot import (  # noqa: E402
    DEFAULT_PILOT_THRESHOLDS,
    run_production_pilot,
)
from tagmemorag.provider_probe import PROBE_NAMES, run_provider_probe  # noqa: E402
from tagmemorag.readiness import run_readiness_smoke  # noqa: E402

SCHEMA_VERSION = "production_verification.v1"
DEFAULT_CONFIG = "examples/config/local-hashing-npz.yaml"
DEFAULT_SUITE = "tests/fixtures/eval/coffee.jsonl"
DEFAULT_DOCS = "tests/fixtures"
DEFAULT_WORKDIR = ".tmp/production-verification"
DEFAULT_HASHING_BASELINE = "tests/fixtures/eval/baselines/hashing.json"
DEFAULT_PRODUCTION_BASELINE = "tests/fixtures/eval/baselines/siliconflow.json"
DEFAULT_INFORMATIONAL_SUITES = (
    "cross_kb_negatives.jsonl",
    "fault_codes.jsonl",
    "model_numbers.jsonl",
    "tag_cooccurrence.jsonl",
)
DEFAULT_ACCEPTED_SUITES = (
    "product_manuals.jsonl",
    "mixed_language.jsonl",
    "tag_rerank_edge.jsonl",
)


@dataclass(frozen=True)
class VerificationStep:
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
class VerificationReport:
    status: str
    config_path: str
    workdir: str
    steps: list[VerificationStep]
    next_steps: list[str]
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "config_path": self.config_path,
            "workdir": self.workdir,
            "steps": [step.to_dict() for step in self.steps],
            "next_steps": list(self.next_steps),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)

    def to_markdown(self) -> str:
        lines = [
            "# Production Environment Verification",
            "",
            f"- Status: `{self.status}`",
            f"- Config: `{self.config_path}`",
            f"- Workdir: `{self.workdir}`",
            "",
            "| Step | Status | Detail |",
            "| --- | --- | --- |",
        ]
        for step in self.steps:
            detail = _compact_detail(step.detail)
            if step.error:
                detail = f"{detail}; error={step.error.get('type', 'Error')}:{step.error.get('reason', '')}".strip("; ")
            lines.append(f"| `{step.name}` | `{step.status}` | {detail} |")
        if self.next_steps:
            lines.extend(["", "## Next Steps"])
            lines.extend(f"- {step}" for step in self.next_steps)
        return "\n".join(lines) + "\n"


def run_verification(
    *,
    config_path: str | Path = DEFAULT_CONFIG,
    suite_path: str | Path = DEFAULT_SUITE,
    docs_path: str | Path | None = DEFAULT_DOCS,
    workdir: str | Path = DEFAULT_WORKDIR,
    probes: list[str] | None = None,
    hashing_baseline_path: str | Path | None = DEFAULT_HASHING_BASELINE,
    production_baseline_path: str | Path | None = DEFAULT_PRODUCTION_BASELINE,
    informational_suites: list[str] | None = None,
    accepted_suites: list[str] | None = None,
    thresholds: EvalThresholds = DEFAULT_PILOT_THRESHOLDS,
) -> VerificationReport:
    report_dir = _run_workdir(workdir)
    report_dir.mkdir(parents=True, exist_ok=True)
    steps: list[VerificationStep] = []

    config_report = validate_config(config_path)
    steps.append(
        VerificationStep(
            "config_validate",
            config_report.status,
            {
                "profile": dict(config_report.profile),
                "checks": _count_statuses([check.status for check in config_report.checks]),
            },
            _first_check_error(config_report.to_dict().get("checks") or []),
        )
    )

    selected_probes = _normalize_probes(probes or [])
    if selected_probes:
        probe_report = run_provider_probe(str(config_path), selected=selected_probes)
        steps.append(
            VerificationStep(
                "provider_probe",
                probe_report.status,
                {
                    "selected": selected_probes,
                    "probes": _count_statuses([probe.status for probe in probe_report.probes]),
                    "names": [probe.name for probe in probe_report.probes],
                },
                _first_check_error([probe.to_dict() for probe in probe_report.probes]),
            )
        )
    else:
        steps.append(
            VerificationStep(
                "provider_probe",
                "skipped",
                {"selected": [], "reason": "live_provider_probes_require_explicit_probe_option"},
            )
        )

    smoke_report = run_readiness_smoke(workdir=report_dir / "readiness", keep_workdir=True)
    steps.append(
        VerificationStep(
            "readiness_smoke",
            smoke_report.status,
            {
                "checks": _count_statuses([check.status for check in smoke_report.checks]),
                "workdir": smoke_report.workdir,
            },
            _first_check_error([check.to_dict() for check in smoke_report.checks]),
        )
    )

    pilot_report = run_production_pilot(
        config_path=config_path,
        suite_path=suite_path,
        docs_path=docs_path,
        workdir=report_dir / "pilot",
        thresholds=thresholds,
        hashing_baseline_path=hashing_baseline_path,
        production_baseline_path=production_baseline_path,
        informational_suites=informational_suites if informational_suites is not None else list(DEFAULT_INFORMATIONAL_SUITES),
        accepted_suites=accepted_suites if accepted_suites is not None else list(DEFAULT_ACCEPTED_SUITES),
    )
    steps.append(
        VerificationStep(
            "pilot_run",
            pilot_report.status,
            {
                "stages": _count_statuses([stage.status for stage in pilot_report.stages]),
                "workdir": pilot_report.workdir,
                "suite": Path(str(suite_path)).name,
            },
            _first_check_error([stage.to_dict() for stage in pilot_report.stages]),
        )
    )

    status = _aggregate_status(steps)
    return VerificationReport(
        status=status,
        config_path=str(config_path),
        workdir=str(report_dir),
        steps=steps,
        next_steps=_next_steps(status, steps),
    )


def render_report(report: VerificationReport, *, fmt: str) -> str:
    if fmt == "json":
        return report.to_json() + "\n"
    if fmt == "markdown":
        return report.to_markdown()
    raise ValueError("format must be 'json' or 'markdown'")


def write_report(report: VerificationReport, output: str | Path, *, fmt: str) -> None:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_report(report, fmt=fmt), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--suite", default=DEFAULT_SUITE)
    parser.add_argument("--docs", default=DEFAULT_DOCS)
    parser.add_argument("--workdir", default=DEFAULT_WORKDIR)
    parser.add_argument("--output", default=None)
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    parser.add_argument("--probe", action="append", choices=(*PROBE_NAMES, "all"), default=[])
    parser.add_argument("--hashing-baseline", default=DEFAULT_HASHING_BASELINE)
    parser.add_argument("--production-baseline", default=DEFAULT_PRODUCTION_BASELINE)
    parser.add_argument("--informational-suites", default=",".join(DEFAULT_INFORMATIONAL_SUITES))
    parser.add_argument("--accepted-suites", default=",".join(DEFAULT_ACCEPTED_SUITES))
    args = parser.parse_args(argv)

    try:
        report = run_verification(
            config_path=args.config,
            suite_path=args.suite,
            docs_path=args.docs,
            workdir=args.workdir,
            probes=args.probe,
            hashing_baseline_path=args.hashing_baseline,
            production_baseline_path=args.production_baseline,
            informational_suites=_split_csv(args.informational_suites),
            accepted_suites=_split_csv(args.accepted_suites),
        )
    except Exception as exc:  # noqa: BLE001
        print(f"production verification error: {type(exc).__name__}: {_safe_reason(str(exc))}", file=sys.stderr)
        return 2

    if args.output:
        write_report(report, args.output, fmt=args.format)
    else:
        print(render_report(report, fmt=args.format), end="")
    return 1 if report.status == "failed" else 0


def _normalize_probes(probes: list[str]) -> list[str]:
    selected: list[str] = []
    for probe in probes:
        for item in str(probe).split(","):
            value = item.strip()
            if value and value not in selected:
                selected.append(value)
    if "all" in selected:
        return ["all"]
    return [probe for probe in selected if probe in PROBE_NAMES]


def _run_workdir(workdir: str | Path) -> Path:
    path = Path(workdir).expanduser()
    if path.name == "production-verification":
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        path = path / stamp
    return path.resolve()


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def _count_statuses(statuses: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for status in statuses:
        counts[status] = counts.get(status, 0) + 1
    return counts


def _first_check_error(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    for item in items:
        error = item.get("error")
        if isinstance(error, dict):
            return {"type": str(error.get("type") or "Error"), "reason": _safe_reason(str(error.get("reason") or ""))}
        if item.get("status") == "failed":
            return {"type": str(item.get("name") or "FailedStep"), "reason": _safe_reason(str(item.get("message") or "step_failed"))}
    return None


def _aggregate_status(steps: list[VerificationStep]) -> str:
    required_statuses = {step.status for step in steps if step.name != "provider_probe" or step.status != "skipped"}
    if "failed" in required_statuses:
        return "failed"
    if "warning" in required_statuses:
        return "warning"
    return "passed"


def _next_steps(status: str, steps: list[VerificationStep]) -> list[str]:
    if status == "failed":
        failed = ", ".join(step.name for step in steps if step.status == "failed")
        return [
            f"Investigate failed verification step(s): {failed}.",
            "Do not open pilot traffic until failed required steps pass or have an explicit rollback decision.",
        ]
    if status == "warning":
        return [
            "Review warning steps and attach owner signoff before pilot traffic.",
            "Retain the verification report directory with the rollout record.",
        ]
    return [
        "Retain the verification report directory with the rollout record.",
        "Run explicit live provider probes for any remote providers not checked in this report.",
        "Proceed to service-level health, ready, metrics, and managed-library checks from the runbook.",
    ]


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


def _safe_reason(reason: str) -> str:
    value = " ".join(str(reason or "").split())
    return value[:160] or "production_verification_failed"


__all__ = [
    "SCHEMA_VERSION",
    "VerificationReport",
    "VerificationStep",
    "render_report",
    "run_verification",
    "write_report",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
