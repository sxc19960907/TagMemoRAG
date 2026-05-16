"""Generate dual-embedder candidate proposals for re-labeling an eval suite.

Phase A of `eval-fixture-rewrite`: for each query in `--suite`, run wave_search
with both the hashing and siliconflow embedders, take the union of the top-K
candidates (deduped by source_file + header), and write a ProposalRecord JSON
line per query for human review.

Output schema (one query per line):

    {
      "case_id": "coffee-steam-weak",
      "query": "蒸汽很小怎么办",
      "kb_name": "default",
      "current_relevant": [{source_file, header, text_contains}, ...],
      "candidates": [
        {
          "source": "hashing|siliconflow|extra",
          "rank_in_source": 1,
          "node_id": 7,
          "source_file": "coffee_machine.md",
          "header": "蒸汽功能",
          "text_excerpt": "首200字...",
          "tags": ["coffee", "steam"]
        },
        ...
      ],
      "ai_suggestion": null
    }

`ai_suggestion` is left null and filled in during a later review stage
(currently by the Claude session; Phase B may swap to an external LLM).

Requires `SILICONFLOW_API_KEY` in env when used (siliconflow recall is the
whole point — falling back to a single embedder defeats the goal).
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

# Reuse build_eval_baseline's siliconflow config + retry helper to avoid
# duplicating retry/backoff plumbing (D6.h).
SCRIPTS_ROOT = REPO_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import build_eval_baseline as bel  # noqa: E402

from tagmemorag.config import Settings, StorageConfig  # noqa: E402
from tagmemorag.embedder import HashingEmbedder, HttpEmbedder  # noqa: E402
from tagmemorag.eval.dataset import EvalCase, load_eval_suite  # noqa: E402
from tagmemorag.state import build_kb  # noqa: E402
from tagmemorag.types import GraphState, Result  # noqa: E402
from tagmemorag.wave_searcher import wave_search  # noqa: E402


CandidateDict = dict[str, Any]


def _hashing_cfg(tmp_root: Path) -> Settings:
    return Settings(
        storage=StorageConfig(data_dir=str(tmp_root / "data-hashing")),
        manual_library={"registry_path": str(tmp_root / "registry-hashing.sqlite3")},  # type: ignore[arg-type]
        model={"provider": "hashing", "dim": 64, "batch_size": 16},  # type: ignore[arg-type]
        wave_phase1={"spike_enabled": True},  # type: ignore[arg-type]
    )


def _siliconflow_cfg(tmp_root: Path) -> Settings:
    return Settings(
        storage=StorageConfig(data_dir=str(tmp_root / "data-siliconflow")),
        manual_library={"registry_path": str(tmp_root / "registry-siliconflow.sqlite3")},  # type: ignore[arg-type]
        model={  # type: ignore[arg-type]
            "provider": "http",
            "name": bel.SILICONFLOW_MODEL_NAME,
            "dim": bel.SILICONFLOW_MODEL_DIM,
            "base_url": bel.SILICONFLOW_BASE_URL,
            "api_key_env": bel.SILICONFLOW_API_KEY_ENV,
            "normalize": True,
        },
        wave_phase1={"spike_enabled": True},  # type: ignore[arg-type]
    )


def _make_excerpt(text: str, max_chars: int = 200) -> str:
    text = text.replace("\n", " ").strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1] + "…"


def _result_to_candidate(
    result: Result,
    *,
    source: str,
    rank_in_source: int,
) -> CandidateDict:
    return {
        "source": source,
        "rank_in_source": int(rank_in_source),
        "node_id": int(result.node_id),
        "source_file": str(result.source_file),
        "header": str(result.header),
        "text_excerpt": _make_excerpt(result.text),
        "tags": list(result.tags or []),
        "score": round(float(result.score), 6),
    }


def _candidate_key(c: CandidateDict) -> tuple[str, str]:
    return (c["source_file"], c["header"])


def _dedupe_union(
    hashing_results: list[Result],
    siliconflow_results: list[Result],
    *,
    extra_pairs: list[tuple[str, str]],
    state: GraphState,
) -> list[CandidateDict]:
    """Build the per-query candidate list.

    Order: hashing rank 1..K, then siliconflow rank 1..K not already seen,
    then extra-candidates not already seen. Dedupe by (source_file, header).
    """
    seen: dict[tuple[str, str], CandidateDict] = {}

    for rank, r in enumerate(hashing_results, start=1):
        cand = _result_to_candidate(r, source="hashing", rank_in_source=rank)
        seen[_candidate_key(cand)] = cand

    for rank, r in enumerate(siliconflow_results, start=1):
        cand = _result_to_candidate(r, source="siliconflow", rank_in_source=rank)
        key = _candidate_key(cand)
        if key in seen:
            # Mark that siliconflow also found it; keep first occurrence.
            seen[key]["also_found_by"] = (
                seen[key].get("also_found_by", []) + ["siliconflow"]
            )
        else:
            seen[key] = cand

    for source_file, header in extra_pairs:
        key = (source_file, header)
        if key in seen:
            continue
        # Look up the matching node in the hashing graph (cheap source-of-truth
        # for text content; siliconflow KB has same chunks). Fall back to a
        # placeholder text if no matching node found — extra-candidates are a
        # human override and must not crash the pipeline.
        node_id = -1
        text = ""
        tags: list[str] = []
        for nid, attrs in state.graph.nodes(data=True):
            if str(attrs.get("source_file")) == source_file and str(attrs.get("header")) == header:
                node_id = int(nid)
                text = str(attrs.get("text", ""))
                tags = list(attrs.get("tags") or [])
                break
        if node_id == -1:
            print(
                f"[warn] extra-candidate {source_file!r}:{header!r} not found in graph; "
                "human reviewer should verify",
                file=sys.stderr,
            )
        seen[key] = {
            "source": "extra",
            "rank_in_source": 0,
            "node_id": node_id,
            "source_file": source_file,
            "header": header,
            "text_excerpt": _make_excerpt(text) if text else "(not found in graph)",
            "tags": tags,
            "score": 0.0,
        }

    # Stable ordering: hashing first (by rank), then siliconflow new entries (by rank), then extra.
    def _sort_key(c: CandidateDict) -> tuple[int, int]:
        bucket = {"hashing": 0, "siliconflow": 1, "extra": 2}.get(c["source"], 3)
        return (bucket, c["rank_in_source"])

    return sorted(seen.values(), key=_sort_key)


def _parse_extra_candidates(spec: str | None) -> list[tuple[str, str]]:
    """Parse `--extra-candidates "file.md:header,file.md:header2"`."""
    if not spec:
        return []
    pairs: list[tuple[str, str]] = []
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if ":" not in chunk:
            raise ValueError(f"extra-candidate {chunk!r} missing ':' separator")
        source_file, _, header = chunk.partition(":")
        pairs.append((source_file.strip(), header.strip()))
    return pairs


def _expected_to_dict(expected) -> dict[str, Any]:
    return {
        "source_file": expected.source_file or "",
        "header": expected.header or "",
        "text_contains": list(expected.text_contains or ()),
        "metadata": dict(expected.metadata or {}),
    }


def _proposal_record(
    case: EvalCase,
    candidates: list[CandidateDict],
) -> dict[str, Any]:
    return {
        "case_id": case.id,
        "query": case.query,
        "kb_name": case.kb_name,
        "current_relevant": [_expected_to_dict(r) for r in case.relevant],
        "current_negatives": [_expected_to_dict(r) for r in case.negatives],
        "candidates": candidates,
        "ai_suggestion": None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", required=True, type=Path)
    parser.add_argument("--docs", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument(
        "--extra-candidates",
        default=None,
        help='Comma-separated "source_file:header" pairs to force into the candidate list.',
    )
    parser.add_argument(
        "--source-k",
        type=int,
        default=10,
        help="wave_search source_k for both embedders (defaults to top-k).",
    )
    args = parser.parse_args(argv)

    cases = load_eval_suite(args.suite)
    if not cases:
        print(f"no cases in {args.suite}", file=sys.stderr)
        return 1

    extra_pairs = _parse_extra_candidates(args.extra_candidates)

    with tempfile.TemporaryDirectory(prefix="relabel-") as tmp:
        tmp_root = Path(tmp)
        hashing_cfg = _hashing_cfg(tmp_root)
        siliconflow_cfg = _siliconflow_cfg(tmp_root)

        # Smoke check siliconflow before burning time on KB build.
        bel._smoke_check_siliconflow(siliconflow_cfg)

        hashing_embedder = HashingEmbedder(dim=hashing_cfg.model.dim)
        siliconflow_embedder = HttpEmbedder(
            siliconflow_cfg.model.name or bel.SILICONFLOW_MODEL_NAME,
            base_url=siliconflow_cfg.model.base_url or bel.SILICONFLOW_BASE_URL,
            api_key_env=siliconflow_cfg.model.api_key_env or bel.SILICONFLOW_API_KEY_ENV,
            timeout_seconds=float(siliconflow_cfg.model.timeout_seconds or 30.0),
            batch_size=int(siliconflow_cfg.model.batch_size or 16),
            dim=int(siliconflow_cfg.model.dim),
            normalize=bool(siliconflow_cfg.model.normalize),
        )

        print(f"[relabel] building hashing KB ({args.docs}) ...", file=sys.stderr)
        hashing_state = build_kb(args.docs, "default", hashing_cfg, embedder=hashing_embedder)
        print(
            f"[relabel] building siliconflow KB ({args.docs}) — this calls Qwen-VL ...",
            file=sys.stderr,
        )
        # build_kb's embed step internally batches; wrap the entire build_kb
        # call in retry to recover from transient API errors mid-batch.
        siliconflow_state = bel._with_retry(
            lambda: build_kb(args.docs, "default", siliconflow_cfg, embedder=siliconflow_embedder),
        )

        records: list[dict[str, Any]] = []
        for case in cases:
            qv_h = hashing_embedder.encode_query(case.query)
            hashing_results = wave_search(
                qv_h,
                hashing_state.graph,
                hashing_state.vectors,
                hashing_state.anchors,
                top_k=args.top_k,
                source_k=args.source_k,
            )

            qv_s = bel._with_retry(lambda: siliconflow_embedder.encode_query(case.query))
            siliconflow_results = wave_search(
                qv_s,
                siliconflow_state.graph,
                siliconflow_state.vectors,
                siliconflow_state.anchors,
                top_k=args.top_k,
                source_k=args.source_k,
            )

            candidates = _dedupe_union(
                hashing_results,
                siliconflow_results,
                extra_pairs=extra_pairs,
                state=hashing_state,
            )
            records.append(_proposal_record(case, candidates))
            print(
                f"[relabel] {case.id}: {len(candidates)} candidates "
                f"(hashing={len(hashing_results)}, siliconflow={len(siliconflow_results)}, "
                f"extra={len(extra_pairs)})",
                file=sys.stderr,
            )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    tmp_out = args.output.with_suffix(args.output.suffix + ".tmp")
    try:
        with tmp_out.open("w", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        tmp_out.replace(args.output)
    except BaseException:
        tmp_out.unlink(missing_ok=True)
        raise

    print(f"wrote {args.output} with {len(records)} proposal record(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
