"""Diagnose Phase 4 V8 geodesicRerank under varying alpha / min_geo_samples.

Builds the product-manual fixture once, runs every query under each
(alpha, min_samples) combo, and reports:

  - applied_pct        : V8 actually contributed to ranking
  - max_geo_zero_pct   : V8 ran but L2 fallback kicked in (no signal)
  - skipped_pct        : V8 didn't run (with reason breakdown)
  - hit_count_p50/p90  : per-candidate tag hit count distribution
  - avg_swap_total     : (rank_changed + new_entry + lost_entry) per query

PASS gate (default args): max_geo_zero_pct < 50% AND applied_pct > 0
otherwise the diagnostic exits non-zero — meaning V8 has no signal on this
fixture set and ops should re-tune `geodesic_min_geo_samples` or check that
chunks carry tags. Also reports CSV-style table for easy grep.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from statistics import mean, quantiles

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tagmemorag.config import Settings, StorageConfig  # noqa: E402
from tagmemorag.embedder import HashingEmbedder  # noqa: E402
from tagmemorag.state import build_kb  # noqa: E402
from tagmemorag.wave_geodesic_rerank import geodesic_rerank  # noqa: E402
from tagmemorag.wave_searcher import wave_search  # noqa: E402
from tagmemorag.wave_tag_spike import (  # noqa: E402
    _reset_matrix_cache_for_tests,
    apply_tag_boost,
)


def _build_cfg(
    tmp_root: Path,
    *,
    alpha: float,
    min_samples: int,
    oversample: float,
) -> Settings:
    return Settings(
        storage=StorageConfig(data_dir=str(tmp_root / "data")),
        manual_library={"registry_path": str(tmp_root / "manual_registry.sqlite3")},  # type: ignore[arg-type]
        model={"provider": "hashing", "dim": 64, "batch_size": 16},  # type: ignore[arg-type]
        wave_phase1={  # type: ignore[arg-type]
            "spike_enabled": True,
            "dynamic_boost_factor_strategy": "pyramid",
            "geodesic_rerank_enabled": True,
            "geodesic_alpha": alpha,
            "geodesic_min_geo_samples": min_samples,
            "geodesic_oversample_factor": oversample,
        },
        search={"tag_boost": 0.03, "lexical_enabled": False, "ann_preselect_enabled": False},  # type: ignore[arg-type]
    )


def _load_queries(suite_dir: Path) -> list[str]:
    queries: list[str] = []
    for path in sorted(suite_dir.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            payload = json.loads(line)
            q = payload.get("question") or payload.get("query")
            if q:
                queries.append(str(q))
    return queries


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])
    cut = quantiles(values, n=100)
    idx = max(0, min(98, int(q) - 1))
    return float(cut[idx])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docs", type=Path, default=REPO_ROOT / "tests" / "fixtures" / "product_manuals")
    parser.add_argument("--suite-dir", type=Path, default=REPO_ROOT / "tests" / "fixtures" / "eval")
    parser.add_argument("--alphas", type=str, default="0.0,0.1,0.3,0.5,1.0",
                        help="Comma-separated α values to sweep.")
    parser.add_argument("--min-samples", type=str, default="1,2,4",
                        help="Comma-separated min_geo_samples values to sweep.")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--oversample", type=float, default=2.0)
    parser.add_argument("--strict", action="store_true",
                        help="Exit non-zero if any cell fails the PASS gate.")
    args = parser.parse_args(argv)

    queries = _load_queries(args.suite_dir)
    if not queries:
        print(f"no eval queries found under {args.suite_dir}", file=sys.stderr)
        return 2

    alphas = [float(a) for a in args.alphas.split(",") if a.strip()]
    min_samples_list = [int(m) for m in args.min_samples.split(",") if m.strip()]
    print("=== Phase 4 V8 geodesicRerank diagnostic ===")
    print(f"Queries: {len(queries)}  TopK: {args.top_k}  Oversample: {args.oversample}")
    print(f"alphas: {alphas}")
    print(f"min_samples: {min_samples_list}")
    print()

    rows: list[dict] = []
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="v8-diag-") as tmp:
        tmp_root = Path(tmp)
        # Build KB once with constant settings (only differ by α/min_samples below).
        bootstrap = _build_cfg(tmp_root, alpha=0.3, min_samples=2, oversample=args.oversample)
        embedder = HashingEmbedder(dim=64)
        state = build_kb(args.docs, "default", bootstrap, embedder=embedder)

        for alpha in alphas:
            for min_samples in min_samples_list:
                cfg = _build_cfg(tmp_root, alpha=alpha, min_samples=min_samples, oversample=args.oversample)
                applied = 0
                max_geo_zero = 0
                skipped = 0
                skipped_reasons: dict[str, int] = {}
                hit_counts: list[int] = []
                swaps: list[int] = []
                for q in queries:
                    qv = embedder.encode_query(q)
                    _reset_matrix_cache_for_tests()
                    _boosted, info = apply_tag_boost(
                        qv, kb_name="default", settings=cfg, base_tag_boost=0.03
                    )
                    if info.skipped_reason or not info.accumulated_energy:
                        skipped += 1
                        skipped_reasons[info.skipped_reason or "energy_field_empty"] = (
                            skipped_reasons.get(info.skipped_reason or "energy_field_empty", 0) + 1
                        )
                        continue
                    # Build candidate pool via wave_search oversample, then call V8.
                    pool_size = max(args.top_k, int(args.top_k * args.oversample))
                    cands = wave_search(
                        qv,
                        state.graph,
                        state.vectors,
                        state.anchors,
                        top_k=args.top_k,
                        source_k=args.top_k,
                        steps=1,
                        decay=0.7,
                        amplitude_cutoff=0.01,
                        rerank_pool_size=pool_size,
                    )
                    rerank = geodesic_rerank(
                        cands,
                        energy_field=info.accumulated_energy,
                        graph=state.graph,
                        kb_name="default",
                        settings=cfg,
                        top_k=args.top_k,
                    )
                    if rerank.applied:
                        applied += 1
                        hit_counts.extend(rerank.hit_count_observed)
                        swaps.append(sum(rerank.swap_kinds.values()))
                    else:
                        if rerank.skipped_reason == "max_geo_zero":
                            max_geo_zero += 1
                        else:
                            skipped += 1
                            skipped_reasons[rerank.skipped_reason or "unknown"] = (
                                skipped_reasons.get(rerank.skipped_reason or "unknown", 0) + 1
                            )

                total = len(queries)
                row = {
                    "alpha": alpha,
                    "min_samples": min_samples,
                    "applied_pct": round(100 * applied / total, 1),
                    "max_geo_zero_pct": round(100 * max_geo_zero / total, 1),
                    "skipped_pct": round(100 * skipped / total, 1),
                    "hit_p50": round(_percentile(hit_counts, 50), 1) if hit_counts else 0.0,
                    "hit_p90": round(_percentile(hit_counts, 90), 1) if hit_counts else 0.0,
                    "avg_swap": round(mean(swaps), 2) if swaps else 0.0,
                    "skipped_reasons": dict(skipped_reasons),
                }
                rows.append(row)

                # PASS gate
                ok = row["applied_pct"] > 0 and row["max_geo_zero_pct"] < 50
                if not ok:
                    failures.append(
                        f"α={alpha} min_samples={min_samples}: "
                        f"applied={row['applied_pct']}% max_geo_zero={row['max_geo_zero_pct']}%"
                    )

    # Print table
    print(f"{'α':>5} {'min':>4} {'applied%':>9} {'maxGeo0%':>9} {'skipped%':>9} {'hit_p50':>8} {'hit_p90':>8} {'avgSwap':>8}")
    for r in rows:
        print(
            f"{r['alpha']:>5} {r['min_samples']:>4} {r['applied_pct']:>9} "
            f"{r['max_geo_zero_pct']:>9} {r['skipped_pct']:>9} "
            f"{r['hit_p50']:>8} {r['hit_p90']:>8} {r['avg_swap']:>8}"
        )
    print()
    if failures:
        print("PASS gate failures:")
        for f in failures:
            print(f"  - {f}")
    else:
        print("PASS gate: all cells satisfy applied_pct > 0 and max_geo_zero_pct < 50")

    if args.strict and failures:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
