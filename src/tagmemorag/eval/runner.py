from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from uuid import uuid4

from tagmemorag.config import Settings, StorageConfig
from tagmemorag.embedder import create_embedder
from tagmemorag.metadata_narrowing import infer_metadata_narrowing, merge_inferred_filters
from tagmemorag.search_runtime import execute_search
from tagmemorag.state import build_kb, load_kb, save_kb

from .dataset import EvalCase, EvalSuiteError, EvalThresholds, load_eval_suite
from .matching import NegativeHit, match_expectations, match_negatives
from .metrics import aggregate_metrics, compute_ranking_metrics
from .report import EvalCaseReport, EvalReport, EvalSummary, expected_to_dict

DEFAULT_THRESHOLDS = EvalThresholds(min_recall_at_k=0.8, min_mrr=0.75, min_hit_at_k=0.8)
BASELINE_FLOOR_DELTA = 0.02


def run_eval(
    *,
    cfg: Settings,
    suite_path: str | Path,
    docs_path: str | Path | None = None,
    top_k: int | None = None,
    source_k: int | None = None,
    steps: int | None = None,
    decay: float | None = None,
    amplitude_cutoff: float | None = None,
    aggregate: str | None = None,
    metadata_field_boost: float | None = None,
    tag_boost: float | None = None,
    kb_filter: str | None = None,
    reuse_built_kb: bool = False,
    eval_data_dir: str | Path | None = None,
    thresholds: EvalThresholds = DEFAULT_THRESHOLDS,
) -> EvalReport:
    resolved_top_k = top_k or cfg.search.top_k or 5
    _validate_top_k(resolved_top_k)
    _validate_thresholds(thresholds)
    search_params = _resolve_search_params(
        cfg,
        source_k=source_k,
        steps=steps,
        decay=decay,
        amplitude_cutoff=amplitude_cutoff,
        aggregate=aggregate,
        metadata_field_boost=metadata_field_boost,
        tag_boost=tag_boost,
    )
    cases = load_eval_suite(suite_path)
    if kb_filter:
        cases = [case for case in cases if case.kb_name == kb_filter]
        if not cases:
            raise EvalSuiteError(f"No eval cases found for kb {kb_filter!r}")
    if not reuse_built_kb and docs_path is None:
        raise EvalSuiteError("--docs is required unless --reuse-built-kb is set")
    run_cfg, storage_snapshot = _resolve_eval_config(cfg, eval_data_dir, reuse_built_kb)
    embedder = _create_embedder_from_config(run_cfg)
    states = {}
    for kb_name in sorted({case.kb_name for case in cases}):
        if reuse_built_kb:
            states[kb_name] = load_kb(kb_name, run_cfg)
        else:
            state = build_kb(docs_path, kb_name, run_cfg, embedder=embedder)
            save_kb(state, run_cfg)
            states[kb_name] = state

    case_reports: list[EvalCaseReport] = []
    for case in cases:
        case_top_k = case.top_k_override or resolved_top_k
        _validate_top_k(case_top_k)
        state = states[case.kb_name]
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
            source_k=int(search_params["source_k"]),
            steps=int(search_params["steps"]),
            decay=float(search_params["decay"]),
            amplitude_cutoff=float(search_params["amplitude_cutoff"]),
            aggregate=str(search_params["aggregate"]),
            filters=merge_inferred_filters(None, narrowing),
            boost_filters=narrowing.boost_filters,
        )
        results = execution.results
        rank_matches = match_expectations(results, case.relevant, case_id=case.id)
        metrics = compute_ranking_metrics(rank_matches, len(case.relevant), case_top_k)
        negative_hits = match_negatives(results[:case_top_k], case.negatives, case_id=case.id)
        threshold_failures = _threshold_failures(metrics.to_dict(), case.thresholds, prefix="case")
        negative_failures = _negative_violations(negative_hits)
        failures = negative_failures + threshold_failures
        passed = not failures
        case_reports.append(
            EvalCaseReport(
                id=case.id,
                query=case.query,
                kb_name=case.kb_name,
                top_k=case_top_k,
                passed=passed,
                metrics=metrics,
                thresholds=case.thresholds,
                expected=[expected_to_dict(item, f"{case.id}#{index + 1}") for index, item in enumerate(case.relevant)],
                actual_top_k=[_result_to_report(result, rank_matches[index] if index < len(rank_matches) else set()) for index, result in enumerate(results)],
                failures=failures,
                search_strategy=execution.strategy,
                ann_candidate_count=execution.ann_candidate_count,
                ann_fallback_reason=execution.ann_fallback_reason,
                negatives=[expected_to_dict(item, f"{case.id}#neg{index + 1}") for index, item in enumerate(case.negatives)],
                negative_hits=[hit.to_dict() for hit in negative_hits],
            )
        )

    aggregate = aggregate_metrics([case.metrics for case in case_reports])
    suite_failures = _threshold_failures(aggregate.to_dict(), thresholds, prefix="suite")
    passed = not suite_failures and all(case.passed for case in case_reports)
    if suite_failures:
        failed_case = EvalCaseReport(
            id="__suite__",
            query="",
            kb_name="",
            top_k=resolved_top_k,
            passed=False,
            metrics=aggregate,
            thresholds=thresholds,
            expected=[],
            actual_top_k=[],
            failures=suite_failures,
        )
        case_reports = [*case_reports, failed_case]
    summary = EvalSummary(cases=len(cases), passed=passed, metrics=aggregate)
    return EvalReport(
        suite=str(suite_path),
        docs=str(docs_path) if docs_path is not None else None,
        kb_names=sorted(states),
        top_k=resolved_top_k,
        thresholds=thresholds,
        summary=summary,
        cases=case_reports,
        config_snapshot={
            "model": {"provider": run_cfg.model.provider, "name": run_cfg.model.name, "dim": run_cfg.model.dim},
            "search": {"top_k": resolved_top_k, **search_params},
            "storage": storage_snapshot,
            "reuse_built_kb": reuse_built_kb,
            "build_ids": {kb_name: states[kb_name].build_id for kb_name in sorted(states)},
        },
    )


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


