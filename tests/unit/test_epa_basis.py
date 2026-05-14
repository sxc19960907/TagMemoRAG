from __future__ import annotations

import numpy as np
import pytest

from tagmemorag.config import ManualLibraryConfig, Settings, StorageConfig
from tagmemorag.epa_basis import (
    COLD_START,
    EPA_BASIS_SCHEMA_VERSION,
    REAL_PCA,
    basis_path,
    build_cold_start_basis,
    load_epa_basis,
    retrain_if_needed,
    save_epa_basis,
    train_real_pca,
)
from tagmemorag.epa_projector import EPAProjector
from tagmemorag.errors import ServiceError
from tagmemorag.manual_registry import create_registry
from tagmemorag.tag_store import upsert_canonical_tag


def _cfg(tmp_path, *, dim: int = 8) -> Settings:
    return Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "data")),
        manual_library=ManualLibraryConfig(registry_path=str(tmp_path / "manual_registry.sqlite3")),
        model={"dim": dim},
    )


def _insert_vector_tag(cfg: Settings, name: str, vector: np.ndarray) -> None:
    with create_registry(cfg.manual_library.registry_path).connection() as conn:
        tag_id = upsert_canonical_tag(conn, "default", name)
        conn.execute(
            "UPDATE tags SET vector=?, embedding_dim=?, embedded_at=? WHERE id=?",
            (np.asarray(vector, dtype=np.float32).tobytes(), int(vector.shape[0]), "2026-05-14T00:00:00+00:00", tag_id),
        )


def test_cold_start_basis_uses_identity_rows():
    basis = build_cold_start_basis(8, 4, tag_count_at_train=3)

    assert basis.train_kind == COLD_START
    assert basis.K == 4
    assert basis.dim == 8
    assert basis.tag_count_at_train == 3
    np.testing.assert_allclose(basis.orthoBasis, np.eye(8, dtype=np.float32)[:4])
    np.testing.assert_allclose(basis.basisMean, np.zeros(8, dtype=np.float32))
    assert basis.basisLabels == ["axis-0", "axis-1", "axis-2", "axis-3"]


def test_save_load_roundtrip_and_projector(tmp_path):
    path = tmp_path / "epa_basis.npz"
    basis = build_cold_start_basis(8, 4, tag_count_at_train=2)

    save_epa_basis(path, basis)
    loaded = load_epa_basis(path)
    assert loaded is not None
    projected = EPAProjector(loaded).project(np.array([1, 2, 0, 0, 0, 0, 0, 0], dtype=np.float32))

    assert loaded.schema_version == EPA_BASIS_SCHEMA_VERSION
    assert loaded.train_kind == COLD_START
    np.testing.assert_allclose(loaded.orthoBasis, basis.orthoBasis)
    assert projected["dominantAxes"][0]["label"] == "axis-1"
    assert projected["logicDepth"] > 0


def test_load_rejects_unknown_schema_version(tmp_path):
    path = tmp_path / "epa_basis.npz"
    basis = build_cold_start_basis(8, 4)
    save_epa_basis(path, basis)
    with np.load(path, allow_pickle=True) as npz:
        payload = {key: npz[key] for key in npz.files}
    payload["meta_schema_version"] = np.int32(2)
    with path.open("wb") as handle:
        np.savez(handle, **payload)

    with pytest.raises(ServiceError) as exc:
        load_epa_basis(path)

    assert exc.value.code == "STORAGE_SCHEMA_MISMATCH"
    assert exc.value.detail["actual"] == 2


def test_train_real_pca_selects_real_basis():
    rng = np.random.default_rng(42)
    vectors = rng.normal(size=(20, 8)).astype(np.float32)
    names = [f"tag-{index}" for index in range(vectors.shape[0])]

    basis = train_real_pca(vectors, names, cluster_count=16, min_K=4, energy_threshold=0.90)

    assert basis.train_kind == REAL_PCA
    assert basis.K >= 4
    assert basis.orthoBasis.shape == (basis.K, 8)
    assert len(basis.basisLabels) == basis.K
    assert set(basis.basisLabels).issubset(set(names))


def test_retrain_if_needed_cold_starts_then_graduates(tmp_path):
    cfg = _cfg(tmp_path, dim=8)
    for index in range(3):
        vector = np.zeros(8, dtype=np.float32)
        vector[index] = 1.0
        _insert_vector_tag(cfg, f"cold-{index}", vector)

    first = retrain_if_needed(cfg, force=True)
    cold = load_epa_basis(basis_path(cfg))

    rng = np.random.default_rng(7)
    for index, vector in enumerate(rng.normal(size=(16, 8)).astype(np.float32), start=3):
        _insert_vector_tag(cfg, f"real-{index}", vector)
    second = retrain_if_needed(cfg, force=True)
    real = load_epa_basis(basis_path(cfg))

    assert first is not None
    assert first["epa_basis_train_kind"] == COLD_START
    assert cold is not None and cold.train_kind == COLD_START
    assert second is not None
    assert second["epa_basis_train_kind"] == REAL_PCA
    assert real is not None and real.train_kind == REAL_PCA
    assert real.tag_count_at_train == 19
