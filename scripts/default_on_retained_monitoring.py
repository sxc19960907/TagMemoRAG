#!/usr/bin/env python3
"""Summarize default-on retained RAG monitoring reports from a manifest."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tagmemorag.default_on_retained_monitoring import run_default_on_retained_monitoring, write_monitoring_report  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("examples/default-on-retained-monitoring.json"))
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    args = parser.parse_args(argv)

    report = run_default_on_retained_monitoring(args.manifest)
    if args.output:
        write_monitoring_report(report, args.output, fmt=args.format)
    else:
        print(report.to_markdown() if args.format == "markdown" else report.to_json(), end="")
    return 0 if report.status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
