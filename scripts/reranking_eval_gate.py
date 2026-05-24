#!/usr/bin/env python3
"""Compare reranking candidate reports against the release-quality gate."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tagmemorag.reranking_eval_gate import (  # noqa: E402
    RerankingEvalGateInputError,
    run_reranking_eval_gate,
    write_reranking_eval_gate_report,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-readiness", required=True, type=Path)
    parser.add_argument("--candidate-readiness", required=True, type=Path)
    parser.add_argument("--baseline-ranking-pressure", required=True, type=Path)
    parser.add_argument("--candidate-ranking-pressure", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    args = parser.parse_args(argv)

    try:
        report = run_reranking_eval_gate(
            baseline_readiness_path=args.baseline_readiness,
            candidate_readiness_path=args.candidate_readiness,
            baseline_ranking_pressure_path=args.baseline_ranking_pressure,
            candidate_ranking_pressure_path=args.candidate_ranking_pressure,
        )
    except RerankingEvalGateInputError as exc:
        print(f"reranking-eval-gate error: {exc}", file=sys.stderr)
        return 2

    if args.output:
        write_reranking_eval_gate_report(report, args.output, fmt=args.format)
    elif args.format == "markdown":
        print(report.to_markdown(), end="")
    else:
        print(report.to_json())
    return 0 if report.status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
