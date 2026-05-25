#!/usr/bin/env python3
"""Run an offline same-page ordering candidate dry run."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tagmemorag.same_page_ordering_candidate import (  # noqa: E402
    SamePageOrderingCandidateInputError,
    render_report,
    run_same_page_ordering_candidate,
    write_candidate_ranking_pressure,
    write_report,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--candidate-ranking-pressure-output", type=Path, default=None)
    parser.add_argument("--max-results", type=int, default=None)
    parser.add_argument("--dominance-threshold", type=int, default=2)
    args = parser.parse_args(argv)

    try:
        report = run_same_page_ordering_candidate(
            args.report,
            max_results=args.max_results,
            dominance_threshold=args.dominance_threshold,
        )
        if args.output is not None:
            write_report(report, args.output, fmt=args.format)
        else:
            print(render_report(report, fmt=args.format), end="")
        if args.candidate_ranking_pressure_output is not None:
            write_candidate_ranking_pressure(report, args.candidate_ranking_pressure_output)
        return 0 if report.status != "failed" else 1
    except SamePageOrderingCandidateInputError as exc:
        print(f"same-page candidate error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