def _resolve_eval_config(cfg: Settings, eval_data_dir: str | Path | None, reuse_built_kb: bool) -> tuple[Settings, dict[str, str]]:
    if reuse_built_kb:
        return cfg, {"data_dir": cfg.storage.data_dir}
    data_dir = Path(eval_data_dir) if eval_data_dir is not None else Path(".tmp") / "eval" / uuid4().hex
    run_cfg = cfg.model_copy(deep=True)
    run_cfg.storage = StorageConfig(data_dir=str(data_dir), schema_version=cfg.storage.schema_version)
    return run_cfg, {"data_dir": str(data_dir)}


def _threshold_failures(metrics: dict[str, float], thresholds: EvalThresholds, *, prefix: str) -> list[str]:
    failures: list[str] = []
    for metric_name, threshold_name in (
        ("precision_at_k", "min_precision_at_k"),
        ("recall_at_k", "min_recall_at_k"),
        ("mrr", "min_mrr"),
        ("hit_at_k", "min_hit_at_k"),
    ):
        threshold = getattr(thresholds, threshold_name)
        if threshold is not None and metrics[metric_name] < threshold:
            failures.append(f"{prefix} {metric_name} {metrics[metric_name]:.6f} < {threshold:.6f}")
    return failures


def _negative_violations(hits: list[NegativeHit]) -> list[str]:
    return [
        f"negative #{hit.negative_index} matched at rank {hit.rank} ({hit.source_file})"
        for hit in hits
    ]


def _validate_thresholds(thresholds: EvalThresholds) -> None:
    for key, value in thresholds.to_dict().items():
        if value < 0.0 or value > 1.0:
            raise EvalSuiteError(f"{key} must be between 0.0 and 1.0")


def _validate_top_k(top_k: int) -> None:
    if top_k <= 0:
        raise EvalSuiteError("top_k must be a positive integer")


