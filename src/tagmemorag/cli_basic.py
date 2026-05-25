from __future__ import annotations

import json
from pathlib import Path
import secrets
import sys

import uvicorn

from .demo import DemoQaOptions, run_demo_qa
from .auth.config_store import ConfigAuthStore
from .cli_helpers import create_embedder_from_config
from .config import load_config
from .config_validation import validate_config
from .logging_setup import configure_logging
from .manual_registry import create_registry
from .metadata_narrowing import infer_metadata_narrowing, merge_inferred_filters
from .search_runtime import execute_search, search_ann_enabled, search_debug_enabled, search_debug_payload
from .state import build_kb, load_kb, save_kb
from .tag_cooccurrence import cooccurrence_path, load_cooccurrence
from .tag_governance import load_tag_policy, resolve_tags_for_search
from .tag_intrinsic_residuals import train_intrinsic_residuals_for_kb


def run_basic_command(args) -> int:
    if args.command == "build":
        cfg = load_config(args.config)
        configure_logging(cfg.logging.level, cfg.logging.format)
        emb = create_embedder_from_config(cfg)
        state = build_kb(args.docs, args.kb, cfg, embedder=emb)
        save_kb(state, cfg)
        print(
            json.dumps(
                {"kb_name": state.kb_name, "build_id": state.build_id, "chunks": state.graph.number_of_nodes()},
                ensure_ascii=False,
            )
        )
        return 0
    if args.command == "search":
        return _run_search(args)
    if args.command == "demo" and args.demo_command == "qa":
        return _run_demo_qa(args)
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
    if args.command == "langchain" and args.langchain_command == "compare":
        return _run_langchain_compare(args)
    if args.command == "retrain-residuals":
        return _run_retrain_residuals(args)
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
    return 1


def _run_search(args) -> int:
    cfg = load_config(args.config)
    configure_logging(cfg.logging.level, cfg.logging.format)
    emb = create_embedder_from_config(cfg)
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
        payload["debug"]["metadata_narrowing"] = narrowing.to_debug_dict(enabled=cfg.search.metadata_narrowing_enabled)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _run_demo_qa(args) -> int:
    payload = run_demo_qa(
        DemoQaOptions(
            question=args.question,
            config_path=args.config,
            kb_name=args.kb,
            top_k=args.top_k,
            source_k=args.source_k,
            token_budget=args.token_budget,
            output_path=args.output,
        )
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["status"] == "passed" else 1


def _run_langchain_compare(args) -> int:
    from .langchain_adapter import LangChainAdapterUnavailable, LangChainParseConfig, compare_langchain_to_native

    config = LangChainParseConfig(
        max_chars=args.max_chars,
        min_chars=args.min_chars,
        overlap_chars=args.overlap_chars,
    )
    try:
        report = compare_langchain_to_native(args.file, config=config, root_dir=args.root_dir)
    except LangChainAdapterUnavailable as exc:
        print(f"langchain compare error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"langchain compare error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    return 0


def _run_retrain_residuals(args) -> int:
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
