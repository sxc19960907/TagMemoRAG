from __future__ import annotations

import json
import sys

from .cli_helpers import split_csv
from .eval.dataset import EvalThresholds
from .production_provider_smoke import run_production_provider_smoke, write_provider_smoke_report
from .production_provider_verify import DEFAULT_VERIFY_MANUAL, run_production_provider_verify, write_verify_report
from .provider_probe import run_provider_probe


def run_provider_command(args) -> int:
    if args.provider_command != "probe":
        return 1
    selected = []
    if args.all:
        selected.append("all")
    for name in ("embedding", "answer", "reranker", "qdrant", "s3"):
        if getattr(args, name):
            selected.append(name)
    report = run_provider_probe(args.config, selected=selected or ["all"], kb_name=args.kb)
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    return 1 if report.status == "failed" else 0


def run_production_provider_command(args) -> int:
    if args.production_provider_command == "smoke":
        return _run_production_provider_smoke(args)
    if args.production_provider_command == "verify":
        return _run_production_provider_verify(args)
    return 1


def _run_production_provider_smoke(args) -> int:
    try:
        report = run_production_provider_smoke(
            config_path=args.config,
            kb_name=args.kb,
            manual_paths=args.manual,
            metadata_path=args.metadata,
            metadata_format=args.metadata_format,
            workdir=args.workdir,
            question=args.question,
            rebuild_mode=args.rebuild_mode,
            answer_top_k=args.answer_top_k,
            answer_source_k=args.answer_source_k,
            reset_qdrant_collection=args.reset_qdrant_collection,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"production-provider smoke error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    if args.output:
        write_provider_smoke_report(report, args.output, fmt=args.format)
    else:
        if args.format == "markdown":
            print(report.to_markdown(), end="")
        else:
            print(report.to_json())
    return 1 if report.status == "failed" else 0


def _run_production_provider_verify(args) -> int:
    thresholds = EvalThresholds(
        min_recall_at_k=args.pilot_min_recall_at_k,
        min_mrr=args.pilot_min_mrr,
        min_hit_at_k=args.pilot_min_hit_at_k,
    )
    try:
        report = run_production_provider_verify(
            level=args.level,
            config_path=args.config,
            kb_name=args.kb,
            manual_paths=args.manual or [DEFAULT_VERIFY_MANUAL],
            metadata_path=args.metadata,
            metadata_format=args.metadata_format,
            workdir=args.workdir,
            output_path=args.output,
            output_format=args.format,
            question=args.question,
            start_docker=not args.skip_docker,
            ensure_bucket=not args.skip_bucket,
            reset_qdrant=not args.no_reset_qdrant,
            check_only=args.check_only,
            pilot_suite_path=args.pilot_suite,
            pilot_docs_path=args.pilot_docs,
            pilot_workdir=args.pilot_workdir,
            pilot_output_path=args.pilot_output,
            pilot_output_format=args.pilot_format,
            pilot_top_k=args.pilot_top_k,
            pilot_source_k=args.pilot_source_k,
            pilot_thresholds=thresholds,
            pilot_hashing_baseline_path=args.pilot_hashing_baseline,
            pilot_production_baseline_path=args.pilot_production_baseline,
            pilot_informational_suites=split_csv(args.pilot_informational_suites),
            pilot_accepted_suites=split_csv(args.pilot_accepted_suites),
        )
    except Exception as exc:  # noqa: BLE001
        print(f"production-provider verify error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    if args.verify_output:
        write_verify_report(report, args.verify_output, fmt=args.verify_format)
    if not args.verify_output:
        if args.verify_format == "markdown":
            print(report.to_markdown(), end="")
        else:
            print(report.to_json())
    return 1 if report.status == "failed" else 0
