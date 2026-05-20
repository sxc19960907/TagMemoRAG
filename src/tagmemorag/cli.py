from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import secrets
import sys
import time

import uvicorn

from .config import load_config
from .auth.config_store import ConfigAuthStore
from .config_validation import validate_config
from .embedder import create_embedder
from .epa_basis import retrain_if_needed, basis_path, load_epa_basis
from .eval.dataset import EvalSuiteError, EvalThresholds
from .eval.runner import run_eval
from .logging_setup import configure_logging
from .manual_bundle import export_bundle, import_bundle, inspect_bundle
from .manual_bulk_import import BulkUploadedFile, commit_bulk_import, preview_bulk_import
from .manual_library import build_dirty_state_report, migrate_sidecars_to_registry, registry_inspect, verify_registry_blobs
from .metadata_narrowing import infer_metadata_narrowing, merge_inferred_filters
from .provider_probe import run_provider_probe
from .qdrant_ops import inspect_qdrant
from .readiness import run_readiness_smoke
from .rebuild_queue import RebuildQueue
from .retrieval_feedback import (
    create_feedback,
    export_eval_promotion,
    list_feedback,
    preview_eval_promotion,
    review_feedback,
)
from .search_runtime import execute_search, search_ann_enabled, search_debug_enabled, search_debug_payload
from .state import AppState, build_kb, load_kb, save_kb, start_library_rebuild
from .tag_governance import (
    commit_tag_rewrite,
    load_tag_policy,
    resolve_tags_for_search,
    save_tag_policy,
    tag_usage_report,
    preview_tag_rewrite,
)
from .manual_registry import create_registry
from .production_pilot import (
    DEFAULT_PILOT_CONFIG,
    DEFAULT_PILOT_DOCS,
    DEFAULT_PILOT_SUITE,
    DEFAULT_PILOT_THRESHOLDS,
    run_production_pilot,
    write_pilot_report,
)
from .production_provider_smoke import (
    DEFAULT_PROVIDER_SMOKE_CONFIG,
    DEFAULT_PROVIDER_SMOKE_QUESTION,
    run_production_provider_smoke,
    write_provider_smoke_report,
)
from .tag_cooccurrence import cooccurrence_path, load_cooccurrence
from .tag_intrinsic_residuals import train_intrinsic_residuals_for_kb


