#!/usr/bin/env python3
"""Summarize release readiness from retained real-data RAG quality reports."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tagmemorag.release_readiness import DEFAULT_REPORT_PATHS, run_release_readiness, write_release_readiness_report  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    parser.add_argument(
        "--report",
        action="append",
        default=[],
        help="Override a report path as name=path. May be repeated.",
    )
    args = parser.parse_args(argv)

    paths = dict(DEFAULT_REPORT_PATHS)
    for override in args.report:
        if "=" not in override:
            print(f"release-readiness error: invalid --report override {override!r}; expected name=path", file=sys.stderr)
            return 2
        name, path = override.split("=", 1)
        paths[name.strip()] = path.strip()

    report = run_release_readiness(report_paths=paths)
    if args.output:
        write_release_readiness_report(report, args.output, fmt=args.format)
    else:
        if args.format == "markdown":
            print(report.to_markdown(), end="")
        else:
            print(report.to_json())
    return 1 if report.status == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
