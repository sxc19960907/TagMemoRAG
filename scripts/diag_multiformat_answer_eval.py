#!/usr/bin/env python3
"""Run live multi-format retrieval through the local answer diagnostic."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import diag_general_web_answer_eval as answer_diag  # noqa: E402


DEFAULT_SUITE = "tests/fixtures/eval/multiformat_real_knowledge.jsonl"
DEFAULT_DOCS = ".tmp/multiformat-real-knowledge/multiformat_real"
DEFAULT_CONFIG = "examples/config/local-hashing-npz.yaml"
DEFAULT_KB = "multiformat_real"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", default=DEFAULT_SUITE)
    parser.add_argument("--docs", default=DEFAULT_DOCS)
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--kb", default=DEFAULT_KB)
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--source-k", type=int, default=None)
    parser.add_argument("--token-budget", type=int, default=answer_diag.DEFAULT_TOKEN_BUDGET)
    parser.add_argument("--output", default=None)
    args = parser.parse_args(argv)

    try:
        report = answer_diag.run_diagnostic(
            suite_path=args.suite,
            docs_path=args.docs,
            config_path=args.config,
            kb_name=args.kb,
            top_k=args.top_k,
            source_k=args.source_k,
            token_budget=args.token_budget,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"multi-format answer eval error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    report["schema_version"] = "multiformat_answer_eval.v1"
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    summary = report["summary"]
    print(
        "multi-format answer eval "
        f"{'passed' if summary['passed'] else 'failed'}: "
        f"cases={summary['cases']} failed={summary['failed']}"
    )
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