def _create_embedder_from_config(cfg):
    return create_embedder(
        cfg.model.name,
        cfg.model.device,
        cfg.model.batch_size,
        cfg.model.dim,
        provider=cfg.model.provider,
        base_url=cfg.model.base_url,
        embeddings_url=cfg.model.embeddings_url,
        api_key_env=cfg.model.api_key_env,
        timeout_seconds=cfg.model.timeout_seconds,
        dimensions=cfg.model.dimensions,
        normalize=cfg.model.normalize,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tagmemorag")
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build")
    build.add_argument("--docs", required=True)
    build.add_argument("--kb", default="default")
    build.add_argument("--config", default="config.yaml")

    search = sub.add_parser("search")
    search.add_argument("question")
    search.add_argument("--kb", default="default")
    search.add_argument("--top-k", type=int, default=None)
    search.add_argument("--config", default="config.yaml")
    search.add_argument("--brand", default=None)
    search.add_argument("--category", default=None)
    search.add_argument("--model", default=None)
    search.add_argument("--language", default=None)
    search.add_argument("--tag", action="append", default=[])
    search.add_argument("--debug-search", action="store_true")

    serve = sub.add_parser("serve")
    serve.add_argument("--host", default=None)
    serve.add_argument("--port", type=int, default=None)
    serve.add_argument("--config", default="config.yaml")

    config_cmd = sub.add_parser("config")
    config_sub = config_cmd.add_subparsers(dest="config_command", required=True)
    config_validate = config_sub.add_parser("validate")
    config_validate.add_argument("--config", default="config.yaml")
    config_validate.add_argument("--format", choices=["json"], default="json")

    residuals = sub.add_parser("retrain-residuals")
    residuals.add_argument("--kb", default="default")
    residuals.add_argument("--config", default="config.yaml")

    eval_parser = sub.add_parser("eval")
    eval_sub = eval_parser.add_subparsers(dest="eval_command", required=True)
    eval_run = eval_sub.add_parser("run")
    eval_run.add_argument("--suite", required=True)
    eval_run.add_argument("--docs", default=None)
    eval_run.add_argument("--config", default="config.yaml")
    eval_run.add_argument("--output", default=None)
    eval_run.add_argument("--top-k", type=int, default=None)
    eval_run.add_argument("--source-k", type=int, default=None)
    eval_run.add_argument("--steps", type=int, default=None)
    eval_run.add_argument("--decay", type=float, default=None)
    eval_run.add_argument("--amplitude-cutoff", type=float, default=None)
    eval_run.add_argument("--aggregate", choices=["max", "sum"], default=None)
    eval_run.add_argument("--metadata-field-boost", type=float, default=None)
    eval_run.add_argument("--tag-boost", type=float, default=None)
    eval_run.add_argument("--kb", default=None)
    eval_run.add_argument("--reuse-built-kb", action="store_true")
    eval_run.add_argument("--eval-data-dir", default=None)
    eval_run.add_argument("--min-precision-at-k", type=float, default=None)
    eval_run.add_argument("--min-recall-at-k", type=float, default=0.8)
    eval_run.add_argument("--min-mrr", type=float, default=0.75)
    eval_run.add_argument("--min-hit-at-k", type=float, default=0.8)
    eval_run.add_argument(
        "--baseline",
        default=None,
        help="Path to baseline JSON. Suite-level thresholds are clamped to baseline - 0.02 (clipped to existing min_* values).",
    )

    auth = sub.add_parser("auth")
    auth_sub = auth.add_subparsers(dest="auth_command", required=True)
    generate_key = auth_sub.add_parser("generate-key")
    generate_key.add_argument("--id", required=True)
    generate_key.add_argument("--label", default="")
    generate_key.add_argument("--scopes", default="search")
    generate_key.add_argument("--kb", default="*")
    generate_key.add_argument("--rate", type=int, default=60)
    generate_key.add_argument("--prefix", default="tmr_live_")

    manual_bulk = sub.add_parser("manual-bulk")
    manual_bulk_sub = manual_bulk.add_subparsers(dest="manual_bulk_command", required=True)
    bulk_preview = manual_bulk_sub.add_parser("preview")
    _add_bulk_args(bulk_preview, include_import_args=False)
    bulk_import = manual_bulk_sub.add_parser("import")
    _add_bulk_args(bulk_import, include_import_args=True)

    manual_library = sub.add_parser("manual-library")
    manual_library_sub = manual_library.add_subparsers(dest="manual_library_command", required=True)
    library_rebuild = manual_library_sub.add_parser("rebuild")
    library_rebuild.add_argument("--kb", default="default")
    library_rebuild.add_argument("--config", default="config.yaml")
    library_rebuild.add_argument("--mode", choices=["full", "incremental", "auto"], default="full")
    library_rebuild.add_argument("--no-fallback", action="store_true")
    library_rebuild.add_argument("--queued", action="store_true")
    library_jobs = manual_library_sub.add_parser("rebuild-jobs")
    library_jobs_sub = library_jobs.add_subparsers(dest="manual_library_jobs_command", required=True)
    jobs_list = library_jobs_sub.add_parser("list")
    jobs_list.add_argument("--kb", default=None)
    jobs_list.add_argument("--config", default="config.yaml")
    jobs_list.add_argument("--status", default=None)
    jobs_inspect = library_jobs_sub.add_parser("inspect")
    jobs_inspect.add_argument("--config", default="config.yaml")
    jobs_inspect.add_argument("--job-id", required=True)
    jobs_cancel = library_jobs_sub.add_parser("cancel")
    jobs_cancel.add_argument("--config", default="config.yaml")
    jobs_cancel.add_argument("--job-id", required=True)
    library_dirty = manual_library_sub.add_parser("dirty")
    library_dirty.add_argument("--kb", default="default")
    library_dirty.add_argument("--config", default="config.yaml")
    library_dirty.add_argument("--format", choices=["json", "csv"], default="json")
    library_registry = manual_library_sub.add_parser("registry")
    library_registry_sub = library_registry.add_subparsers(dest="manual_registry_command", required=True)
    registry_inspect_parser = library_registry_sub.add_parser("inspect")
    registry_inspect_parser.add_argument("--kb", default="default")
    registry_inspect_parser.add_argument("--config", default="config.yaml")
    registry_migrate = library_registry_sub.add_parser("migrate")
    registry_migrate.add_argument("--kb", default="default")
    registry_migrate.add_argument("--config", default="config.yaml")
    registry_migrate.add_argument("--dry-run", action="store_true", default=False)
    registry_verify = library_registry_sub.add_parser("verify-blobs")
    registry_verify.add_argument("--kb", default="default")
    registry_verify.add_argument("--config", default="config.yaml")
    library_bundle = manual_library_sub.add_parser("bundle")
    library_bundle_sub = library_bundle.add_subparsers(dest="manual_bundle_command", required=True)
    bundle_export = library_bundle_sub.add_parser("export")
    bundle_export.add_argument("--kb", default="default")
    bundle_export.add_argument("--config", default="config.yaml")
    bundle_export.add_argument("--output", required=True)
    bundle_inspect = library_bundle_sub.add_parser("inspect")
    bundle_inspect.add_argument("--bundle", required=True)
    bundle_inspect.add_argument("--config", default=None)
    bundle_inspect.add_argument("--target-kb", default=None)
    bundle_inspect.add_argument("--conflict-mode", choices=["fail", "skip", "overwrite"], default="fail")
    bundle_import = library_bundle_sub.add_parser("import")
    bundle_import.add_argument("--bundle", required=True)
    bundle_import.add_argument("--config", default="config.yaml")
    bundle_import.add_argument("--target-kb", default=None)
    bundle_import.add_argument("--conflict-mode", choices=["fail", "skip", "overwrite"], default="fail")
    bundle_import.add_argument("--dry-run", action="store_true", default=False)

    tag = sub.add_parser("tag")
    tag_sub = tag.add_subparsers(dest="tag_command", required=True)
    tag_stats = tag_sub.add_parser("stats")
    tag_stats.add_argument("--kb", default="default")
    tag_stats.add_argument("--config", default="config.yaml")
    tag_policy = tag_sub.add_parser("policy")
    tag_policy.add_argument("--kb", default="default")
    tag_policy.add_argument("--config", default="config.yaml")
    tag_policy.add_argument("--file", default=None, help="Write policy from JSON file; omit to print current policy.")
    tag_preview = tag_sub.add_parser("rewrite-preview")
    _add_tag_rewrite_args(tag_preview, include_commit_args=False)
    tag_commit = tag_sub.add_parser("rewrite")
    _add_tag_rewrite_args(tag_commit, include_commit_args=True)

    qdrant = sub.add_parser("qdrant")
    qdrant_sub = qdrant.add_subparsers(dest="qdrant_command", required=True)
    qdrant_inspect = qdrant_sub.add_parser("inspect")
    qdrant_inspect.add_argument("--kb", default="default")
    qdrant_inspect.add_argument("--config", default="config.yaml")

    provider = sub.add_parser("provider")
    provider_sub = provider.add_subparsers(dest="provider_command", required=True)
    provider_probe = provider_sub.add_parser("probe")
    provider_probe.add_argument("--config", default="config.yaml")
    provider_probe.add_argument("--kb", default="default")
    provider_probe.add_argument("--format", choices=["json"], default="json")
    provider_probe.add_argument("--all", action="store_true", default=False)
    provider_probe.add_argument("--embedding", action="store_true", default=False)
    provider_probe.add_argument("--answer", action="store_true", default=False)
    provider_probe.add_argument("--reranker", action="store_true", default=False)
    provider_probe.add_argument("--qdrant", action="store_true", default=False)
    provider_probe.add_argument("--s3", action="store_true", default=False)

    production_provider = sub.add_parser("production-provider")
    production_provider_sub = production_provider.add_subparsers(dest="production_provider_command", required=True)
    production_provider_smoke = production_provider_sub.add_parser("smoke")
    production_provider_smoke.add_argument("--config", default=DEFAULT_PROVIDER_SMOKE_CONFIG)
    production_provider_smoke.add_argument("--kb", default="default")
    production_provider_smoke.add_argument("--manual", action="append", default=[], help="Manual source document path. Repeat for many files.")
    production_provider_smoke.add_argument("--metadata", default=None, help="Optional JSON, JSONL, or CSV metadata path. Omit to use *.metadata.json sidecars.")
    production_provider_smoke.add_argument("--metadata-format", choices=["json", "jsonl", "csv"], default="json")
    production_provider_smoke.add_argument("--workdir", default=None)
    production_provider_smoke.add_argument("--output", default=None)
    production_provider_smoke.add_argument("--format", choices=["json", "markdown"], default="json")
    production_provider_smoke.add_argument("--question", default=DEFAULT_PROVIDER_SMOKE_QUESTION)
    production_provider_smoke.add_argument("--rebuild-mode", choices=["full", "incremental", "auto"], default="full")
    production_provider_smoke.add_argument("--answer-top-k", type=int, default=6)
    production_provider_smoke.add_argument("--answer-source-k", type=int, default=6)
    production_provider_smoke.add_argument("--reset-qdrant-collection", action="store_true", default=False)

    readiness = sub.add_parser("readiness")
    readiness_sub = readiness.add_subparsers(dest="readiness_command", required=True)
    readiness_smoke = readiness_sub.add_parser("smoke")
    readiness_smoke.add_argument("--workdir", default=None)
    readiness_smoke.add_argument("--keep-workdir", action="store_true", default=False)

    pilot = sub.add_parser("pilot")
    pilot_sub = pilot.add_subparsers(dest="pilot_command", required=True)
    pilot_run = pilot_sub.add_parser("run")
    pilot_run.add_argument("--config", default=DEFAULT_PILOT_CONFIG)
    pilot_run.add_argument("--suite", default=DEFAULT_PILOT_SUITE)
    pilot_run.add_argument("--docs", default=DEFAULT_PILOT_DOCS)
    pilot_run.add_argument("--workdir", default=None)
    pilot_run.add_argument("--output", default=None)
    pilot_run.add_argument("--format", choices=["json", "markdown"], default="json")
    pilot_run.add_argument("--top-k", type=int, default=None)
    pilot_run.add_argument("--source-k", type=int, default=None)
    pilot_run.add_argument("--min-recall-at-k", type=float, default=DEFAULT_PILOT_THRESHOLDS.min_recall_at_k)
    pilot_run.add_argument("--min-mrr", type=float, default=DEFAULT_PILOT_THRESHOLDS.min_mrr)
    pilot_run.add_argument("--min-hit-at-k", type=float, default=DEFAULT_PILOT_THRESHOLDS.min_hit_at_k)
    pilot_run.add_argument("--hashing-baseline", default=None)
    pilot_run.add_argument("--production-baseline", default=None)
    pilot_run.add_argument(
        "--informational-suites",
        default="",
        help="Comma-separated eval suite filenames whose diagnosis is informational and not blocking.",
    )
    pilot_run.add_argument(
        "--accepted-suites",
        default="",
        help="Comma-separated eval suite filenames whose diagnosis has been reviewed and accepted as non-blocking.",
    )

    epa = sub.add_parser("epa")
    epa_sub = epa.add_subparsers(dest="epa_command", required=True)
    epa_rebuild = epa_sub.add_parser("rebuild")
    epa_rebuild.add_argument("--config", default="config.yaml")
    epa_rebuild.add_argument("--force", action="store_true")

    feedback = sub.add_parser("feedback")
    feedback_sub = feedback.add_subparsers(dest="feedback_command", required=True)
    feedback_submit = feedback_sub.add_parser("submit")
    feedback_submit.add_argument("--kb", default="default")
    feedback_submit.add_argument("--config", default="config.yaml")
    feedback_submit.add_argument("--json", required=True, help="Feedback payload JSON file.")
    feedback_list = feedback_sub.add_parser("list")
    feedback_list.add_argument("--kb", default="default")
    feedback_list.add_argument("--config", default="config.yaml")
    feedback_list.add_argument("--status", default=None)
    feedback_list.add_argument("--outcome", default=None)
    feedback_list.add_argument("--query", default=None)
    feedback_list.add_argument("--limit", type=int, default=50)
    feedback_review = feedback_sub.add_parser("review")
    feedback_review.add_argument("--kb", default="default")
    feedback_review.add_argument("--config", default="config.yaml")
    feedback_review.add_argument("--feedback-id", required=True)
    feedback_review.add_argument("--status", default=None)
    feedback_review.add_argument("--operator-note", default=None)
    feedback_preview = feedback_sub.add_parser("promote-preview")
    _add_feedback_promote_args(feedback_preview)
    feedback_promote = feedback_sub.add_parser("promote")
    _add_feedback_promote_args(feedback_promote)
    feedback_promote.add_argument("--append", action="store_true")
    feedback_promote.add_argument("--overwrite", action="store_true")

    args = parser.parse_args(argv)
    if args.command == "build":
        cfg = load_config(args.config)
        configure_logging(cfg.logging.level, cfg.logging.format)
        emb = _create_embedder_from_config(cfg)
        state = build_kb(args.docs, args.kb, cfg, embedder=emb)
        save_kb(state, cfg)
        print(json.dumps({"kb_name": state.kb_name, "build_id": state.build_id, "chunks": state.graph.number_of_nodes()}, ensure_ascii=False))
        return 0
    if args.command == "search":
        cfg = load_config(args.config)
        configure_logging(cfg.logging.level, cfg.logging.format)
        emb = _create_embedder_from_config(cfg)
        state = load_kb(args.kb, cfg)
        query_vec = emb.encode_query(args.question)
        params = {
            "top_k": args.top_k or cfg.search.top_k,
            "source_k": cfg.search.source_k,
            "steps": cfg.search.steps,
            "decay": cfg.search.decay,
            "amplitude_cutoff": cfg.search.amplitude_cutoff,
            "aggregate": cfg.search.aggregate,
        }
        filters = {
            "brand": args.brand,
            "product_category": args.category,
            "product_model": args.model,
            "language": args.language,
            "tags": resolve_tags_for_search(args.tag, load_tag_policy(args.kb, cfg)),
        }
        narrowing = infer_metadata_narrowing(
            query_text=args.question,
            graph=state.graph,
            explicit_filters=filters,
            enabled=cfg.search.metadata_narrowing_enabled,
            category_policy=cfg.search.metadata_narrowing_category_policy,
            brand_policy=cfg.search.metadata_narrowing_brand_policy,
            min_candidates=cfg.search.metadata_narrowing_min_candidates,
        )
        filters = merge_inferred_filters(filters, narrowing)
        execution = execute_search(
            state=state,
            query_vec=query_vec,
            settings=cfg,
            query_text=args.question,
            top_k=int(params["top_k"]),
            source_k=int(params["source_k"]),
            steps=int(params["steps"]),
            decay=float(params["decay"]),
            amplitude_cutoff=float(params["amplitude_cutoff"]),
            aggregate=str(params["aggregate"]),
            filters=filters,
            boost_filters=narrowing.boost_filters,
        )
        payload = {"build_id": state.build_id, "results": [r.to_dict() for r in execution.results]}
        if search_debug_enabled(args.debug_search, cfg):
            payload["debug"] = search_debug_payload(
                execution,
                params,
                ann_enabled=search_ann_enabled(state, cfg),
            )
            payload["debug"]["metadata_narrowing"] = narrowing.to_debug_dict(
                enabled=cfg.search.metadata_narrowing_enabled
            )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    if args.command == "serve":
        cfg = load_config(args.config)
        configure_logging(cfg.logging.level, cfg.logging.format)
        from . import api

        api.settings = cfg
        uvicorn.run(api.app, host=args.host or cfg.server.host, port=args.port or cfg.server.port)
        return 0
    if args.command == "config" and args.config_command == "validate":
        report = validate_config(args.config)
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
        return 1 if report.status == "failed" else 0
    if args.command == "retrain-residuals":
        cfg = load_config(args.config)
        configure_logging(cfg.logging.level, cfg.logging.format)
        matrix = load_cooccurrence(cooccurrence_path(cfg, args.kb))
        if matrix is None or matrix.edge_count == 0:
            print(f"retrain-residuals error: cooccurrence matrix missing for kb={args.kb!r}", file=sys.stderr)
            return 2
        registry_path = Path(cfg.storage.data_dir) / "manual_registry.sqlite3"
        if cfg.manual_library.registry_path != "data/manual_registry.sqlite3":
            registry_path = Path(cfg.manual_library.registry_path)
        top_n = cfg.wave_phase1.intrinsic_residual_top_n or cfg.wave_phase1.pyramid_top_k
        try:
            registry = create_registry(registry_path)
            with registry.connection() as conn:
                report = train_intrinsic_residuals_for_kb(
                    args.kb,
                    conn,
                    matrix,
                    expected_dim=cfg.model.dim,
                    top_n=int(top_n),
                )
        except Exception as exc:
            print(f"retrain-residuals error: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 2
        print(json.dumps({"kb_name": args.kb, **report.to_dict()}, ensure_ascii=False))
        return 0
    if args.command == "eval" and args.eval_command == "run":
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
                print(
                    f"eval error: suite {suite_name!r} missing from baseline {args.baseline!r}",
                    file=sys.stderr,
                )
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
    if args.command == "auth" and args.auth_command == "generate-key":
        plaintext = args.prefix + secrets.token_urlsafe(24)
        scopes = [item.strip() for item in args.scopes.split(",") if item.strip()]
        kb_allowlist = [item.strip() for item in args.kb.split(",") if item.strip()]
        payload = {
            "id": args.id,
            "hash": ConfigAuthStore.hash_plaintext(plaintext),
            "label": args.label,
            "kb_allowlist": kb_allowlist,
            "scopes": scopes,
            "rate_limit_per_minute": args.rate,
        }
        print("# Add this under auth.keys:")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        print("# Give this plaintext key to the client once:")
        print(plaintext)
        return 0
    if args.command == "manual-bulk" and args.manual_bulk_command == "preview":
        cfg = load_config(args.config)
        configure_logging(cfg.logging.level, cfg.logging.format)
        metadata_text = _read_text_file(args.metadata)
        uploaded = _read_bulk_files(args.file)
        preview = preview_bulk_import(
            args.kb,
            metadata_text,
            args.metadata_format,
            uploaded,
            cfg,
            mode=args.mode,
            overwrite=args.overwrite,
        )
        print(json.dumps(preview.to_dict(), ensure_ascii=False, indent=2))
        return 0
    if args.command == "manual-bulk" and args.manual_bulk_command == "import":
        cfg = load_config(args.config)
        configure_logging(cfg.logging.level, cfg.logging.format)
        metadata_text = _read_text_file(args.metadata)
        uploaded = _read_bulk_files(args.file)
        result = commit_bulk_import(
            args.kb,
            metadata_text,
            args.metadata_format,
            uploaded,
            cfg,
            mode=args.mode,
            overwrite=args.overwrite,
            selected_rows=set(args.selected_row) if args.selected_row else None,
        )
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return 0
    if args.command == "manual-library" and args.manual_library_command == "rebuild":
        cfg = load_config(args.config)
        configure_logging(cfg.logging.level, cfg.logging.format)
        embedder = _create_embedder_from_config(cfg)
        try:
            current = load_kb(args.kb, cfg)
        except Exception:
            current = None
        app_state = AppState(current)
        if args.queued or cfg.manual_library.rebuild_queue_enabled:
            queue = RebuildQueue(app_state, cfg, embedder=embedder)
            job, coalesced = queue.enqueue(
                args.kb,
                mode=args.mode,
                allow_fallback=not args.no_fallback,
                trigger="cli",
            )
            queue.drain_until_idle()
            print(json.dumps(queue.inspect(job.job_id) | {"coalesced": coalesced}, ensure_ascii=False, indent=2))
            return 0 if queue.get(job.job_id).status == "succeeded" else 1
        task = start_library_rebuild(
            app_state,
            args.kb,
            cfg,
            embedder=embedder,
            mode=args.mode,
            allow_fallback=not args.no_fallback,
        )
        while task.status == "running":
            time.sleep(0.05)
        print(json.dumps(task.to_dict(), ensure_ascii=False, indent=2))
        return 0 if task.status == "done" else 1
    if args.command == "manual-library" and args.manual_library_command == "rebuild-jobs":
        cfg = load_config(args.config)
        configure_logging(cfg.logging.level, cfg.logging.format)
        queue = RebuildQueue(AppState(), cfg)
        if args.manual_library_jobs_command == "list":
            print(json.dumps({"jobs": queue.list_jobs(kb_name=args.kb, status=args.status)}, ensure_ascii=False, indent=2))
            return 0
        if args.manual_library_jobs_command == "inspect":
            print(json.dumps(queue.inspect(args.job_id), ensure_ascii=False, indent=2))
            return 0
        if args.manual_library_jobs_command == "cancel":
            print(json.dumps(queue.cancel(args.job_id).to_dict(), ensure_ascii=False, indent=2))
            return 0
    if args.command == "manual-library" and args.manual_library_command == "dirty":
        cfg = load_config(args.config)
        configure_logging(cfg.logging.level, cfg.logging.format)
        try:
            graph_state = load_kb(args.kb, cfg)
        except Exception:
            graph_state = None
        report = build_dirty_state_report(args.kb, cfg, graph_state=graph_state)
        rows = report["dirty_manuals"]
        if args.format == "csv":
            fieldnames = ["manual_id", "source_file", "operation", "updated_at", "checksum", "status", "searchable", "exists"]
            writer = csv.DictWriter(sys.stdout, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        else:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    if args.command == "manual-library" and args.manual_library_command == "registry":
        cfg = load_config(args.config)
        configure_logging(cfg.logging.level, cfg.logging.format)
        if args.manual_registry_command == "inspect":
            print(json.dumps(registry_inspect(args.kb, cfg), ensure_ascii=False, indent=2))
            return 0
        if args.manual_registry_command == "migrate":
            report = migrate_sidecars_to_registry(args.kb, cfg, dry_run=args.dry_run)
            print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
            return 0
        if args.manual_registry_command == "verify-blobs":
            print(json.dumps(verify_registry_blobs(args.kb, cfg), ensure_ascii=False, indent=2))
            return 0
    if args.command == "manual-library" and args.manual_library_command == "bundle":
        cfg = load_config(args.config) if args.config else None
        if cfg is not None:
            configure_logging(cfg.logging.level, cfg.logging.format)
        if args.manual_bundle_command == "export":
            assert cfg is not None
            result = export_bundle(args.kb, cfg, args.output)
            print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
            return 0
        if args.manual_bundle_command == "inspect":
            report = inspect_bundle(args.bundle, cfg, target_kb=args.target_kb, conflict_mode=args.conflict_mode)
            print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
            return 0 if report.valid else 1
        if args.manual_bundle_command == "import":
            assert cfg is not None
            result = import_bundle(
                args.bundle,
                cfg,
                target_kb=args.target_kb,
                conflict_mode=args.conflict_mode,
                dry_run=args.dry_run,
            )
            print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
            return 0
    if args.command == "tag" and args.tag_command == "stats":
        cfg = load_config(args.config)
        configure_logging(cfg.logging.level, cfg.logging.format)
        try:
            graph_state = load_kb(args.kb, cfg)
        except Exception:
            graph_state = None
        print(json.dumps(tag_usage_report(args.kb, cfg, graph_state=graph_state), ensure_ascii=False, indent=2))
        return 0
    if args.command == "tag" and args.tag_command == "policy":
        cfg = load_config(args.config)
        configure_logging(cfg.logging.level, cfg.logging.format)
        if args.file:
            policy_data = json.loads(_read_text_file(args.file))
            policy = save_tag_policy(args.kb, cfg, policy_data)
        else:
            policy = load_tag_policy(args.kb, cfg)
        print(json.dumps(policy.to_dict(), ensure_ascii=False, indent=2))
        return 0
    if args.command == "tag" and args.tag_command == "rewrite-preview":
        cfg = load_config(args.config)
        configure_logging(cfg.logging.level, cfg.logging.format)
        preview = preview_tag_rewrite(args.kb, cfg, source_tags=args.source_tag, target_tag=args.target_tag, mode=args.mode)
        print(json.dumps(preview.to_dict(), ensure_ascii=False, indent=2))
        return 0
    if args.command == "tag" and args.tag_command == "rewrite":
        cfg = load_config(args.config)
        configure_logging(cfg.logging.level, cfg.logging.format)
        result = commit_tag_rewrite(
            args.kb,
            cfg,
            source_tags=args.source_tag,
            target_tag=args.target_tag,
            mode=args.mode,
            update_policy=args.update_policy,
            policy_alias_mode=args.policy_alias_mode,
        )
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return 0
    if args.command == "qdrant" and args.qdrant_command == "inspect":
        cfg = load_config(args.config)
        configure_logging(cfg.logging.level, cfg.logging.format)
        print(json.dumps(inspect_qdrant(args.kb, cfg), ensure_ascii=False, indent=2))
        return 0
    if args.command == "provider" and args.provider_command == "probe":
        selected = []
        if args.all:
            selected.append("all")
        for name in ("embedding", "answer", "reranker", "qdrant", "s3"):
            if getattr(args, name):
                selected.append(name)
        report = run_provider_probe(args.config, selected=selected or ["all"], kb_name=args.kb)
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
        return 1 if report.status == "failed" else 0
    if args.command == "production-provider" and args.production_provider_command == "smoke":
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
    if args.command == "readiness" and args.readiness_command == "smoke":
        report = run_readiness_smoke(workdir=args.workdir, keep_workdir=args.keep_workdir)
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
        return 0 if report.status == "passed" else 1
    if args.command == "pilot" and args.pilot_command == "run":
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
                informational_suites=_split_csv(args.informational_suites),
                accepted_suites=_split_csv(args.accepted_suites),
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
    if args.command == "epa" and args.epa_command == "rebuild":
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
    if args.command == "feedback" and args.feedback_command == "submit":
        cfg = load_config(args.config)
        configure_logging(cfg.logging.level, cfg.logging.format)
        payload = json.loads(_read_text_file(args.json))
        feedback = create_feedback(args.kb, payload, cfg)
        print(json.dumps({"feedback": feedback.to_dict()}, ensure_ascii=False, indent=2))
        return 0
    if args.command == "feedback" and args.feedback_command == "list":
        cfg = load_config(args.config)
        configure_logging(cfg.logging.level, cfg.logging.format)
        rows = list_feedback(args.kb, cfg, status=args.status, outcome=args.outcome, query=args.query, limit=args.limit)
        print(json.dumps({"kb_name": args.kb, "feedback": [row.to_dict() for row in rows]}, ensure_ascii=False, indent=2))
        return 0
    if args.command == "feedback" and args.feedback_command == "review":
        cfg = load_config(args.config)
        configure_logging(cfg.logging.level, cfg.logging.format)
        feedback = review_feedback(
            args.kb,
            args.feedback_id,
            cfg,
            status=args.status,
            operator_note=args.operator_note,
        )
        print(json.dumps({"feedback": feedback.to_dict()}, ensure_ascii=False, indent=2))
        return 0
    if args.command == "feedback" and args.feedback_command == "promote-preview":
        cfg = load_config(args.config)
        configure_logging(cfg.logging.level, cfg.logging.format)
        preview = preview_eval_promotion(args.kb, args.feedback_id, cfg, output_path=args.output)
        print(json.dumps(preview.to_dict(), ensure_ascii=False, indent=2))
        return 0
    if args.command == "feedback" and args.feedback_command == "promote":
        cfg = load_config(args.config)
        configure_logging(cfg.logging.level, cfg.logging.format)
        preview = export_eval_promotion(
            args.kb,
            args.feedback_id,
            cfg,
            output_path=args.output,
            append=args.append,
            overwrite=args.overwrite,
        )
        print(json.dumps(preview.to_dict(), ensure_ascii=False, indent=2))
        return 0
    return 1


def _add_bulk_args(parser: argparse.ArgumentParser, *, include_import_args: bool) -> None:
    parser.add_argument("--kb", default="default")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--metadata", required=True, help="Path to JSON, JSONL, or CSV metadata.")
    parser.add_argument("--metadata-format", choices=["json", "jsonl", "csv"], default="csv")
    parser.add_argument("--file", action="append", default=[], help="Manual source document path. Repeat for many files.")
    parser.add_argument("--mode", choices=["create_only", "upsert", "dry_run"], default="create_only")
    parser.add_argument("--overwrite", action="store_true")
    if include_import_args:
        parser.add_argument("--selected-row", action="append", type=int, default=[])


def _add_tag_rewrite_args(parser: argparse.ArgumentParser, *, include_commit_args: bool) -> None:
    parser.add_argument("--kb", default="default")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--source-tag", action="append", required=True)
    parser.add_argument("--target-tag", required=True)
    parser.add_argument("--mode", choices=["merge", "rename"], default="merge")
    if include_commit_args:
        parser.add_argument("--update-policy", action="store_true")
        parser.add_argument("--policy-alias-mode", choices=["synonym", "deprecated"], default=None)


def _add_feedback_promote_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--kb", default="default")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--feedback-id", action="append", required=True)
    parser.add_argument("--output", default=None)


def _read_text_file(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _read_bulk_files(paths: list[str]) -> list[BulkUploadedFile]:
    return [BulkUploadedFile(filename=Path(path).name, content=Path(path).read_bytes()) for path in paths]


if __name__ == "__main__":
    raise SystemExit(main())
