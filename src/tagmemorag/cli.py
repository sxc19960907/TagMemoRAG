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
from .embedder import create_embedder
from .eval.dataset import EvalSuiteError, EvalThresholds
from .eval.runner import run_eval
from .logging_setup import configure_logging
from .manual_bulk_import import BulkUploadedFile, commit_bulk_import, preview_bulk_import
from .manual_library import export_dirty_state
from .retrieval_feedback import (
    create_feedback,
    export_eval_promotion,
    list_feedback,
    preview_eval_promotion,
    review_feedback,
)
from .search_runtime import execute_search
from .state import AppState, build_kb, load_kb, save_kb, start_library_rebuild
from .tag_governance import (
    commit_tag_rewrite,
    load_tag_policy,
    resolve_tags_for_search,
    save_tag_policy,
    tag_usage_report,
    preview_tag_rewrite,
)


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

    serve = sub.add_parser("serve")
    serve.add_argument("--host", default=None)
    serve.add_argument("--port", type=int, default=None)
    serve.add_argument("--config", default="config.yaml")

    eval_parser = sub.add_parser("eval")
    eval_sub = eval_parser.add_subparsers(dest="eval_command", required=True)
    eval_run = eval_sub.add_parser("run")
    eval_run.add_argument("--suite", required=True)
    eval_run.add_argument("--docs", default=None)
    eval_run.add_argument("--config", default="config.yaml")
    eval_run.add_argument("--output", default=None)
    eval_run.add_argument("--top-k", type=int, default=None)
    eval_run.add_argument("--kb", default=None)
    eval_run.add_argument("--reuse-built-kb", action="store_true")
    eval_run.add_argument("--eval-data-dir", default=None)
    eval_run.add_argument("--min-precision-at-k", type=float, default=None)
    eval_run.add_argument("--min-recall-at-k", type=float, default=0.8)
    eval_run.add_argument("--min-mrr", type=float, default=0.75)
    eval_run.add_argument("--min-hit-at-k", type=float, default=0.8)

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
    library_dirty = manual_library_sub.add_parser("dirty")
    library_dirty.add_argument("--kb", default="default")
    library_dirty.add_argument("--config", default="config.yaml")
    library_dirty.add_argument("--format", choices=["json", "csv"], default="json")

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
        filters = {
            "brand": args.brand,
            "product_category": args.category,
            "product_model": args.model,
            "language": args.language,
            "tags": resolve_tags_for_search(args.tag, load_tag_policy(args.kb, cfg)),
        }
        execution = execute_search(
            state=state,
            query_vec=query_vec,
            settings=cfg,
            top_k=args.top_k or cfg.search.top_k,
            source_k=cfg.search.source_k,
            steps=cfg.search.steps,
            decay=cfg.search.decay,
            amplitude_cutoff=cfg.search.amplitude_cutoff,
            aggregate=cfg.search.aggregate,
            filters=filters,
        )
        print(json.dumps({"build_id": state.build_id, "results": [r.to_dict() for r in execution.results]}, ensure_ascii=False, indent=2))
        return 0
    if args.command == "serve":
        cfg = load_config(args.config)
        configure_logging(cfg.logging.level, cfg.logging.format)
        from . import api

        api.settings = cfg
        uvicorn.run(api.app, host=args.host or cfg.server.host, port=args.port or cfg.server.port)
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
        try:
            report = run_eval(
                cfg=cfg,
                suite_path=args.suite,
                docs_path=args.docs,
                top_k=args.top_k,
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
    if args.command == "manual-library" and args.manual_library_command == "dirty":
        cfg = load_config(args.config)
        configure_logging(cfg.logging.level, cfg.logging.format)
        try:
            graph_state = load_kb(args.kb, cfg)
        except Exception:
            graph_state = None
        rows = export_dirty_state(args.kb, cfg, graph_state=graph_state)
        if args.format == "csv":
            fieldnames = ["manual_id", "source_file", "operation", "updated_at", "checksum", "status", "searchable", "exists"]
            writer = csv.DictWriter(sys.stdout, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        else:
            print(json.dumps({"kb_name": args.kb, "dirty_manual_count": len(rows), "dirty_manuals": rows}, ensure_ascii=False, indent=2))
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


def _read_bulk_files(paths: list[str]) -> list[BulkUploadedFile]:
    return [BulkUploadedFile(filename=Path(path).name, content=Path(path).read_bytes()) for path in paths]


if __name__ == "__main__":
    raise SystemExit(main())
