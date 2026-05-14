from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import time

import numpy as np

from tagmemorag.config import ManualLibraryConfig, Settings, StorageConfig
from tagmemorag.epa_basis import basis_path, build_cold_start_basis, epa_basis_lock, load_epa_basis, retrain_if_needed, save_epa_basis
from tagmemorag.manual_registry import create_registry
from tagmemorag.tag_store import upsert_canonical_tag


def _cfg(tmp_path) -> Settings:
    return Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "data")),
        manual_library=ManualLibraryConfig(registry_path=str(tmp_path / "manual_registry.sqlite3")),
        model={"dim": 8},
    )


def test_epa_basis_lock_serializes_writers(tmp_path):
    lock_path = tmp_path / "epa_basis.lock"
    events: list[str] = []

    def worker(name: str) -> None:
        with epa_basis_lock(lock_path, timeout_sec=2.0):
            events.append(f"{name}:start")
            time.sleep(0.05)
            events.append(f"{name}:end")

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(worker, "a"), pool.submit(worker, "b")]
        for future in futures:
            future.result()

    assert events in (
        ["a:start", "a:end", "b:start", "b:end"],
        ["b:start", "b:end", "a:start", "a:end"],
    )


def test_retrain_concurrent_calls_leave_one_valid_basis(tmp_path):
    cfg = _cfg(tmp_path)
    with create_registry(cfg.manual_library.registry_path).connection() as conn:
        tag_id = upsert_canonical_tag(conn, "default", "maintenance")
        conn.execute(
            "UPDATE tags SET vector=?, embedding_dim=?, embedded_at=? WHERE id=?",
            (np.eye(8, dtype=np.float32)[0].tobytes(), 8, "2026-05-14T00:00:00+00:00", tag_id),
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        reports = list(pool.map(lambda _index: retrain_if_needed(cfg, force=True), range(2)))
    loaded = load_epa_basis(basis_path(cfg))

    assert all(report is not None for report in reports)
    assert loaded is not None
    assert loaded.train_kind == "cold-start"
    assert loaded.tag_count_at_train == 1


def test_tmp_file_is_ignored_when_loading_final_basis(tmp_path):
    path = tmp_path / "epa_basis.npz"
    basis = build_cold_start_basis(8, 4, tag_count_at_train=1)
    save_epa_basis(path, basis)
    path.with_name(path.name + ".tmp").write_bytes(b"partial")

    loaded = load_epa_basis(path)

    assert loaded is not None
    assert loaded.train_kind == "cold-start"
