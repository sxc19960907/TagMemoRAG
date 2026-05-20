from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import fcntl
import os
from pathlib import Path
import time
from typing import TYPE_CHECKING, Iterator, Sequence

import numpy as np

from .config import Settings
from .errors import ErrorCode, ServiceError
from .manual_registry import create_registry
from .observability.metrics import get_metrics
from .tag_store import StoredTag, iter_canonical_tags_with_vectors

if TYPE_CHECKING:  # pragma: no cover
    from .indexgen import KbPaths

EPA_BASIS_SCHEMA_VERSION = 1
COLD_START = "cold-start"
REAL_PCA = "real-pca"


@dataclass(frozen=True)
class EPABasis:
    orthoBasis: np.ndarray
    basisMean: np.ndarray
    basisEnergies: np.ndarray
    basisLabels: list[str]
    K: int
    dim: int
    train_kind: str
    tag_count_at_train: int
    trained_at: str = ""
    schema_version: int = EPA_BASIS_SCHEMA_VERSION

    def to_dict(self) -> dict[str, object]:
        return {
            "orthoBasis": self.orthoBasis,
            "basisMean": self.basisMean,
            "basisEnergies": self.basisEnergies,
            "basisLabels": self.basisLabels,
            "K": self.K,
            "dim": self.dim,
            "train_kind": self.train_kind,
            "tag_count_at_train": self.tag_count_at_train,
            "trained_at": self.trained_at,
            "schema_version": self.schema_version,
        }


def basis_path(cfg: Settings, paths: "KbPaths | None" = None) -> Path:
    if paths is not None:
        return paths.epa_basis
    return Path(cfg.storage.data_dir) / "_global" / "epa_basis.npz"


def basis_lock_path(cfg: Settings, paths: "KbPaths | None" = None) -> Path:
    if paths is not None:
        return paths.generation_root / "epa_basis.lock"
    return Path(cfg.storage.data_dir) / "_global" / "epa_basis.lock"


def basis_dirty_path(cfg: Settings, paths: "KbPaths | None" = None) -> Path:
    if paths is not None:
        return paths.generation_root / "epa_basis.dirty"
    return Path(cfg.storage.data_dir) / "_global" / "epa_basis.dirty"


def mark_epa_basis_dirty(cfg: Settings, paths: "KbPaths | None" = None) -> None:
    path = basis_dirty_path(cfg, paths)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_now(), encoding="utf-8")


@contextmanager
def epa_basis_lock(lock_path: Path, timeout_sec: float = 30.0) -> Iterator[None]:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.touch(exist_ok=True)
    fd = os.open(lock_path, os.O_RDWR)
    deadline = time.monotonic() + timeout_sec
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"epa_basis lock contention exceeded {timeout_sec}s")
                time.sleep(0.05)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def build_cold_start_basis(dim: int, K: int = 8, *, tag_count_at_train: int = 0) -> EPABasis:
    if K < 1 or K > dim:
        raise ValueError(f"K must be between 1 and dim; got K={K}, dim={dim}")
    return EPABasis(
        orthoBasis=np.eye(dim, dtype=np.float32)[:K],
        basisMean=np.zeros(dim, dtype=np.float32),
        basisEnergies=np.ones(K, dtype=np.float32),
        basisLabels=[f"axis-{index}" for index in range(K)],
        K=K,
        dim=dim,
        train_kind=COLD_START,
        tag_count_at_train=tag_count_at_train,
        trained_at=_now(),
    )


