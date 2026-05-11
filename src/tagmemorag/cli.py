from __future__ import annotations

import argparse
import json

import uvicorn

from .config import load_config
from .embedder import create_embedder
from .state import build_kb, load_kb, save_kb
from .wave_searcher import wave_search


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
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)

    args = parser.parse_args(argv)
    if args.command == "build":
        cfg = load_config(args.config)
        emb = create_embedder(cfg.model.name, cfg.model.device, cfg.model.batch_size, cfg.model.dim)
        state = build_kb(args.docs, args.kb, cfg, embedder=emb)
        save_kb(state, cfg)
        print(json.dumps({"kb_name": state.kb_name, "build_id": state.build_id, "chunks": state.graph.number_of_nodes()}, ensure_ascii=False))
        return 0
    if args.command == "search":
        cfg = load_config(args.config)
        emb = create_embedder(cfg.model.name, cfg.model.device, cfg.model.batch_size, cfg.model.dim)
        state = load_kb(args.kb, cfg)
        query_vec = emb.encode_query(args.question)
        results = wave_search(query_vec, state.graph, state.vectors, state.anchors, top_k=args.top_k or cfg.search.top_k)
        print(json.dumps({"build_id": state.build_id, "results": [r.to_dict() for r in results]}, ensure_ascii=False, indent=2))
        return 0
    if args.command == "serve":
        uvicorn.run("tagmemorag.api:app", host=args.host, port=args.port)
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
