"""AC6 baseline invariance: execute_search output must be byte-identical with
and without the Phase 0 tag tables / EPA basis. Phase 0 is a pure data layer
addition; if the search path ever starts reading the tag store, this test
will fail and force a deliberate update to the baseline.
"""
from __future__ import annotations

import json
import shutil
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

import numpy as np

from tagmemorag.config import Settings
from tagmemorag.search_runtime import execute_search
from tagmemorag.state import build_kb


_QUERIES = ("蒸汽很小", "清洗", "E05 故障")


def _serialize_results(results) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for item in results:
        if is_dataclass(item):
            payload.append(asdict(item))
        elif isinstance(item, dict):
            payload.append(item)
        else:
            payload.append({"node_id": getattr(item, "node_id", None), "score": getattr(item, "score", None)})
    return payload


def _run_searches(state, embedder, settings: Settings) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for query in _QUERIES:
        query_vec = embedder.encode_query(query)
        execution = execute_search(
            state=state,
            query_vec=np.asarray(query_vec, dtype=np.float32),
            settings=settings,
            top_k=settings.search.top_k,
            source_k=settings.search.source_k,
            steps=settings.search.steps,
            decay=settings.search.decay,
            amplitude_cutoff=settings.search.amplitude_cutoff,
            aggregate=settings.search.aggregate,
            query_text=query,
        )
        out.append(
            {
                "query": query,
                "results": _serialize_results(execution.results),
                "strategy": execution.strategy,
                "ann_candidate_count": execution.ann_candidate_count,
                "lexical_candidate_count": execution.lexical_candidate_count,
                "lexical_source_count": execution.lexical_source_count,
                "lexical_profile": execution.lexical_profile,
            }
        )
    return out


def test_search_output_invariant_after_phase0_data_purge(test_config: Settings, fake_embedder) -> None:
    docs_dir = Path(__file__).parents[1] / "fixtures"
    state = build_kb(docs_dir, "default", test_config, embedder=fake_embedder)
    baseline = _run_searches(state, fake_embedder, test_config)

    registry_path = Path(test_config.storage.data_dir) / "manual_registry.sqlite3"
    epa_dir = Path(test_config.storage.data_dir) / "_global"
    assert registry_path.exists(), "Phase 0 must populate manual_registry.sqlite3"
    assert (epa_dir / "epa_basis.npz").exists(), "Phase 0 must produce EPA basis"

    registry_path.unlink()
    shutil.rmtree(epa_dir, ignore_errors=True)

    rebuilt_state = build_kb(docs_dir, "default", test_config, embedder=fake_embedder)
    after_purge = _run_searches(rebuilt_state, fake_embedder, test_config)

    assert json.dumps(baseline, ensure_ascii=False, sort_keys=True) == json.dumps(
        after_purge, ensure_ascii=False, sort_keys=True
    )


def test_search_output_invariant_when_phase0_disabled(test_config: Settings, fake_embedder) -> None:
    docs_dir = Path(__file__).parents[1] / "fixtures"
    state = build_kb(docs_dir, "default", test_config, embedder=fake_embedder)
    baseline = _run_searches(state, fake_embedder, test_config)

    disabled_cfg = test_config.model_copy(
        update={
            "wave_phase0": test_config.wave_phase0.model_copy(
                update={"enabled": False, "epa_basis_enabled": False}
            )
        }
    )
    after_disabled = _run_searches(state, fake_embedder, disabled_cfg)

    assert json.dumps(baseline, ensure_ascii=False, sort_keys=True) == json.dumps(
        after_disabled, ensure_ascii=False, sort_keys=True
    )