def _resolve_search_params(
    cfg: Settings,
    *,
    source_k: int | None,
    steps: int | None,
    decay: float | None,
    amplitude_cutoff: float | None,
    aggregate: str | None,
    metadata_field_boost: float | None,
    tag_boost: float | None,
) -> dict[str, int | float | str]:
    resolved = {
        "source_k": source_k if source_k is not None else cfg.search.source_k,
        "steps": steps if steps is not None else cfg.search.steps,
        "decay": decay if decay is not None else cfg.search.decay,
        "amplitude_cutoff": amplitude_cutoff if amplitude_cutoff is not None else cfg.search.amplitude_cutoff,
        "aggregate": aggregate if aggregate is not None else cfg.search.aggregate,
        "metadata_field_boost": metadata_field_boost if metadata_field_boost is not None else cfg.search.metadata_field_boost,
        "tag_boost": tag_boost if tag_boost is not None else cfg.search.tag_boost,
        "lexical_enabled": cfg.search.lexical_enabled,
        "lexical_candidate_k": cfg.search.lexical_candidate_k,
        "lexical_source_k": cfg.search.lexical_source_k,
        "lexical_min_token_chars": cfg.search.lexical_min_token_chars,
        "lexical_boost": cfg.search.lexical_boost,
        "lexical_exact_code_boost": cfg.search.lexical_exact_code_boost,
        "lexical_model_boost": cfg.search.lexical_model_boost,
        "metadata_narrowing_enabled": cfg.search.metadata_narrowing_enabled,
        "metadata_narrowing_brand_policy": cfg.search.metadata_narrowing_brand_policy,
        "metadata_narrowing_category_policy": cfg.search.metadata_narrowing_category_policy,
        "metadata_narrowing_min_candidates": cfg.search.metadata_narrowing_min_candidates,
    }
    if int(resolved["source_k"]) <= 0:
        raise EvalSuiteError("source_k must be a positive integer")
    if int(resolved["steps"]) < 0:
        raise EvalSuiteError("steps must be greater than or equal to 0")
    if float(resolved["decay"]) < 0.0:
        raise EvalSuiteError("decay must be greater than or equal to 0.0")
    if float(resolved["amplitude_cutoff"]) < 0.0:
        raise EvalSuiteError("amplitude_cutoff must be greater than or equal to 0.0")
    if str(resolved["aggregate"]) not in {"max", "sum"}:
        raise EvalSuiteError("aggregate must be 'max' or 'sum'")
    if float(resolved["metadata_field_boost"]) < 0.0:
        raise EvalSuiteError("metadata_field_boost must be greater than or equal to 0.0")
    if float(resolved["tag_boost"]) < 0.0:
        raise EvalSuiteError("tag_boost must be greater than or equal to 0.0")
    return resolved


def _result_to_report(result, matched_expected_indexes: set[int]) -> dict:
    data = result.to_dict()
    data["matched_expected_indexes"] = sorted(matched_expected_indexes)
    data["score"] = round(float(data["score"]), 6)
    text = data.get("text", "")
    if isinstance(text, str) and len(text) > 500:
        data["text"] = text[:500]
    return data


def load_baseline(path: str | Path) -> dict[str, dict[str, float]]:
    """Load a baseline JSON written by scripts/build_eval_baseline.py.

    Returns the inner ``suites`` map keyed by suite filename.
    """
    baseline_path = Path(path)
    if not baseline_path.exists():
        raise EvalSuiteError(f"baseline file not found: {baseline_path}")
    try:
        payload = json.loads(baseline_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise EvalSuiteError(f"baseline file {baseline_path} is not valid JSON: {exc.msg}") from exc
    suites = payload.get("suites")
    if not isinstance(suites, dict):
        raise EvalSuiteError(f"baseline file {baseline_path} is missing the 'suites' object")
    return {str(name): {str(k): float(v) for k, v in metrics.items()} for name, metrics in suites.items()}


def baseline_thresholds_for(
    baseline_metrics: dict[str, float],
    *,
    floor_delta: float = BASELINE_FLOOR_DELTA,
    case_thresholds: EvalThresholds = DEFAULT_THRESHOLDS,
) -> EvalThresholds:
    """Derive suite-level thresholds = max(baseline - floor_delta, case_threshold).

    Returns ``EvalThresholds`` with each metric clamped to [0.0, 1.0].
    """
    return EvalThresholds(
        min_precision_at_k=_baseline_threshold(
            baseline_metrics.get("precision_at_k"), floor_delta, case_thresholds.min_precision_at_k
        ),
        min_recall_at_k=_baseline_threshold(
            baseline_metrics.get("recall_at_k"), floor_delta, case_thresholds.min_recall_at_k
        ),
        min_mrr=_baseline_threshold(
            baseline_metrics.get("mrr"), floor_delta, case_thresholds.min_mrr
        ),
        min_hit_at_k=_baseline_threshold(
            baseline_metrics.get("hit_at_k"), floor_delta, case_thresholds.min_hit_at_k
        ),
    )


def _baseline_threshold(baseline: float | None, floor_delta: float, case_threshold: float | None) -> float | None:
    if baseline is None:
        return case_threshold
    derived = max(0.0, min(1.0, float(baseline) - float(floor_delta)))
    if case_threshold is None:
        return derived
    return max(derived, float(case_threshold))