def train_real_pca(
    tag_vectors: np.ndarray,
    tag_names: Sequence[str],
    *,
    cluster_count: int = 32,
    min_K: int = 8,
    energy_threshold: float = 0.95,
) -> EPABasis:
    vectors = np.asarray(tag_vectors, dtype=np.float32)
    if vectors.ndim != 2 or vectors.shape[0] == 0:
        raise ValueError("tag_vectors must be a non-empty 2D array")
    if len(tag_names) != vectors.shape[0]:
        raise ValueError("tag_names length must match tag_vectors rows")

    from sklearn.cluster import KMeans
    from sklearn.decomposition import PCA

    tag_count, dim = vectors.shape
    n_clusters = min(max(1, cluster_count), tag_count)
    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    kmeans.fit(vectors)
    centroids = np.asarray(kmeans.cluster_centers_, dtype=np.float32)
    cluster_sizes = np.bincount(kmeans.labels_, minlength=n_clusters).astype(np.float32)
    weighted_mean = (centroids * cluster_sizes.reshape(-1, 1)).sum(axis=0) / cluster_sizes.sum()
    centered = (centroids - weighted_mean) * np.sqrt(cluster_sizes).reshape(-1, 1)

    component_count = min(n_clusters, dim)
    pca = PCA(n_components=component_count, random_state=42)
    pca.fit(centered)
    ratios = np.asarray(pca.explained_variance_ratio_, dtype=np.float64)
    if ratios.size and np.isfinite(ratios).all() and ratios.sum() > 0:
        selected = int(np.searchsorted(np.cumsum(ratios), energy_threshold) + 1)
    else:
        selected = min_K
    K = min(max(selected, min_K), pca.components_.shape[0])

    basis = np.asarray(pca.components_[:K], dtype=np.float32)
    labels = _labels_for_axes(basis, vectors, tag_names)
    energies = np.asarray(pca.explained_variance_[:K], dtype=np.float32)
    if energies.shape[0] < K:
        energies = np.pad(energies, (0, K - energies.shape[0]), constant_values=0.0).astype(np.float32)

    return EPABasis(
        orthoBasis=basis,
        basisMean=np.asarray(weighted_mean, dtype=np.float32),
        basisEnergies=energies,
        basisLabels=labels,
        K=K,
        dim=dim,
        train_kind=REAL_PCA,
        tag_count_at_train=tag_count,
        trained_at=_now(),
    )


def save_epa_basis(path: Path, basis: EPABasis) -> None:
    _validate_basis_shapes(basis)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("wb") as handle:
        np.savez(
            handle,
            orthoBasis=np.asarray(basis.orthoBasis, dtype=np.float32),
            basisMean=np.asarray(basis.basisMean, dtype=np.float32),
            basisEnergies=np.asarray(basis.basisEnergies, dtype=np.float32),
            basisLabels=np.asarray(basis.basisLabels, dtype=object),
            meta_K=np.int32(basis.K),
            meta_dim=np.int32(basis.dim),
            meta_train_kind=np.asarray(basis.train_kind, dtype=object),
            meta_tag_count_at_train=np.int32(basis.tag_count_at_train),
            meta_trained_at=np.asarray(basis.trained_at or _now(), dtype=object),
            meta_schema_version=np.int32(EPA_BASIS_SCHEMA_VERSION),
        )
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)
    dir_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


def load_epa_basis(path: Path) -> EPABasis | None:
    if not path.exists():
        return None
    try:
        with np.load(path, allow_pickle=True) as npz:
            schema_version = int(npz["meta_schema_version"])
            if schema_version != EPA_BASIS_SCHEMA_VERSION:
                raise ServiceError(
                    ErrorCode.STORAGE_SCHEMA_MISMATCH,
                    "EPA basis schema version is not supported.",
                    {"expected": EPA_BASIS_SCHEMA_VERSION, "actual": schema_version, "path": str(path)},
                )
            basis = EPABasis(
                orthoBasis=np.asarray(npz["orthoBasis"], dtype=np.float32),
                basisMean=np.asarray(npz["basisMean"], dtype=np.float32),
                basisEnergies=np.asarray(npz["basisEnergies"], dtype=np.float32),
                basisLabels=[str(item) for item in npz["basisLabels"].tolist()],
                K=int(npz["meta_K"]),
                dim=int(npz["meta_dim"]),
                train_kind=str(npz["meta_train_kind"].item()),
                tag_count_at_train=int(npz["meta_tag_count_at_train"]),
                trained_at=str(npz["meta_trained_at"].item()),
                schema_version=schema_version,
            )
    except ServiceError:
        raise
    except Exception as exc:
        raise ServiceError(
            ErrorCode.STORAGE_LOAD_FAILED,
            "Failed to load EPA basis.",
            {"path": str(path), "error_type": type(exc).__name__},
        ) from exc
    _validate_basis_shapes(basis)
    return basis


