from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from ..config import load_config
from .filters import parse_filter_args
from .generation import ReplayGenerationError, load_generation_state, resolve_generation_selector
from .loader import ReplayLoadError, ReplayPlanLoader
from .metrics import compute_deltas, compute_run_metrics, summarize_rerank
from .models import ReplayReport
from .report import render_markdown
from .runner import replay_plans


DEFAULT_METRICS = (
    "any_hit_rate",
    "evidence_overlap_at_k",
    "top1_stability",
    "latency_ms_p50",
    "latency_ms_p95",
)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "replay":
        return _cmd_replay(args)
    parser.print_help()
    return 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="trellis-rag-eval")
    sub = parser.add_subparsers(dest="command")
    replay = sub.add_parser("replay", help="Replay persisted QueryPlans against a generation")
    replay.add_argument("--kb", required=True, help="KB name")
    replay.add_argument("--generation", required=True, help="target generation: active, shadow, gN, or N")
    replay.add_argument("--baseline", default=None, help="optional baseline generation")
    replay.add_argument("--config", default="config.yaml", help="config path")
    replay.add_argument("--filter", action="append", default=[], help="filter key=value; may repeat")
    replay.add_argument("--metrics", default=",".join(DEFAULT_METRICS), help="comma-separated metric names")
    replay.add_argument("--limit", type=int, default=None, help="maximum replayable plans after filters")
    replay.add_argument("--force-mode", choices=["classic", "agentic"], default=None)
    replay.add_argument("--output-format", choices=["json", "markdown"], default="json")
    return parser


def _cmd_replay(args) -> int:
    try:
        report = _run_replay(args)
    except (ReplayLoadError, ReplayGenerationError, ValueError) as exc:
        return _print_error(str(exc), args.output_format)
    if args.output_format == "markdown":
        sys.stdout.write(render_markdown(report))
    else:
        sys.stdout.write(json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return 3 if report.regression_detected else 0


def _run_replay(args) -> ReplayReport:
    settings = load_config(args.config)
    filters = parse_filter_args(args.filter)
    metrics_requested = _parse_metrics(args.metrics)
    loader = ReplayPlanLoader(args.kb, settings)
    plans, skipped = loader.load(filters=filters, limit=args.limit)
    target_generation = resolve_generation_selector(args.kb, settings, args.generation)
    target_state = load_generation_state(args.kb, settings, target_generation)
    target_cases = replay_plans(
        plans=plans,
        state=target_state,
        settings=settings,
        generation=target_generation,
    )
    plans_by_id = {plan.plan_id: plan for plan in plans}
    target_metrics = compute_run_metrics(target_cases, plans_by_id=plans_by_id)
    target = {
        "generation": target_generation,
        "metrics": _filter_metrics(target_metrics.to_dict(), metrics_requested),
        "cases": [case.to_dict() for case in target_cases],
    }
    baseline = None
    deltas: dict[str, float] = {}
    regression_detected = False
    if args.baseline:
        baseline_generation = resolve_generation_selector(args.kb, settings, args.baseline)
        baseline_state = load_generation_state(args.kb, settings, baseline_generation)
        baseline_cases = replay_plans(
            plans=plans,
            state=baseline_state,
            settings=settings,
            generation=baseline_generation,
        )
        baseline_by_id = {case.plan_id: case for case in baseline_cases}
        baseline_metrics = compute_run_metrics(baseline_cases, plans_by_id=plans_by_id)
        target_metrics_for_delta = compute_run_metrics(
            target_cases,
            plans_by_id=plans_by_id,
            baseline_by_id=baseline_by_id,
        )
        target["metrics"] = _filter_metrics(target_metrics_for_delta.to_dict(), metrics_requested)
        baseline = {
            "generation": baseline_generation,
            "metrics": _filter_metrics(baseline_metrics.to_dict(), metrics_requested),
            "cases": [case.to_dict() for case in baseline_cases],
        }
        deltas = {
            key: value
            for key, value in compute_deltas(target_metrics_for_delta, baseline_metrics).items()
            if key.removesuffix("_delta") in metrics_requested or key == "queries_replayed_delta"
        }
        regression_detected = bool(deltas.get("any_hit_rate_delta", 0.0) < 0.0)

    row_counts = {
        "loaded": len(plans) + len(skipped),
        "selected": len(plans),
        "skipped": len(skipped),
        "replayed": sum(1 for case in target_cases if case.query_replayed),
    }
    return ReplayReport(
        kb=args.kb,
        filters=filters.to_dict(),
        metrics_requested=tuple(metrics_requested),
        row_counts=row_counts,
        target=target,
        baseline=baseline,
        deltas=deltas,
        rerank_summary=summarize_rerank(plans),
        skipped_rows=tuple(skipped),
        regression_detected=regression_detected,
        forced_mode=args.force_mode,
    )


def _parse_metrics(raw: str) -> tuple[str, ...]:
    metrics = tuple(item.strip() for item in str(raw or "").split(",") if item.strip())
    return metrics or DEFAULT_METRICS


def _filter_metrics(metrics: dict[str, Any], requested: tuple[str, ...]) -> dict[str, Any]:
    always = {"queries_replayed"}
    allowed = set(requested) | always
    return {key: value for key, value in metrics.items() if key in allowed}


def _print_error(message: str, output_format: str) -> int:
    if output_format == "markdown":
        sys.stdout.write(f"# Replay Error\n\n- error: {message}\n")
    else:
        sys.stdout.write(json.dumps({"error": message}, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
