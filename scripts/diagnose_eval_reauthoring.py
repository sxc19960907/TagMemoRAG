"""Diagnose eval fixture reauthoring priority across embedder baselines.

The report compares the deterministic hashing CI baseline with an
informational production-embedder baseline (currently SiliconFlow) and ranks
which suites need human fixture review first. It is offline and never calls an
embedding provider.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tagmemorag.eval_reauthoring import (  # noqa: E402
    DiagnosisInputError,
    DiagnosisReport,
    SuiteDiagnosis,
    classify_suite,
    diagnose_reauthoring as _diagnose_reauthoring,
)

DEFAULT_HASHING_BASELINE = REPO_ROOT / "tests" / "fixtures" / "eval" / "baselines" / "hashing.json"
DEFAULT_PRODUCTION_BASELINE = REPO_ROOT / "tests" / "fixtures" / "eval" / "baselines" / "siliconflow.json"
SCHEMA_VERSION = "eval_reauthoring_diagnosis.v1"


def diagnose_reauthoring(
    hashing_baseline: str | Path = DEFAULT_HASHING_BASELINE,
    production_baseline: str | Path = DEFAULT_PRODUCTION_BASELINE,
    *,
    informational_suites: Iterable[str] | None = None,
    accepted_suites: Iterable[str] | None = None,
) -> DiagnosisReport:
    return _diagnose_reauthoring(
        hashing_baseline,
        production_baseline,
        informational_suites=informational_suites,
        accepted_suites=accepted_suites,
    )


def write_report(report: DiagnosisReport, output: str | Path, *, fmt: str) -> None:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_report(report, fmt=fmt), encoding="utf-8")


def render_report(report: DiagnosisReport, *, fmt: str) -> str:
    if fmt == "json":
        return report.to_json() + "\n"
    if fmt == "markdown":
        return report.to_markdown()
    raise DiagnosisInputError("format must be 'json' or 'markdown'")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hashing-baseline", type=Path, default=DEFAULT_HASHING_BASELINE)
    parser.add_argument("--production-baseline", type=Path, default=DEFAULT_PRODUCTION_BASELINE)
    parser.add_argument(
        "--informational-suites",
        default="",
        help="Comma-separated suite filenames whose diagnosis is informational and does not count as blocking.",
    )
    parser.add_argument(
        "--accepted-suites",
        default="",
        help="Comma-separated suite filenames whose diagnosis has been reviewed and accepted as non-blocking.",
    )
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)

    try:
        report = diagnose_reauthoring(
            args.hashing_baseline,
            args.production_baseline,
            informational_suites=_split_csv(args.informational_suites),
            accepted_suites=_split_csv(args.accepted_suites),
        )
        rendered = render_report(report, fmt=args.format)
        if args.output is not None:
            write_report(report, args.output, fmt=args.format)
        else:
            print(rendered, end="")
        return 0
    except DiagnosisInputError as exc:
        print(f"diagnose eval reauthoring error: {exc}", file=sys.stderr)
        return 2


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


__all__ = [
    "DEFAULT_HASHING_BASELINE",
    "DEFAULT_PRODUCTION_BASELINE",
    "SCHEMA_VERSION",
    "DiagnosisInputError",
    "DiagnosisReport",
    "SuiteDiagnosis",
    "classify_suite",
    "diagnose_reauthoring",
    "render_report",
    "write_report",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
