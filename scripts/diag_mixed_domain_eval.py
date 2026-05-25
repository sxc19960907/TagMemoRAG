#!/usr/bin/env python3
"""Run the mixed-domain shared-KB retrieval diagnostic.

The default suite checks that real product-manual questions and public
documentation questions can coexist in one KB without top-ranked cross-domain
pollution. Unit tests use local fixture docs; operator validation can stage
real manuals plus previously seeded public-web docs with --stage-from-defaults.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tagmemorag.config import load_config  # noqa: E402
from tagmemorag.eval.dataset import EvalSuiteError, EvalThresholds  # noqa: E402
from tagmemorag.eval.runner import run_eval  # noqa: E402

DEFAULT_SUITE = REPO_ROOT / "tests" / "fixtures" / "eval" / "mixed_knowledge.jsonl"
DEFAULT_CONFIG = REPO_ROOT / "examples" / "config" / "local-hashing-npz.yaml"
DEFAULT_MANUAL_DOCS = REPO_ROOT / "product_manuals"
DEFAULT_PUBLIC_WEB_DOCS = REPO_ROOT / ".tmp" / "general-web-eval" / "general_web"
DEFAULT_KB = "mixed_knowledge"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    parser.add_argument("--docs", type=Path, default=None)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--kb", default=DEFAULT_KB)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--source-k", type=int, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--eval-data-dir", type=Path, default=None)
    parser.add_argument("--stage-from-defaults", action="store_true")
    parser.add_argument("--manual-docs", type=Path, default=DEFAULT_MANUAL_DOCS)
    parser.add_argument("--public-web-docs", type=Path, default=DEFAULT_PUBLIC_WEB_DOCS)
    args = parser.parse_args(argv)

    temp_dir: tempfile.TemporaryDirectory[str] | None = None
    try:
        docs_path = args.docs
        if args.stage_from_defaults:
            temp_dir = tempfile.TemporaryDirectory(prefix="mixed-domain-docs-")
            docs_path = stage_default_docs(
                destination=Path(temp_dir.name),
                manual_docs=args.manual_docs,
                public_web_docs=args.public_web_docs,
            )
        if docs_path is None:
            raise EvalSuiteError("--docs is required unless --stage-from-defaults is set")

        report = run_diagnostic(
            suite_path=args.suite,
            docs_path=docs_path,
            config_path=args.config,
            kb_name=args.kb,
            top_k=args.top_k,
            source_k=args.source_k,
            eval_data_dir=args.eval_data_dir,
        )
    except EvalSuiteError as exc:
        print(f"mixed-domain eval error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - diagnostics should fail cleanly.
        print(f"mixed-domain eval error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    finally:
        if temp_dir is not None:
            temp_dir.cleanup()

    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    summary = report["summary"]
    print(
        "mixed-domain eval "
        f"{'passed' if summary['passed'] else 'failed'}: "
        f"cases={summary['cases']} hit@k={summary['hit_at_k']:.6f} "
        f"mrr={summary['mrr']:.6f}"
    )
    if not summary["passed"]:
        for case in report["failed_cases"]:
            print(f"- {case['id']}: {', '.join(case['failures'])}")
    return 0 if summary["passed"] else 1


def run_diagnostic(
    *,
    suite_path: str | Path = DEFAULT_SUITE,
    docs_path: str | Path,
    config_path: str | Path = DEFAULT_CONFIG,
    kb_name: str = DEFAULT_KB,
    top_k: int = 5,
    source_k: int | None = None,
    eval_data_dir: str | Path | None = None,
) -> dict[str, Any]:
    docs = Path(docs_path)
    if not docs.exists():
        raise EvalSuiteError(f"docs path does not exist: {docs}")
    cfg = load_config(config_path)
    report = run_eval(
        cfg=cfg,
        suite_path=suite_path,
        docs_path=docs,
        top_k=top_k,
        source_k=source_k,
        kb_filter=kb_name,
        eval_data_dir=eval_data_dir,
        thresholds=EvalThresholds(min_recall_at_k=0.0, min_mrr=0.0, min_hit_at_k=0.0),
    )
    payload = report.to_dict()
    payload["schema_version"] = "mixed_domain_eval.v1"
    payload["failed_cases"] = [
        {"id": case.id, "failures": list(case.failures)}
        for case in report.cases
        if not case.passed and case.id != "__suite__"
    ]
    return payload


def stage_default_docs(
    *,
    destination: str | Path,
    manual_docs: str | Path = DEFAULT_MANUAL_DOCS,
    public_web_docs: str | Path = DEFAULT_PUBLIC_WEB_DOCS,
) -> Path:
    dest = Path(destination)
    dest.mkdir(parents=True, exist_ok=True)
    manual_root = Path(manual_docs)
    public_root = Path(public_web_docs)
    if not manual_root.exists():
        raise EvalSuiteError(f"manual docs path does not exist: {manual_root}")
    if not public_root.exists():
        raise EvalSuiteError(f"public web docs path does not exist: {public_root}")
    _copy_tree_files(manual_root, dest, suffixes={".pdf", ".json"})
    public_web = public_root / "public_web"
    if not public_web.exists():
        raise EvalSuiteError(f"public web docs path is missing public_web/: {public_root}")
    _copy_tree_files(public_web, dest / "public_web", suffixes={".md", ".json"})
    return dest


def _copy_tree_files(source_root: Path, dest_root: Path, *, suffixes: set[str]) -> None:
    for source in sorted(source_root.rglob("*")):
        if not source.is_file() or source.suffix.lower() not in suffixes:
            continue
        target = dest_root / source.relative_to(source_root)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


if __name__ == "__main__":
    raise SystemExit(main())
