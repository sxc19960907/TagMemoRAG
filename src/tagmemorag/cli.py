from __future__ import annotations

import argparse
import json
import secrets
import sys

import uvicorn

from .config import load_config
from .auth.config_store import ConfigAuthStore
from .embedder import create_embedder
from .eval.dataset import EvalSuiteError, EvalThresholds
from .eval.runner import run_eval
from .logging_setup import configure_logging
from .state import build_kb, load_kb, save_kb
from .wave_searcher import wave_search


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
        results = wave_search(query_vec, state.graph, state.vectors, state.anchors, top_k=args.top_k or cfg.search.top_k)
        print(json.dumps({"build_id": state.build_id, "results": [r.to_dict() for r in results]}, ensure_ascii=False, indent=2))
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
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
