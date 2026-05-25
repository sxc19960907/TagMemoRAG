#!/usr/bin/env python3
"""Summarize general-web eval cases where relevant evidence is under-ranked.

This script reads an existing `tagmemorag eval run --output` JSON report. It
does not run retrieval, fetch web pages, or edit fixtures. Output is bounded:
raw query text and raw result snippets are intentionally omitted.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tagmemorag.general_web_ranking_pressure import (  # noqa: E402
    RankingPressureInputError,
    render_report,
    summarize_ranking_pressure,
    write_report,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--max-results-after-match", type=int, default=0)
    args = parser.parse_args(argv)

    try:
        report = summarize_ranking_pressure(args.report, max_results_after_match=args.max_results_after_match)
        if args.output is not None:
            write_report(report, args.output, fmt=args.format)
        else:
            print(render_report(report, fmt=args.format), end="")
        return 0
    except RankingPressureInputError as exc:
        print(f"general-web ranking pressure error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
