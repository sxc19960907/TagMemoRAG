"""Diagnose EPA logicDepth and Phase 1 dynamic boost behavior.

The script builds the product-manual fixture twice with the deterministic
hashing embedder:

- default-size cold-start EPA (`epa_min_k=8`)
- forced real-PCA EPA (`epa_min_k=4`)

It then evaluates every query in tests/fixtures/eval/*.jsonl and reports both
raw logicDepth and end-to-end apply_tag_boost alpha variation.
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
from tagmemorag.epa_projector import EPAProjector  # noqa: E402
from tagmemorag.manual_registry import create_registry  # noqa: E402
from tagmemorag.state import build_kb  # noqa: E402
from tagmemorag.tag_store import iter_canonical_tags_with_vectors  # noqa: E402
from tagmemorag.wave_tag_spike import _reset_matrix_cache_for_tests, apply_tag_boost  # noqa: E402

MIN_ALPHA_STD = 0.0045


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
class DiagRun:
    label: str
    train_kind: str
    K: int
    tag_count: int
    explained_variance_ratio: tuple[float, ...]
    logic_depth: SeriesStats
    alpha: SeriesStats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docs", type=Path, default=REPO_ROOT / "tests" / "fixtures" / "product_manuals")
    parser.add_argument("--suite-dir", type=Path, default=REPO_ROOT / "tests" / "fixtures" / "eval")
    parser.add_argument("--scale", type=float, default=2.0, help="EPA logicDepth scale to test in strategy=epa mode.")
    parser.add_argument("--base-tag-boost", type=float, default=0.03)
    args = parser.parse_args(argv)

    queries = list(_load_queries(args.suite_dir))
    if not queries:
        print(f"no eval queries found under {args.suite_dir}", file=sys.stderr)
        return 2

    cold = run_diag(
        label="Cold-start",
        docs_dir=args.docs,
        queries=queries,
        epa_min_k=8,
        scale=args.scale,
        base_tag_boost=args.base_tag_boost,
    )
    real = run_diag(
        label="Real-PCA",
        docs_dir=args.docs,
        queries=queries,
        epa_min_k=4,
        scale=args.scale,
        base_tag_boost=args.base_tag_boost,
    )

    print("=== EPA Diagnostic ===")
    print(f"Queries: {len(queries)}")
    _print_run(cold)
    _print_run(real)

    std_pass = real.alpha.std > MIN_ALPHA_STD
    range_pass = real.alpha.range_over_mean > 0.1
    energy_sum = float(sum(real.explained_variance_ratio))
    energy_pass = real.train_kind == "real-pca" and energy_sum > 0.5
    print(f"  std(alpha) > {MIN_ALPHA_STD:g}:              {_status(std_pass)}")
    print(f"  range(alpha)/mean(alpha) > 0.1:   {_status(range_pass)}")
    print(f"  pca explained_variance sum > 0.5: {_status(energy_pass)}")

    overall = std_pass and range_pass and energy_pass
    print(f"\n=> overall: {_status(overall)}")
    return 0 if overall else 1


def run_diag(
    *,
    label: str,
    docs_dir: Path,
    queries: list[str],
    epa_min_k: int,
    scale: float,
    base_tag_boost: float,
) -> DiagRun:
    with tempfile.TemporaryDirectory(prefix="epa-diag-") as tmp:
        tmp_root = Path(tmp)
        cfg = Settings(
            storage=StorageConfig(data_dir=str(tmp_root / "data")),
            manual_library={"registry_path": str(tmp_root / "manual_registry.sqlite3")},  # type: ignore[arg-type]
            model={"provider": "hashing", "dim": 64, "batch_size": 16},  # type: ignore[arg-type]
            wave_phase0={"epa_min_k": epa_min_k},  # type: ignore[arg-type]
            wave_phase1={  # type: ignore[arg-type]
                "spike_enabled": True,
                "dynamic_boost_factor_strategy": "epa",
                "epa_logic_depth_scale": scale,
            },
            search={"tag_boost": base_tag_boost},  # type: ignore[arg-type]
        )
        embedder = HashingEmbedder(dim=64)
        build_kb(docs_dir, "default", cfg, embedder=embedder)
        basis = load_epa_basis(basis_path(cfg))
        if basis is None:
            raise RuntimeError(f"EPA basis was not written for {label}")

        projector = EPAProjector(basis)
        logic_depth_values: list[float] = []
        alpha_values: list[float] = []
        for query in queries:
            query_vec = embedder.encode_query(query)
            projection = projector.project(query_vec)
            logic_depth_values.append(float(projection["logicDepth"]))
            _reset_matrix_cache_for_tests()
            _boosted, info = apply_tag_boost(
                query_vec,
                kb_name="default",
                settings=cfg,
                base_tag_boost=base_tag_boost,
            )
            alpha_values.append(float(info.boost_factor_applied))

        return DiagRun(
            label=label,
            train_kind=basis.train_kind,
            K=basis.K,
            tag_count=basis.tag_count_at_train,
            explained_variance_ratio=_explained_variance_ratio(cfg, basis.K),
            logic_depth=_stats(logic_depth_values),
            alpha=_stats(alpha_values),
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


def _explained_variance_ratio(cfg: Settings, K: int) -> tuple[float, ...]:
    registry = create_registry(cfg.manual_library.registry_path)
    rows: list[np.ndarray] = []
    with registry.connection() as conn:
        for tag in iter_canonical_tags_with_vectors(conn):
            if tag.vector is None or tag.embedding_dim != cfg.model.dim:
                continue
            vector = np.frombuffer(tag.vector, dtype=np.float32)
            if vector.shape == (cfg.model.dim,):
                rows.append(vector)
    if len(rows) < 2:
        return ()

    from sklearn.cluster import KMeans
    from sklearn.decomposition import PCA

    vectors = np.stack(rows).astype(np.float32)
    n_clusters = min(max(1, cfg.wave_phase0.epa_cluster_count), vectors.shape[0])
    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    kmeans.fit(vectors)
    centroids = np.asarray(kmeans.cluster_centers_, dtype=np.float32)
    cluster_sizes = np.bincount(kmeans.labels_, minlength=n_clusters).astype(np.float32)
    weighted_mean = (centroids * cluster_sizes.reshape(-1, 1)).sum(axis=0) / cluster_sizes.sum()
    centered = (centroids - weighted_mean) * np.sqrt(cluster_sizes).reshape(-1, 1)
    pca = PCA(n_components=min(n_clusters, vectors.shape[1]), random_state=42)
    pca.fit(centered)
    return tuple(float(value) for value in pca.explained_variance_ratio_[:K])


def _stats(values: list[float]) -> SeriesStats:
    arr = np.asarray(values, dtype=np.float64)
    return SeriesStats(
        mean=float(arr.mean()),
        std=float(arr.std()),
        minimum=float(arr.min()),
        maximum=float(arr.max()),
    )


def _print_run(run: DiagRun) -> None:
    print(f"\n{run.label}: train_kind={run.train_kind}  K={run.K}  tag_count={run.tag_count}")
    if run.train_kind == "real-pca":
        ratios = ", ".join(f"{value:.4f}" for value in run.explained_variance_ratio)
        print(f"  PCA explained_variance_ratio: [{ratios}] sum_top_K={sum(run.explained_variance_ratio):.4f}")
    else:
        print("  PCA explained_variance_ratio: N/A (cold-start)")
    print(
        "  logicDepth: "
        f"mean={run.logic_depth.mean:.6f} std={run.logic_depth.std:.6f} "
        f"range=[{run.logic_depth.minimum:.6f}, {run.logic_depth.maximum:.6f}]"
    )
    print(
        "  alpha:      "
        f"mean={run.alpha.mean:.6f} std={run.alpha.std:.6f} "
        f"range=[{run.alpha.minimum:.6f}, {run.alpha.maximum:.6f}] "
        f"range/mean={run.alpha.range_over_mean:.6f}"
    )


def _status(value: bool) -> str:
    return "PASS" if value else "FAIL"


if __name__ == "__main__":
    raise SystemExit(main())
