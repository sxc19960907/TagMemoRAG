#!/usr/bin/env python3
"""Summarize same-page ordering pressure from an existing eval report."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tagmemorag.same_page_ordering_diagnostic import (  # noqa: E402
    SamePageOrderingInputError,
    render_report,
    summarize_same_page_ordering,
    write_report,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--max-results", type=int, default=None)
    parser.add_argument("--near-tie-score-delta", type=float, default=0.05)
    args = parser.parse_args(argv)

    try:
        report = summarize_same_page_ordering(
            args.report,
            max_results=args.max_results,
            near_tie_score_delta=args.near_tie_score_delta,
        )
        if args.output is not None:
            write_report(report, args.output, fmt=args.format)
        else:
            print(render_report(report, fmt=args.format), end="")
        return 0
    except SamePageOrderingInputError as exc:
        print(f"same-page ordering diagnostic error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
