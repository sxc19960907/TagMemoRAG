from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from tagmemorag.config import Settings, StorageConfig, load_config
from tagmemorag.embedder import create_embedder
from tagmemorag.metadata_narrowing import infer_metadata_narrowing, merge_inferred_filters
from tagmemorag.retrieval import DEFAULT_TOKEN_BUDGET, build_retrieve_response, context_evidence_diagnostics
from tagmemorag.search_runtime import execute_search
from tagmemorag.state import build_kb

from .dataset import EvalSuiteError, load_eval_suite
from .matching import match_expectations


def run_context_quality_diagnostic(
    *,
    suite_path: str | Path,
    docs_path: str | Path,
    config_path: str | Path,
    kb_name: str,
    top_k: int = 5,
    source_k: int | None = None,
    token_budget: int = DEFAULT_TOKEN_BUDGET,
    eval_data_dir: str | Path | None = None,
) -> dict[str, Any]:
    docs = Path(docs_path)
    if not docs.exists():
        raise EvalSuiteError(f"docs path does not exist: {docs}")
    if top_k <= 0:
        raise EvalSuiteError("top_k must be a positive integer")

    cfg = load_config(config_path)
    run_cfg = _isolated_config(cfg, eval_data_dir)
    cases = [case for case in load_eval_suite(suite_path) if case.kb_name == kb_name]
    if not cases:
        raise EvalSuiteError(f"No eval cases found for kb {kb_name!r}")

    embedder = _create_embedder_from_config(run_cfg)
    state = build_kb(docs, kb_name, run_cfg, embedder=embedder)
    resolved_source_k = source_k if source_k is not None else run_cfg.search.source_k

    case_reports = []
    for ordinal, case in enumerate(cases, 1):
        case_top_k = case.top_k_override or top_k
        query_vec = embedder.encode_query(case.query)
        narrowing = infer_metadata_narrowing(
            query_text=case.query,
            graph=state.graph,
            explicit_filters=None,
            enabled=run_cfg.search.metadata_narrowing_enabled,
            category_policy=run_cfg.search.metadata_narrowing_category_policy,
            brand_policy=run_cfg.search.metadata_narrowing_brand_policy,
            min_candidates=run_cfg.search.metadata_narrowing_min_candidates,
        )
        execution = execute_search(
            state=state,
            query_vec=query_vec,
            settings=run_cfg,
            query_text=case.query,
            top_k=case_top_k,
            source_k=resolved_source_k,
            steps=run_cfg.search.steps,
            decay=run_cfg.search.decay,
            amplitude_cutoff=run_cfg.search.amplitude_cutoff,
            aggregate=run_cfg.search.aggregate,
            filters=merge_inferred_filters(None, narrowing),
            boost_filters=narrowing.boost_filters,
        )
        retrieve_payload = build_retrieve_response(
            results=execution.results,
            build_id=state.build_id,
            kb_name=state.kb_name,
            trace_id="diag-context-quality",
            search_id=f"diag-context-search-{ordinal:03d}",
            retrieve_id=f"diag-context-retrieve-{ordinal:03d}",
            token_budget=token_budget,
            query_text=case.query,
        )
        rank_matches = match_expectations(execution.results, case.relevant, case_id=case.id)
        diagnostics = context_evidence_diagnostics(retrieve_payload, query_text=case.query)
        evidence_expected_matches = [
            {
                "rank": rank,
                "evidence_id": diagnostics[rank - 1]["evidence_id"],
                "expected_indexes": sorted(matches),
                "selected": bool(diagnostics[rank - 1]["selected"]),
                "context_rank": diagnostics[rank - 1]["context_rank"],
            }
            for rank, matches in enumerate(rank_matches, 1)
            if matches
        ]
        selected_expected = [item for item in evidence_expected_matches if item["selected"]]
        case_reports.append(
            {
                "id": case.id,
                "query": case.query,
                "top_k": case_top_k,
                "retrieved_expected_count": len(evidence_expected_matches),
                "selected_expected_count": len(selected_expected),
                "context_item_count": len((retrieve_payload.get("context_pack") or {}).get("items") or []),
                "answerable": bool((retrieve_payload.get("answerability") or {}).get("answerable")),
                "evidence_expected_matches": evidence_expected_matches,
                "context_diagnostics": diagnostics,
            }
        )

    cases_with_expected = sum(1 for case in case_reports if case["retrieved_expected_count"] > 0)
    cases_with_selected_expected = sum(1 for case in case_reports if case["selected_expected_count"] > 0)
    return {
        "schema_version": "context_quality_eval.v1",
        "suite": str(suite_path),
        "docs": str(docs),
        "kb_name": kb_name,
        "summary": {
            "cases": len(case_reports),
            "cases_with_expected_retrieved": cases_with_expected,
            "cases_with_expected_selected": cases_with_selected_expected,
            "selected_expected_rate": round(cases_with_selected_expected / max(1, len(case_reports)), 6),
        },
        "cases": case_reports,
    }


def _isolated_config(cfg: Settings, eval_data_dir: str | Path | None) -> Settings:
    run_cfg = cfg.model_copy(deep=True)
    data_dir = Path(eval_data_dir) if eval_data_dir is not None else Path(".tmp") / "eval" / uuid4().hex
    run_cfg.storage = StorageConfig(data_dir=str(data_dir), schema_version=cfg.storage.schema_version)
    return run_cfg


def _create_embedder_from_config(cfg: Settings):
    return create_embedder(
        cfg.model.name,
        cfg.model.device,
        cfg.model.batch_size,
        cfg.model.dim,
        provider=cfg.model.provider,
        base_url=cfg.model.base_url,
        embeddings_url=cfg.model.embeddings_url,
        api_key_env=cfg.model.api_key_env,
        timeout_seconds=cfg.model.timeout_seconds,
        dimensions=cfg.model.dimensions,
        normalize=cfg.model.normalize,
    )
