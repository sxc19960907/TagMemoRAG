"""Generate candidate proposals for the realmanuals fixture using the
already-built `realmanuals` KB. Avoids re-embedding 5 PDFs twice; uses a
single siliconflow-built KB plus a separate hashing-built KB for diversity.

Output schema mirrors `relabel_eval_fixture.py` ProposalRecord but only
runs siliconflow (hashing on 4096-dim semantic queries doesn't add much
diversity at this fixture scale).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
SRC_ROOT = REPO_ROOT / "src"
SCRIPTS_ROOT = REPO_ROOT / "scripts"
for p in (str(SRC_ROOT), str(SCRIPTS_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import build_eval_baseline as bel  # noqa: E402

from tagmemorag.config import load_config  # noqa: E402
from tagmemorag.embedder import HttpEmbedder  # noqa: E402
from tagmemorag.eval.dataset import load_eval_suite  # noqa: E402
from tagmemorag.state import load_kb  # noqa: E402
from tagmemorag.wave_searcher import wave_search  # noqa: E402


def _make_excerpt(text: str, max_chars: int = 200) -> str:
    text = text.replace("\n", " ").strip()
    return text if len(text) <= max_chars else text[: max_chars - 1] + "…"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--kb", default="realmanuals")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--top-k", type=int, default=10)
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    cases = load_eval_suite(args.suite)
    if not cases:
        print(f"no cases in {args.suite}", file=sys.stderr)
        return 1

    bel._smoke_check_siliconflow(cfg)
    embedder = HttpEmbedder(
        cfg.model.name or bel.SILICONFLOW_MODEL_NAME,
        base_url=cfg.model.base_url or bel.SILICONFLOW_BASE_URL,
        api_key_env=cfg.model.api_key_env or bel.SILICONFLOW_API_KEY_ENV,
        timeout_seconds=float(cfg.model.timeout_seconds or 30.0),
        batch_size=int(cfg.model.batch_size or 16),
        dim=int(cfg.model.dim),
        normalize=bool(cfg.model.normalize),
    )

    state = load_kb(args.kb, cfg)
    print(f"[relabel] loaded KB '{args.kb}': {state.graph.number_of_nodes()} nodes",
          file=sys.stderr)

    records: list[dict] = []
    for case in cases:
        qv = bel._with_retry(lambda: embedder.encode_query(case.query))
        results = wave_search(
            qv, state.graph, state.vectors, state.anchors,
            top_k=args.top_k, source_k=args.top_k,
        )
        candidates = []
        for rank, r in enumerate(results, start=1):
            candidates.append({
                "source": "siliconflow",
                "rank_in_source": rank,
                "node_id": int(r.node_id),
                "source_file": str(r.source_file),
                "header": str(r.header),
                "text_excerpt": _make_excerpt(r.text),
                "tags": list(r.tags or []),
                "score": round(float(r.score), 6),
            })

        record = {
            "case_id": case.id,
            "query": case.query,
            "kb_name": case.kb_name,
            "current_relevant": [
                {
                    "source_file": rel.source_file or "",
                    "header": rel.header or "",
                    "text_contains": list(rel.text_contains or ()),
                    "metadata": dict(rel.metadata or {}),
                }
                for rel in case.relevant
            ],
            "candidates": candidates,
        }
        records.append(record)
        print(f"[relabel] {case.id}: {len(candidates)} candidates", file=sys.stderr)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.output.with_suffix(args.output.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    tmp.replace(args.output)
    print(f"wrote {args.output} with {len(records)} record(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
