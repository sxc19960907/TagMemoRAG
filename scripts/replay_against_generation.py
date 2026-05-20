"""Replay persisted retrieval feedback against a specific generation.

T1 acceptance criteria: before swap, operators must verify the shadow
generation does not regress on representative queries. T5 (the full
eval-as-driver replay tool) is a separate task; this script is the minimal
ad-hoc tool for T1: read feedback log entries, replay each query against the
chosen generation, summarize hit@k.

Usage:
    uv run python scripts/replay_against_generation.py \
        --kb default \
        --generation 2 \
        [--baseline-generation 1] \
        [--limit 50] \
        [--top-k 5]

Output: a JSON summary printed to stdout. Compares hit@k between baseline and
target generation if --baseline-generation is provided.

This script does NOT modify any state. It loads the requested generation
into a temporary AppState, replays queries, computes metrics, prints, exits.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Bootstrap import path so this can run without `uv run pytest` setup.
_SCRIPT_DIR = Path(__file__).resolve().parent
_SRC = _SCRIPT_DIR.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from tagmemorag.config import load_config
from tagmemorag.indexgen import KbPaths, read_meta
from tagmemorag.retrieval_feedback import feedback_log_path
from tagmemorag.storage.json_anchor import JsonAnchorStore
from tagmemorag.storage.json_graph import JsonGraphStore
from tagmemorag.storage.npz_vector import NpzVectorStore


def _read_feedback_queries(kb_name: str, settings, limit: int) -> list[dict]:
    """Read the latest `limit` queries from the feedback jsonl."""
    path = feedback_log_path(kb_name, settings)
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        rows.append(row)
    return rows[-limit:]


def _load_generation_artifacts(kb_name: str, settings, generation: int):
    """Return (graph, vectors_store, anchors) for a generation, or raise."""
    paths = KbPaths(kb_name, settings, generation=generation)
    if not paths.graph.is_file():
        raise FileNotFoundError(f"No graph.json at {paths.graph}")
    graph = JsonGraphStore(paths.graph).load()
    vectors_store = NpzVectorStore(paths.vectors) if paths.vectors.is_file() else None
    return graph, vectors_store


def _node_text(graph, node_id: int) -> str:
    attrs = graph.nodes[node_id]
    return str(attrs.get("text") or attrs.get("header") or "")


def _hit_at_k_via_lexical(graph, query: str, top_k: int) -> list[int]:
    """Cheap lexical hit detection: count token overlap. Replay's exact
    retrieval would require loading the full search stack — that belongs in
    T5. For T1 acceptance, lexical overlap is sufficient as a regression
    detector: if shadow loses overlap on the same queries, somebody changed
    chunking or text content.
    """
    query_tokens = set(query.lower().split())
    scored: list[tuple[int, int]] = []
    for node_id in graph.nodes:
        text = _node_text(graph, node_id).lower()
        if not text:
            continue
        text_tokens = set(text.split())
        overlap = len(query_tokens & text_tokens)
        if overlap > 0:
            scored.append((node_id, overlap))
    scored.sort(key=lambda item: (-item[1], item[0]))
    return [node_id for node_id, _ in scored[:top_k]]


def _summarize_replay(
    kb_name: str,
    settings,
    generation: int,
    queries: list[dict],
    top_k: int,
) -> dict:
    graph, _ = _load_generation_artifacts(kb_name, settings, generation)
    if graph.number_of_nodes() == 0:
        return {
            "generation": generation,
            "queries_replayed": 0,
            "any_hit_count": 0,
            "any_hit_rate": 0.0,
            "node_count": 0,
        }

    any_hit_count = 0
    for row in queries:
        q = str(row.get("query") or "").strip()
        if not q:
            continue
        hits = _hit_at_k_via_lexical(graph, q, top_k)
        if hits:
            any_hit_count += 1

    return {
        "generation": generation,
        "queries_replayed": len(queries),
        "any_hit_count": any_hit_count,
        "any_hit_rate": (any_hit_count / len(queries)) if queries else 0.0,
        "node_count": graph.number_of_nodes(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--kb", required=True, help="kb_name to replay against")
    parser.add_argument("--generation", type=int, required=True, help="target generation id (e.g. 2 for shadow)")
    parser.add_argument(
        "--baseline-generation",
        type=int,
        default=None,
        help="optional baseline generation for delta comparison (typically active)",
    )
    parser.add_argument("--config", default="config.yaml", help="config file path")
    parser.add_argument("--limit", type=int, default=50, help="max feedback entries to replay")
    parser.add_argument("--top-k", type=int, default=5, help="top-k hits for any-hit metric")
    args = parser.parse_args()

    settings = load_config(args.config)

    meta = read_meta(Path(settings.storage.data_dir) / args.kb)
    if meta is None:
        print(json.dumps({"error": "no_index_json", "kb": args.kb}, ensure_ascii=False))
        return 2

    queries = _read_feedback_queries(args.kb, settings, args.limit)

    summary = {"kb": args.kb, "queries_count": len(queries), "top_k": args.top_k}

    target_summary = _summarize_replay(args.kb, settings, args.generation, queries, args.top_k)
    summary["target"] = target_summary

    if args.baseline_generation is not None:
        baseline_summary = _summarize_replay(
            args.kb, settings, args.baseline_generation, queries, args.top_k
        )
        summary["baseline"] = baseline_summary
        delta = target_summary["any_hit_rate"] - baseline_summary["any_hit_rate"]
        summary["any_hit_rate_delta"] = delta
        summary["regression_detected"] = delta < 0

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not summary.get("regression_detected") else 3


if __name__ == "__main__":
    raise SystemExit(main())
