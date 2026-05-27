from __future__ import annotations

import json
from pathlib import Path
import sys

from .cli_helpers import split_csv
from .config import load_config
from .epa_basis import basis_path, load_epa_basis, retrain_if_needed
from .eval.answer_quality import run_answer_quality_diagnostics
from .eval.dataset import EvalSuiteError, EvalThresholds
from .eval.runner import run_eval
from .logging_setup import configure_logging
from .browser_qa_readiness import run_browser_qa_readiness
from .production_pilot import run_production_pilot, write_pilot_report
from .readiness import run_readiness_smoke


def run_eval_command(args) -> int:
    if args.command == "eval" and args.eval_command == "run":
        return _run_eval(args)
    if args.command == "eval" and args.eval_command == "answer-quality":
        return _run_answer_quality(args)
    if args.command == "readiness" and args.readiness_command == "smoke":
        report = run_readiness_smoke(workdir=args.workdir, keep_workdir=args.keep_workdir)
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
        return 0 if report.status == "passed" else 1
    if args.command == "readiness" and args.readiness_command == "browser-qa":
        report = run_browser_qa_readiness(full=args.full)
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
        if report.status == "passed":
            return 0
        return 2 if report.status == "error" else 1
    if args.command == "pilot" and args.pilot_command == "run":
        return _run_pilot(args)
    if args.command == "epa" and args.epa_command == "rebuild":
        return _run_epa(args)
    return 1


def _run_eval(args) -> int:
    cfg = load_config(args.config)
    configure_logging(cfg.logging.level, cfg.logging.format)
    thresholds = EvalThresholds(
        min_precision_at_k=args.min_precision_at_k,
        min_recall_at_k=args.min_recall_at_k,
        min_mrr=args.min_mrr,
        min_hit_at_k=args.min_hit_at_k,
    )
    if args.baseline:
        from .eval.runner import baseline_thresholds_for, load_baseline

        try:
            baseline = load_baseline(args.baseline)
        except EvalSuiteError as exc:
            print(f"eval error: {exc}", file=sys.stderr)
            return 2
        suite_name = Path(args.suite).name
        suite_metrics = baseline.get(suite_name)
        if suite_metrics is None:
            print(f"eval error: suite {suite_name!r} missing from baseline {args.baseline!r}", file=sys.stderr)
            return 2
        thresholds = baseline_thresholds_for(suite_metrics, case_thresholds=thresholds)
    try:
        report = run_eval(
            cfg=cfg,
            suite_path=args.suite,
            docs_path=args.docs,
            top_k=args.top_k,
            source_k=args.source_k,
            steps=args.steps,
            decay=args.decay,
            amplitude_cutoff=args.amplitude_cutoff,
            aggregate=args.aggregate,
            metadata_field_boost=args.metadata_field_boost,
            tag_boost=args.tag_boost,
            kb_filter=args.kb,
            force_mode=args.force_mode,
            reuse_built_kb=args.reuse_built_kb,
            eval_data_dir=args.eval_data_dir,
            thresholds=thresholds,
        )
    except EvalSuiteError as exc:
        print(f"eval error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"eval error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    if args.output:
        report.write_json(args.output)
    else:
        print(report.to_json())
    summary = report.summary
    print(
        "eval "
        f"{'passed' if summary.passed else 'failed'}: "
        f"cases={summary.cases} "
        f"precision@k={summary.metrics.precision_at_k:.6f} "
        f"recall@k={summary.metrics.recall_at_k:.6f} "
        f"mrr={summary.metrics.mrr:.6f} "
        f"hit@k={summary.metrics.hit_at_k:.6f}"
    )
    if not summary.passed:
        for case in report.cases:
            for failure in case.failures:
                print(f"- {case.id}: {failure}")
    return 0 if summary.passed else 1


def _run_answer_quality(args) -> int:
    try:
        report = run_answer_quality_diagnostics(args.suite)
    except EvalSuiteError as exc:
        print(f"answer-quality eval error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"answer-quality eval error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    if args.output:
        report.write_json(args.output)
    else:
        print(report.to_json())
    summary = report.summary
    print("answer-quality eval " f"{'passed' if summary.passed else 'failed'}: " f"cases={summary.cases}")
    if not summary.passed:
        for case in report.cases:
            for failure in case.failures:
                print(f"- {case.id}: {failure}")
    return 0 if summary.passed else 1


def _run_pilot(args) -> int:
    thresholds = EvalThresholds(
        min_recall_at_k=args.min_recall_at_k,
        min_mrr=args.min_mrr,
        min_hit_at_k=args.min_hit_at_k,
    )
    try:
        report = run_production_pilot(
            config_path=args.config,
            suite_path=args.suite,
            docs_path=args.docs,
            workdir=args.workdir,
            top_k=args.top_k,
            source_k=args.source_k,
            thresholds=thresholds,
            hashing_baseline_path=args.hashing_baseline,
            production_baseline_path=args.production_baseline,
            informational_suites=split_csv(args.informational_suites),
            accepted_suites=split_csv(args.accepted_suites),
            answer_quality_suite_path=args.answer_quality_suite,
            skip_answer_quality=args.skip_answer_quality,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"pilot error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    if args.output:
        write_pilot_report(report, args.output, fmt=args.format)
    else:
        if args.format == "markdown":
            print(report.to_markdown(), end="")
        else:
            print(report.to_json())
    return 1 if report.status == "failed" else 0


def _run_epa(args) -> int:
    cfg = load_config(args.config)
    configure_logging(cfg.logging.level, cfg.logging.format)
    report = retrain_if_needed(cfg, force=args.force)
    if report is None:
        current = load_epa_basis(basis_path(cfg))
        report = {
            "epa_basis_train_kind": current.train_kind if current is not None else "",
            "epa_basis_K": current.K if current is not None else 0,
            "epa_basis_tag_count": current.tag_count_at_train if current is not None else 0,
            "skipped": current is not None,
        }
    else:
        report = report | {"skipped": False}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0
