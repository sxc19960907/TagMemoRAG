from __future__ import annotations

import csv
import json
import sys
import time

from .cli_helpers import create_embedder_from_config, read_bulk_files, read_text_file
from .config import load_config
from .logging_setup import configure_logging
from .manual_bundle import export_bundle, import_bundle, inspect_bundle
from .manual_bulk_import import commit_bulk_import, preview_bulk_import
from .manual_library import build_dirty_state_report, migrate_sidecars_to_registry, registry_inspect, verify_registry_blobs
from .qdrant_ops import inspect_qdrant
from .rebuild_queue import RebuildQueue
from .state import AppState, load_kb, start_library_rebuild
from .tag_governance import (
    commit_tag_rewrite,
    load_tag_policy,
    preview_tag_rewrite,
    save_tag_policy,
    tag_usage_report,
)


def run_manual_command(args) -> int:
    if args.command == "manual-bulk" and args.manual_bulk_command == "preview":
        return _run_manual_bulk_preview(args)
    if args.command == "manual-bulk" and args.manual_bulk_command == "import":
        return _run_manual_bulk_import(args)
    if args.command == "manual-library":
        return _run_manual_library(args)
    if args.command == "tag":
        return _run_tag(args)
    if args.command == "qdrant" and args.qdrant_command == "inspect":
        cfg = load_config(args.config)
        configure_logging(cfg.logging.level, cfg.logging.format)
        print(json.dumps(inspect_qdrant(args.kb, cfg), ensure_ascii=False, indent=2))
        return 0
    return 1


def _run_manual_bulk_preview(args) -> int:
    cfg = load_config(args.config)
    configure_logging(cfg.logging.level, cfg.logging.format)
    metadata_text = read_text_file(args.metadata)
    uploaded = read_bulk_files(args.file)
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


def _run_manual_bulk_import(args) -> int:
    cfg = load_config(args.config)
    configure_logging(cfg.logging.level, cfg.logging.format)
    metadata_text = read_text_file(args.metadata)
    uploaded = read_bulk_files(args.file)
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


def _run_manual_library(args) -> int:
    if args.manual_library_command == "rebuild":
        return _run_manual_library_rebuild(args)
    if args.manual_library_command == "rebuild-jobs":
        return _run_manual_library_jobs(args)
    if args.manual_library_command == "dirty":
        return _run_manual_library_dirty(args)
    if args.manual_library_command == "registry":
        return _run_manual_library_registry(args)
    if args.manual_library_command == "bundle":
        return _run_manual_library_bundle(args)
    return 1


def _run_manual_library_rebuild(args) -> int:
    cfg = load_config(args.config)
    configure_logging(cfg.logging.level, cfg.logging.format)
    embedder = create_embedder_from_config(cfg)
    try:
        current = load_kb(args.kb, cfg)
    except Exception:
        current = None
    app_state = AppState(current)
    if args.queued or cfg.manual_library.rebuild_queue_enabled:
        queue = RebuildQueue(app_state, cfg, embedder=embedder)
        job, coalesced = queue.enqueue(args.kb, mode=args.mode, allow_fallback=not args.no_fallback, trigger="cli")
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


def _run_manual_library_jobs(args) -> int:
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
    return 1


def _run_manual_library_dirty(args) -> int:
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


def _run_manual_library_registry(args) -> int:
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
    return 1


def _run_manual_library_bundle(args) -> int:
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
    return 1


def _run_tag(args) -> int:
    if args.tag_command == "stats":
        cfg = load_config(args.config)
        configure_logging(cfg.logging.level, cfg.logging.format)
        try:
            graph_state = load_kb(args.kb, cfg)
        except Exception:
            graph_state = None
        print(json.dumps(tag_usage_report(args.kb, cfg, graph_state=graph_state), ensure_ascii=False, indent=2))
        return 0
    if args.tag_command == "policy":
        cfg = load_config(args.config)
        configure_logging(cfg.logging.level, cfg.logging.format)
        if args.file:
            policy_data = json.loads(read_text_file(args.file))
            policy = save_tag_policy(args.kb, cfg, policy_data)
        else:
            policy = load_tag_policy(args.kb, cfg)
        print(json.dumps(policy.to_dict(), ensure_ascii=False, indent=2))
        return 0
    if args.tag_command == "rewrite-preview":
        cfg = load_config(args.config)
        configure_logging(cfg.logging.level, cfg.logging.format)
        preview = preview_tag_rewrite(args.kb, cfg, source_tags=args.source_tag, target_tag=args.target_tag, mode=args.mode)
        print(json.dumps(preview.to_dict(), ensure_ascii=False, indent=2))
        return 0
    if args.tag_command == "rewrite":
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
    return 1
