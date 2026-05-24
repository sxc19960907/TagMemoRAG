#!/usr/bin/env python3
"""Run context-pack quality diagnostics for real retrieval eval suites."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tagmemorag.eval.context_quality import run_context_quality_diagnostic  # noqa: E402
from tagmemorag.eval.dataset import EvalSuiteError  # noqa: E402
from tagmemorag.retrieval import DEFAULT_TOKEN_BUDGET  # noqa: E402

DEFAULT_CONFIG = REPO_ROOT / "examples" / "config" / "local-hashing-npz.yaml"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--docs", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--kb", required=True)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--source-k", type=int, default=None)
    parser.add_argument("--token-budget", type=int, default=DEFAULT_TOKEN_BUDGET)
    parser.add_argument("--eval-data-dir", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)

    try:
        report = run_context_quality_diagnostic(
            suite_path=args.suite,
            docs_path=args.docs,
            config_path=args.config,
            kb_name=args.kb,
            top_k=args.top_k,
            source_k=args.source_k,
            token_budget=args.token_budget,
            eval_data_dir=args.eval_data_dir,
        )
    except EvalSuiteError as exc:
        print(f"context-quality eval error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - diagnostics should fail cleanly.
        print(f"context-quality eval error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    summary = report["summary"]
    print(
        "context-quality eval complete: "
        f"cases={summary['cases']} "
        f"expected_selected={summary['cases_with_expected_selected']} "
        f"rate={summary['selected_expected_rate']:.6f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
