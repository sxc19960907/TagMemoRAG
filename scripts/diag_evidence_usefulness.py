#!/usr/bin/env python3
"""Summarize bounded evidence-usefulness cues from an existing eval report."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tagmemorag.evidence_usefulness_diagnostic import (  # noqa: E402
    EvidenceUsefulnessInputError,
    render_report,
    summarize_evidence_usefulness,
    write_report,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--max-results", type=int, default=None)
    args = parser.parse_args(argv)

    try:
        report = summarize_evidence_usefulness(args.report, max_results=args.max_results)
        if args.output is not None:
            write_report(report, args.output, fmt=args.format)
        else:
            print(render_report(report, fmt=args.format), end="")
        return 0
    except EvidenceUsefulnessInputError as exc:
        print(f"evidence-usefulness diagnostic error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