def retrain_if_needed(
    cfg: Settings,
    *,
    force: bool = False,
    paths: "KbPaths | None" = None,
) -> dict[str, object] | None:
    if not cfg.wave_phase0.enabled or not cfg.wave_phase0.epa_basis_enabled:
        return None

    path = basis_path(cfg, paths)
    with epa_basis_lock(basis_lock_path(cfg, paths), timeout_sec=cfg.wave_phase0.epa_lock_timeout_seconds):
        dirty_path = basis_dirty_path(cfg, paths)
        dirty = dirty_path.exists()
        current = load_epa_basis(path)
        rows = _load_global_tag_vectors(cfg)
        tag_count = len(rows)
        if not force and not dirty and current is not None and _within_growth_threshold(
            tag_count,
            current.tag_count_at_train,
            cfg.wave_phase0.epa_retrain_growth_ratio,
        ):
            return None

        min_k = cfg.wave_phase0.epa_min_k
        if tag_count < min_k * 2:
            basis = build_cold_start_basis(cfg.model.dim, min_k, tag_count_at_train=tag_count)
        else:
            names = [row.name for row, _vector in rows]
            vectors = np.stack([vector for _row, vector in rows]).astype(np.float32)
            basis = train_real_pca(
                vectors,
                names,
                cluster_count=cfg.wave_phase0.epa_cluster_count,
                min_K=min_k,
                energy_threshold=cfg.wave_phase0.epa_energy_threshold,
            )
        save_epa_basis(path, basis)
        dirty_path.unlink(missing_ok=True)
        return {
            "epa_basis_train_kind": basis.train_kind,
            "epa_basis_K": basis.K,
            "epa_basis_tag_count": basis.tag_count_at_train,
        }


def retrain_report(
    cfg: Settings,
    *,
    force: bool = False,
    paths: "KbPaths | None" = None,
) -> dict[str, object]:
    started = time.perf_counter()
    try:
        report = retrain_if_needed(cfg, force=force, paths=paths)
    except Exception as exc:
        get_metrics().record_epa_basis_retrain(outcome="failed", duration=time.perf_counter() - started)
        return {"epa_train_error": type(exc).__name__}
    duration = time.perf_counter() - started
    if report is None:
        get_metrics().record_epa_basis_retrain(outcome="skipped", duration=duration)
        current = load_epa_basis(basis_path(cfg, paths))
        if current is None:
            return {}
        return {
            "epa_basis_train_kind": current.train_kind,
            "epa_basis_K": current.K,
            "epa_basis_tag_count": current.tag_count_at_train,
        }
    train_kind = str(report.get("epa_basis_train_kind", "") or "skipped")
    get_metrics().record_epa_basis_retrain(outcome=train_kind, duration=duration)
    return report | {"epa_train_error": ""}


def _load_global_tag_vectors(cfg: Settings) -> list[tuple[StoredTag, np.ndarray]]:
    registry = create_registry(_phase0_registry_path(cfg))
    loaded: list[tuple[StoredTag, np.ndarray]] = []
    with registry.connection() as conn:
        for tag in iter_canonical_tags_with_vectors(conn):
            vector = _decode_tag_vector(tag, expected_dim=cfg.model.dim)
            if vector is not None:
                loaded.append((tag, vector))
    return loaded


def _decode_tag_vector(tag: StoredTag, *, expected_dim: int) -> np.ndarray | None:
    if tag.vector is None or tag.embedding_dim != expected_dim:
        return None
    vector = np.frombuffer(tag.vector, dtype=np.float32)
    if vector.shape != (expected_dim,):
        return None
    return np.asarray(vector, dtype=np.float32)


def _within_growth_threshold(current_count: int, trained_count: int, growth_ratio: float) -> bool:
    if trained_count <= 0:
        return current_count == 0
    return abs(current_count - trained_count) / trained_count < growth_ratio


def _labels_for_axes(basis: np.ndarray, tag_vectors: np.ndarray, tag_names: Sequence[str]) -> list[str]:
    vector_norms = np.linalg.norm(tag_vectors, axis=1, keepdims=True)
    normalized_vectors = tag_vectors / np.maximum(vector_norms, 1e-12)
    axis_norms = np.linalg.norm(basis, axis=1, keepdims=True)
    normalized_axes = basis / np.maximum(axis_norms, 1e-12)
    sims = np.abs(normalized_axes @ normalized_vectors.T)
    return [str(tag_names[int(index)]) for index in sims.argmax(axis=1)]


def _validate_basis_shapes(basis: EPABasis) -> None:
    if basis.train_kind not in {COLD_START, REAL_PCA}:
        raise ValueError(f"unsupported EPA train_kind={basis.train_kind}")
    if basis.orthoBasis.shape != (basis.K, basis.dim):
        raise ValueError("EPA orthoBasis shape does not match K and dim")
    if basis.basisMean.shape != (basis.dim,):
        raise ValueError("EPA basisMean shape does not match dim")
    if basis.basisEnergies.shape != (basis.K,):
        raise ValueError("EPA basisEnergies shape does not match K")
    if len(basis.basisLabels) != basis.K:
        raise ValueError("EPA basisLabels length does not match K")


def _phase0_registry_path(cfg: Settings) -> str | Path:
    if cfg.manual_library.registry_path == "data/manual_registry.sqlite3":
        return Path(cfg.storage.data_dir) / "manual_registry.sqlite3"
    return cfg.manual_library.registry_path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
