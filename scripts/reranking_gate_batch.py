#!/usr/bin/env python3
"""Run the offline release-readiness plus reranking-gate batch."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tagmemorag.reranking_gate_batch import run_reranking_gate_batch  # noqa: E402
from tagmemorag.reranking_eval_gate import RerankingEvalGateInputError  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--general-web-ranking-pressure", type=Path, default=Path(".tmp/eval/general-web-ranking-pressure.json"))
    parser.add_argument("--baseline-readiness", type=Path, default=None)
    parser.add_argument("--candidate-readiness", type=Path, default=None)
    parser.add_argument("--baseline-ranking-pressure", type=Path, default=None)
    parser.add_argument("--candidate-ranking-pressure", type=Path, default=None)
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    args = parser.parse_args(argv)

    try:
        report = run_reranking_gate_batch(
            output_dir=args.output_dir,
            general_web_ranking_pressure_path=args.general_web_ranking_pressure,
            baseline_readiness_path=args.baseline_readiness,
            candidate_readiness_path=args.candidate_readiness,
            baseline_ranking_pressure_path=args.baseline_ranking_pressure,
            candidate_ranking_pressure_path=args.candidate_ranking_pressure,
            summary_format=args.format,
        )
    except RerankingEvalGateInputError as exc:
        print(f"reranking-gate-batch error: {exc}", file=sys.stderr)
        return 2
    print(report.to_markdown() if args.format == "markdown" else report.to_json(), end="")
    return 0 if report.status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
