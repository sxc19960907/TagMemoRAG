"""Diagnose real PDF manual retrieval quality across wave configurations.

This script is intentionally *not* a strict `eval run` wrapper because
`tests/fixtures/eval/realmanuals.jsonl` currently keeps placeholder ground
truth. Instead, it measures the production-PDF failure mode captured by the
Step B report: whether top-K results route to the query's intended product
category.

Usage:
  python scripts/diag_realmanuals_eval.py \
      --config .trellis/tasks/archive/2026-05/05-17-pdf-manual-real-eval/research/realmanuals.yaml \
      --reuse-built-kb \
      --output .trellis/tasks/archive/2026-05/05-17-pdf-manual-real-eval/research/realmanuals-diag.txt
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
SCRIPTS_ROOT = REPO_ROOT / "scripts"
for p in (str(SRC_ROOT), str(SCRIPTS_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import build_eval_baseline as bel  # noqa: E402

from tagmemorag.config import Settings, StorageConfig, load_config  # noqa: E402
from tagmemorag.embedder import create_embedder  # noqa: E402
from tagmemorag.errors import ServiceError  # noqa: E402
from tagmemorag.eval.dataset import EvalCase, load_eval_suite  # noqa: E402
from tagmemorag.search_runtime import execute_search  # noqa: E402
from tagmemorag.state import build_kb, load_kb, save_kb  # noqa: E402
from tagmemorag.types import GraphState, Result  # noqa: E402

DEFAULT_CONFIG = (
    REPO_ROOT
    / ".trellis"
    / "tasks"
    / "archive"
    / "2026-05"
    / "05-17-pdf-manual-real-eval"
    / "research"
    / "realmanuals.yaml"
)
DEFAULT_SUITE = REPO_ROOT / "tests" / "fixtures" / "eval" / "realmanuals.jsonl"
DEFAULT_DOCS = REPO_ROOT / "product_manuals"
PRODUCT_TAGS = {"washer", "dryer", "oven", "refrigerator", "dishwasher", "air_conditioner", "coffee"}

CONFIG_NAMES = ("vec-only", "wave-baseline", "wave-residuals", "wave-resonance")
METRICS = ("top1_category_hit", "top3_category_hit", "top5_category_hit", "mean_reciprocal_category_rank")


@dataclass(frozen=True)
class DiagConfig:
    name: str
    spike_enabled: bool
    residuals: bool = False
    resonance: bool = False


@dataclass(frozen=True)
class CaseDiag:
    case_id: str
    query: str
    intended_category: str
    top_categories: tuple[str, ...]
    top_sources: tuple[str, ...]
    reciprocal_rank: float


DIAG_CONFIGS = {
    "vec-only": DiagConfig("vec-only", spike_enabled=False),
    "wave-baseline": DiagConfig("wave-baseline", spike_enabled=True),
    "wave-residuals": DiagConfig("wave-residuals", spike_enabled=True, residuals=True),
    "wave-resonance": DiagConfig("wave-resonance", spike_enabled=True, resonance=True),
}


def _product_tag(case: EvalCase) -> str:
    for tag in case.tags:
        normalized = tag.strip().lower()
        if normalized in PRODUCT_TAGS:
            return normalized
    raise ValueError(f"case {case.id!r} has no product category tag in {case.tags!r}")


def _apply_diag_config(cfg: Settings, diag: DiagConfig) -> Settings:
    out = cfg.model_copy(deep=True)
    out.wave_phase1.spike_enabled = diag.spike_enabled
    out.wave_phase1.intrinsic_residuals_enabled = diag.residuals
    out.wave_phase1.cross_domain_resonance_enabled = diag.resonance
    out.wave_phase1.geodesic_rerank_enabled = False
    return out


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


def _run_case(case: EvalCase, intended_category: str, state: GraphState, cfg: Settings, embedder: Any, top_k: int) -> CaseDiag:
    query_vec = embedder.encode_query(case.query)
    execution = execute_search(
        state=state,
        query_vec=query_vec,
        settings=cfg,
        query_text=case.query,
        top_k=top_k,
        source_k=cfg.search.source_k,
        steps=cfg.search.steps,
        decay=cfg.search.decay,
        amplitude_cutoff=cfg.search.amplitude_cutoff,
        aggregate=cfg.search.aggregate,
        filters=None,
    )
    results = list(execution.results)
    categories = tuple(_category(result) for result in results[:top_k])
    sources = tuple(result.source_file for result in results[:top_k])
    rr = _reciprocal_rank(categories, intended_category)
    return CaseDiag(
        case_id=case.id,
        query=case.query,
        intended_category=intended_category,
        top_categories=categories,
        top_sources=sources,
        reciprocal_rank=rr,
    )


def _category(result: Result) -> str:
    category = str(result.product_category or result.metadata.get("product_category") or "").strip().lower()
    if category:
        return category
    source = result.source_file.replace("\\", "/")
    return source.split("/", 1)[0].lower() if "/" in source else ""


def _reciprocal_rank(categories: Iterable[str], intended_category: str) -> float:
    for idx, category in enumerate(categories, 1):
        if category == intended_category:
            return 1.0 / idx
    return 0.0


def _aggregate(case_diags: list[CaseDiag]) -> dict[str, float]:
    count = len(case_diags)
    if count == 0:
        return {metric: 0.0 for metric in METRICS}
    return {
        "top1_category_hit": sum(1.0 for item in case_diags if _hit_at(item, 1)) / count,
        "top3_category_hit": sum(1.0 for item in case_diags if _hit_at(item, 3)) / count,
        "top5_category_hit": sum(1.0 for item in case_diags if _hit_at(item, 5)) / count,
        "mean_reciprocal_category_rank": sum(item.reciprocal_rank for item in case_diags) / count,
    }


def _hit_at(item: CaseDiag, k: int) -> bool:
    return item.intended_category in item.top_categories[:k]


def _format_report(results: dict[str, list[CaseDiag]], *, meta: dict[str, Any], top_k: int) -> str:
    lines: list[str] = []
    lines.append("=== Real Manuals PDF Routing Diagnostic ===")
    lines.append(f"KB chunk_count: {meta.get('chunk_count', 'unknown')}")
    lines.append(f"KB model: {meta.get('model_name', 'unknown')} ({meta.get('model_dim', 'unknown')} dim)")
    lines.append(f"Top-K: {top_k}")
    lines.append("Metrics: top1_category_hit / top3_category_hit / top5_category_hit / mean_reciprocal_category_rank")
    lines.append("")

    lines.append("--- Absolute metrics ---")
    lines.append(f"{'config':<18}{'top1':>10}{'top3':>10}{'top5':>10}{'mrr_cat':>12}")
    aggregates: dict[str, dict[str, float]] = {}
    for config_name in results:
        metrics = _aggregate(results[config_name])
        aggregates[config_name] = metrics
        lines.append(
            f"{config_name:<18}"
            f"{metrics['top1_category_hit']:>10.3f}"
            f"{metrics['top3_category_hit']:>10.3f}"
            f"{metrics['top5_category_hit']:>10.3f}"
            f"{metrics['mean_reciprocal_category_rank']:>12.3f}"
        )
    lines.append("")

    if "vec-only" in aggregates and "wave-baseline" in aggregates:
        lines.append("--- Delta: wave-baseline - vec-only ---")
        base = aggregates["vec-only"]
        wave = aggregates["wave-baseline"]
        for metric in METRICS:
            delta = wave[metric] - base[metric]
            sign = "+" if delta >= 0 else ""
            lines.append(f"{metric}: {sign}{delta:.3f}")
        lines.append("")

    if "wave-baseline" in aggregates:
        lines.append("--- Flag deltas vs wave-baseline ---")
        baseline = aggregates["wave-baseline"]
        for config_name in ("wave-residuals", "wave-resonance"):
            if config_name not in aggregates:
                continue
            lines.append(config_name)
            for metric in METRICS:
                delta = aggregates[config_name][metric] - baseline[metric]
                sign = "+" if delta >= 0 else ""
                lines.append(f"  {metric}: {sign}{delta:.3f}")
        lines.append("")

    lines.append("--- Case top-1 routing ---")
    header = f"{'case':<30}{'want':<14}" + "".join(f"{name[:15]:>20}" for name in results)
    lines.append(header)
    first_config = next(iter(results.values()), [])
    for idx, item in enumerate(first_config):
        row = f"{item.case_id:<30}{item.intended_category:<14}"
        for config_name in results:
            diag = results[config_name][idx]
            got = diag.top_categories[0] if diag.top_categories else "(none)"
            mark = "ok" if got == diag.intended_category else "miss"
            row += f"{got + '/' + mark:>20}"
        lines.append(row)
    lines.append("")

    lines.append("--- Case detail (wave-baseline) ---")
    for item in results.get("wave-baseline", []):
        top_sources = ", ".join(item.top_sources[:5])
        top_categories = ", ".join(item.top_categories[:5])
        lines.append(f"{item.case_id}: want={item.intended_category} rr={item.reciprocal_rank:.3f}")
        lines.append(f"  categories: {top_categories}")
        lines.append(f"  sources: {top_sources}")
    return "\n".join(lines)


def _build_or_load_state(cfg: Settings, *, docs: Path, kb_name: str, reuse_built_kb: bool, embedder: Any) -> GraphState:
    if reuse_built_kb:
        return load_kb(kb_name, cfg)
    state = bel._with_retry(lambda: build_kb(docs, kb_name, cfg, embedder=embedder))
    save_kb(state, cfg)
    return state


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    parser.add_argument("--docs", type=Path, default=DEFAULT_DOCS)
    parser.add_argument("--kb", default="realmanuals")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--configs", default=",".join(CONFIG_NAMES))
    parser.add_argument("--reuse-built-kb", action="store_true")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)

    config_names = [name.strip() for name in args.configs.split(",") if name.strip()]
    unknown = [name for name in config_names if name not in DIAG_CONFIGS]
    if unknown:
        print(f"unknown config(s): {', '.join(unknown)}", file=sys.stderr)
        return 2
    if args.top_k <= 0:
        print("--top-k must be positive", file=sys.stderr)
        return 2

    cases = load_eval_suite(args.suite)
    intended = {case.id: _product_tag(case) for case in cases}
    base_cfg = load_config(args.config)
    if base_cfg.model.provider == "http":
        bel._smoke_check_siliconflow(base_cfg)

    all_results: dict[str, list[CaseDiag]] = {}
    meta: dict[str, Any] = {}
    temp_dir: tempfile.TemporaryDirectory[str] | None = None
    try:
        if not args.reuse_built_kb:
            temp_dir = tempfile.TemporaryDirectory(prefix="realmanuals-diag-")
            base_cfg = base_cfg.model_copy(deep=True)
            base_cfg.storage = StorageConfig(
                data_dir=str(Path(temp_dir.name) / "data"),
                schema_version=base_cfg.storage.schema_version,
            )

        embedder = _create_embedder_from_config(base_cfg)
        for config_name in config_names:
            diag_cfg = _apply_diag_config(base_cfg, DIAG_CONFIGS[config_name])
            print(f"[diag] running {config_name}", file=sys.stderr)
            try:
                state = _build_or_load_state(
                    diag_cfg,
                    docs=args.docs,
                    kb_name=args.kb,
                    reuse_built_kb=args.reuse_built_kb,
                    embedder=embedder,
                )
            except ServiceError:
                raise
            meta = dict(state.meta or meta)
            config_results = [
                bel._with_retry(lambda case=case: _run_case(case, intended[case.id], state, diag_cfg, embedder, args.top_k))
                for case in cases
            ]
            all_results[config_name] = config_results
            if not args.reuse_built_kb:
                shutil.rmtree(Path(diag_cfg.storage.data_dir) / args.kb, ignore_errors=True)
    finally:
        if temp_dir is not None:
            temp_dir.cleanup()

    report = _format_report(all_results, meta=meta, top_k=args.top_k)
    print(report)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report + "\n", encoding="utf-8")
        print(f"[written] {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
