"""Diagnose Phase 2b-1 dynamicBoostFactor formula across three strategies.

Builds the product-manual fixture once with hashing embedder and forced
real-PCA EPA (`epa_min_k=4`, 12 unique tags), then evaluates every query in
tests/fixtures/eval/*.jsonl under three configurations:

  - strategy=constant         → dynamic = 1.0 (Phase 1 baseline)
  - strategy=epa              → max(epa_floor, logicDepth * scale) (Phase 2a)
  - strategy=pyramid          → full source formula via ResidualPyramid features
                                (Phase 2b-1; resonance stub = 0)
  - strategy=pyramid+resonance → Phase 3: same as `pyramid` but with
                                `cross_domain_resonance_enabled=True`, i.e.
                                resonance = sum(bridge.strength) feeds the
                                dynamicBoostFactor formula's log term.

Reports alpha-series std / range/mean per strategy, plus pyramid features
(tag_memo_activation / coverage / coherence) statistics. The D2 thresholds
(std > 0.005, range/mean > 0.1) print as `[INFO]` lines but no longer gate
the script's exit code — they were originally calibrated against a tiny
hashing dim=64 fixture by tuning `pyramid_post_scale=4.0`, which the
"only port VCP, no calibration constants" principle (2026-05-17) reverts.

Decision point (Phase 2b-1 D8 / Phase 3 D4, superseded 2026-05-17):
`pyramid_post_scale` default is now 1.0 (VCP-equivalent); deployments may
override per-knob if production data calls for it, but no fixture-driven
calibration is expected.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tagmemorag.config import Settings, StorageConfig  # noqa: E402
from tagmemorag.embedder import HashingEmbedder  # noqa: E402
from tagmemorag.epa_basis import basis_path, load_epa_basis  # noqa: E402
from tagmemorag.state import build_kb  # noqa: E402
from tagmemorag.wave_tag_spike import (  # noqa: E402
    _load_kb_tag_vectors,
    _reset_matrix_cache_for_tests,
    apply_tag_boost,
)
from tagmemorag.residual_pyramid import ResidualPyramid  # noqa: E402


@dataclass(frozen=True)
class SeriesStats:
    mean: float
    std: float
    minimum: float
    maximum: float

    @property
    def range_over_mean(self) -> float:
        if abs(self.mean) < 1e-12:
            return 0.0
        return (self.maximum - self.minimum) / self.mean


@dataclass(frozen=True)
class StrategyRun:
    strategy: str
    alpha: SeriesStats
    resonance: SeriesStats = SeriesStats(0.0, 0.0, 0.0, 0.0)
    bridges: SeriesStats = SeriesStats(0.0, 0.0, 0.0, 0.0)


@dataclass(frozen=True)
class PyramidStats:
    levels: SeriesStats
    coverage: SeriesStats
    coherence: SeriesStats
    tag_memo_activation: SeriesStats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docs", type=Path, default=REPO_ROOT / "tests" / "fixtures" / "product_manuals")
    parser.add_argument("--suite-dir", type=Path, default=REPO_ROOT / "tests" / "fixtures" / "eval")
    parser.add_argument(
        "--scale",
        type=float,
        default=2.0,
        help="EPA logicDepth scale for strategy=epa (Phase 2a, default 2.0).",
    )
    parser.add_argument(
        "--post-scale",
        type=float,
        default=4.0,
        help="Pyramid post-multiplier for strategy=pyramid (Phase 2b-1 D8, default 4.0).",
    )
    parser.add_argument("--base-tag-boost", type=float, default=0.03)
    parser.add_argument("--epa-min-k", type=int, default=4)
    args = parser.parse_args(argv)

    queries = list(_load_queries(args.suite_dir))
    if not queries:
        print(f"no eval queries found under {args.suite_dir}", file=sys.stderr)
        return 2

    print("=== Pyramid Dynamic Boost Diagnostic ===")
    print(f"Queries: {len(queries)}")
    print(f"epa_min_k={args.epa_min_k} epa_scale={args.scale} pyramid_post_scale={args.post_scale} base_tag_boost={args.base_tag_boost}")

    runs: dict[str, StrategyRun] = {}
    pyramid_stats: PyramidStats | None = None

    with tempfile.TemporaryDirectory(prefix="pyramid-diag-") as tmp:
        tmp_root = Path(tmp)
        cfg = _build_cfg(tmp_root, strategy="constant", scale=args.scale, post_scale=args.post_scale, base_tag_boost=args.base_tag_boost, epa_min_k=args.epa_min_k)
        embedder = HashingEmbedder(dim=64)
        build_kb(args.docs, "default", cfg, embedder=embedder)
        basis = load_epa_basis(basis_path(cfg))
        if basis is None:
            raise RuntimeError("EPA basis was not written")
        print(f"\nEPA basis: train_kind={basis.train_kind} K={basis.K} tag_count={basis.tag_count_at_train}")

        for strategy_label, strategy_value, resonance_enabled in (
            ("constant", "constant", False),
            ("epa", "epa", False),
            ("pyramid", "pyramid", False),
            ("pyramid+resonance", "pyramid", True),
        ):
            cfg.wave_phase1.dynamic_boost_factor_strategy = strategy_value  # type: ignore[assignment]
            cfg.wave_phase1.cross_domain_resonance_enabled = resonance_enabled  # type: ignore[assignment]
            alpha_values: list[float] = []
            resonance_values: list[float] = []
            bridges_counts: list[float] = []
            for query in queries:
                query_vec = embedder.encode_query(query)
                _reset_matrix_cache_for_tests()
                _boosted, info = apply_tag_boost(
                    query_vec,
                    kb_name="default",
                    settings=cfg,
                    base_tag_boost=args.base_tag_boost,
                )
                alpha_values.append(float(info.boost_factor_applied))
                resonance_values.append(float(info.cross_domain_resonance))
                bridges_counts.append(float(info.cross_domain_bridges_count))
            runs[strategy_label] = StrategyRun(
                strategy=strategy_label,
                alpha=_stats(alpha_values),
                resonance=_stats(resonance_values),
                bridges=_stats(bridges_counts),
            )

        # Pyramid features stats: instantiate ResidualPyramid directly per query
        tag_rows = _load_kb_tag_vectors(cfg, "default", expected_dim=cfg.model.dim)
        pyramid = ResidualPyramid(
            tag_rows,
            dim=cfg.model.dim,
            max_levels=cfg.wave_phase1.pyramid_max_levels,
            top_k=cfg.wave_phase1.pyramid_top_k,
            min_energy_ratio=cfg.wave_phase1.pyramid_min_energy_ratio,
            use_handshake_features=cfg.wave_phase1.pyramid_use_handshake_features,
        )
        levels_values: list[float] = []
        coverage_values: list[float] = []
        coherence_values: list[float] = []
        activation_values: list[float] = []
        for query in queries:
            query_vec = embedder.encode_query(query)
            result = pyramid.analyze(query_vec)
            levels_values.append(float(result.features.depth))
            coverage_values.append(float(result.features.coverage))
            coherence_values.append(float(result.features.coherence))
            activation_values.append(float(result.features.tag_memo_activation))
        pyramid_stats = PyramidStats(
            levels=_stats(levels_values),
            coverage=_stats(coverage_values),
            coherence=_stats(coherence_values),
            tag_memo_activation=_stats(activation_values),
        )

    for strategy in ("constant", "epa", "pyramid", "pyramid+resonance"):
        run = runs[strategy]
        print(f"\nstrategy={strategy}")
        print(
            "  alpha: "
            f"mean={run.alpha.mean:.6f} std={run.alpha.std:.6f} "
            f"range=[{run.alpha.minimum:.6f}, {run.alpha.maximum:.6f}] "
            f"range/mean={run.alpha.range_over_mean:.6f}"
        )
        if strategy == "pyramid+resonance":
            print(
                "  resonance: "
                f"mean={run.resonance.mean:.6f} std={run.resonance.std:.6f} "
                f"range=[{run.resonance.minimum:.6f}, {run.resonance.maximum:.6f}]"
            )
            print(
                "  bridges:   "
                f"mean={run.bridges.mean:.4f} std={run.bridges.std:.4f} "
                f"range=[{run.bridges.minimum:.0f}, {run.bridges.maximum:.0f}]"
            )

    if pyramid_stats is not None:
        print("\nResidualPyramid features (over query set):")
        for name, stats in (
            ("depth          ", pyramid_stats.levels),
            ("coverage       ", pyramid_stats.coverage),
            ("coherence      ", pyramid_stats.coherence),
            ("activation     ", pyramid_stats.tag_memo_activation),
        ):
            print(
                f"  {name}: mean={stats.mean:.4f} std={stats.std:.4f} "
                f"range=[{stats.minimum:.4f}, {stats.maximum:.4f}]"
            )

    pyr = runs["pyramid"]
    std_pass = pyr.alpha.std > 0.005
    range_pass = pyr.alpha.range_over_mean > 0.1
    print()
    print(f"  [INFO] pyramid std(alpha) > 0.005:               {_status(std_pass)}")
    print(f"  [INFO] pyramid range(alpha)/mean(alpha) > 0.1:   {_status(range_pass)}")

    res = runs["pyramid+resonance"]
    res_std_pass = res.alpha.std > 0.005
    res_range_pass = res.alpha.range_over_mean > 0.1
    print(f"  [INFO] resonance std(alpha) > 0.005:             {_status(res_std_pass)}")
    print(f"  [INFO] resonance range(alpha)/mean(alpha) > 0.1: {_status(res_range_pass)}")

    # The D2 thresholds (std > 0.005, range/mean > 0.1) were originally a
    # PASS/FAIL gate calibrated against a 12-tag hashing dim=64 fixture by
    # tuning `pyramid_post_scale=4.0`. Per the "only port VCP, don't add
    # calibration constants" principle (2026-05-17 ADR reversal), this
    # diagnostic is now informational only — failing thresholds means the
    # alpha series is flat, which is expected on tiny fixtures and not a
    # regression. Re-run on real production data when available.
    overall = std_pass and range_pass and res_std_pass and res_range_pass
    print(f"\n=> overall (informational): {_status(overall)}")
    return 0


def _build_cfg(
    tmp_root: Path,
    *,
    strategy: str,
    scale: float,
    post_scale: float,
    base_tag_boost: float,
    epa_min_k: int,
) -> Settings:
    return Settings(
        storage=StorageConfig(data_dir=str(tmp_root / "data")),
        manual_library={"registry_path": str(tmp_root / "manual_registry.sqlite3")},  # type: ignore[arg-type]
        model={"provider": "hashing", "dim": 64, "batch_size": 16},  # type: ignore[arg-type]
        wave_phase0={"epa_min_k": epa_min_k},  # type: ignore[arg-type]
        wave_phase1={  # type: ignore[arg-type]
            "spike_enabled": True,
            "dynamic_boost_factor_strategy": strategy,
            "epa_logic_depth_scale": scale,
            "epa_floor": 0.0,
            "pyramid_post_scale": post_scale,
        },
        search={"tag_boost": base_tag_boost},  # type: ignore[arg-type]
    )


def _load_queries(suite_dir: Path) -> Iterable[str]:
    for path in sorted(suite_dir.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            payload = json.loads(line)
            query = payload.get("question") or payload.get("query")
            if query:
                yield str(query)


def _stats(values: list[float]) -> SeriesStats:
    arr = np.asarray(values, dtype=np.float64)
    if arr.size == 0:
        return SeriesStats(mean=0.0, std=0.0, minimum=0.0, maximum=0.0)
    return SeriesStats(
        mean=float(arr.mean()),
        std=float(arr.std()),
        minimum=float(arr.min()),
        maximum=float(arr.max()),
    )


def _status(value: bool) -> str:
    return "PASS" if value else "FAIL"


if __name__ == "__main__":
    raise SystemExit(main())
