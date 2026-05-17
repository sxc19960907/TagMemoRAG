"""Evaluate wave_phase1 flag combinations for readiness.

Runs siliconflow CI under 5 configs:
- baseline: all 3 flags off (matches current default)
- only-resonance: cross_domain_resonance_enabled=true
- only-residuals: intrinsic_residuals_enabled=true
- only-geodesic: geodesic_rerank_enabled=true
- all-on: all 3 flags on

For each config, runs 4 strict siliconflow eval suites (coffee /
mixed_language / product_manuals / tag_rerank_edge — the four that
pass strict gating after Phase A/B). Captures the suite-level metrics
(precision_at_k / recall_at_k / mrr / hit_at_k) and prints a delta
table (config vs baseline) plus a per-flag D3 readiness judgment
(flip_on / keep_off).

Notes:
- Stress-test suites (cross_kb_negatives / fault_codes / model_numbers
  / tag_cooccurrence) are excluded — they're informational only.
- Uses build_eval_baseline._with_retry + _smoke_check_siliconflow for
  resilience.
- Each config runs the suites in a fresh tempdir KB build (siliconflow
  embedder calls Qwen-VL).
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
SCRIPTS_ROOT = REPO_ROOT / "scripts"
for p in (str(SRC_ROOT), str(SCRIPTS_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import build_eval_baseline as bel  # noqa: E402

from tagmemorag.config import Settings, StorageConfig  # noqa: E402
from tagmemorag.eval.dataset import EvalThresholds  # noqa: E402
from tagmemorag.eval.runner import run_eval  # noqa: E402

# 4 strict siliconflow suites (after Phase A/B classification).
STRICT_SUITES = [
    "coffee.jsonl",
    "mixed_language.jsonl",
    "product_manuals.jsonl",
    "tag_rerank_edge.jsonl",
]
SUITE_DIR = REPO_ROOT / "tests" / "fixtures" / "eval"
DEFAULT_DOCS_DIR = REPO_ROOT / "tests" / "fixtures" / "product_manuals"
SUITE_DOCS_OVERRIDES = {
    "coffee.jsonl": REPO_ROOT / "tests" / "fixtures",
}

CONFIG_NAMES = [
    "baseline",
    "only-resonance",
    "only-residuals",
    "only-geodesic",
    "all-on",
]


@dataclass
class FlagSet:
    resonance: bool = False
    residuals: bool = False
    geodesic: bool = False


def _flags_for(config_name: str) -> FlagSet:
    return {
        "baseline": FlagSet(),
        "only-resonance": FlagSet(resonance=True),
        "only-residuals": FlagSet(residuals=True),
        "only-geodesic": FlagSet(geodesic=True),
        "all-on": FlagSet(resonance=True, residuals=True, geodesic=True),
    }[config_name]


def _build_config(tmp_root: Path, flags: FlagSet) -> Settings:
    cfg = bel._build_config(bel.EMBEDDER_SILICONFLOW, spike_enabled=True)
    cfg.storage = StorageConfig(data_dir=str(tmp_root / "data"), schema_version=cfg.storage.schema_version)
    # Apply phase flags
    cfg.wave_phase1.cross_domain_resonance_enabled = flags.resonance
    cfg.wave_phase1.intrinsic_residuals_enabled = flags.residuals
    cfg.wave_phase1.geodesic_rerank_enabled = flags.geodesic
    return cfg


def _run_suite(cfg: Settings, suite_path: Path, suite_data_dir: Path) -> dict[str, float]:
    docs = SUITE_DOCS_OVERRIDES.get(suite_path.name, DEFAULT_DOCS_DIR)
    suite_cfg = cfg.model_copy(deep=True)
    suite_cfg.storage = StorageConfig(data_dir=str(suite_data_dir), schema_version=cfg.storage.schema_version)

    def _do() -> Any:
        return run_eval(
            cfg=suite_cfg,
            suite_path=suite_path,
            docs_path=docs,
            eval_data_dir=str(suite_data_dir),
            thresholds=EvalThresholds(),
        )
    report = bel._with_retry(_do)
    return {k: round(float(v), 6) for k, v in report.summary.metrics.to_dict().items()}


def _judge_flag(flag_name: str, deltas: dict[str, dict[str, float]]) -> tuple[str, str]:
    """D3 judgment: flip_on if ≥2 metrics improved by ≥+0.03 in ≥2 suites
    AND no metric regressed by >0.05 in any strict suite. Else keep_off.
    """
    improvements = 0
    suites_with_improvement: set[str] = set()
    metrics_with_improvement: set[str] = set()
    regression_blocker = ""
    for suite, metric_deltas in deltas.items():
        for metric, d in metric_deltas.items():
            if d <= -0.05:
                regression_blocker = f"{suite}.{metric} regressed by {d:.4f}"
            if d >= 0.03:
                improvements += 1
                suites_with_improvement.add(suite)
                metrics_with_improvement.add(metric)

    if regression_blocker:
        return "keep_off", f"regression blocker: {regression_blocker}"
    if len(metrics_with_improvement) >= 2 and len(suites_with_improvement) >= 2:
        return (
            "flip_on",
            f"{improvements} metric improvements across {len(metrics_with_improvement)} metrics "
            f"and {len(suites_with_improvement)} suites",
        )
    return (
        "keep_off",
        f"insufficient improvement ({len(metrics_with_improvement)} metrics, "
        f"{len(suites_with_improvement)} suites)",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional output file to also tee the report to (for archival).",
    )
    parser.add_argument(
        "--configs",
        default=",".join(CONFIG_NAMES),
        help=f"Comma-separated config names to run. Default: all 5 ({CONFIG_NAMES}).",
    )
    args = parser.parse_args(argv)

    configs_to_run = [c.strip() for c in args.configs.split(",") if c.strip()]
    for c in configs_to_run:
        if c not in CONFIG_NAMES:
            print(f"unknown config: {c}", file=sys.stderr)
            return 2

    suites = [SUITE_DIR / s for s in STRICT_SUITES]

    # Smoke once
    bel._smoke_check_siliconflow(_build_config(Path("/tmp"), FlagSet()))

    # Run all configs
    results: dict[str, dict[str, dict[str, float]]] = {}
    for config_name in configs_to_run:
        flags = _flags_for(config_name)
        print(f"\n=== Running config: {config_name} (resonance={flags.resonance} "
              f"residuals={flags.residuals} geodesic={flags.geodesic}) ===", file=sys.stderr)
        with tempfile.TemporaryDirectory(prefix=f"readiness-{config_name}-") as tmp:
            tmp_root = Path(tmp)
            cfg = _build_config(tmp_root, flags)
            config_results: dict[str, dict[str, float]] = {}
            for suite in suites:
                suite_data_dir = tmp_root / suite.stem
                metrics = _run_suite(cfg, suite, suite_data_dir)
                shutil.rmtree(suite_data_dir, ignore_errors=True)
                config_results[suite.name] = metrics
                print(
                    f"  {suite.name}: " + " ".join(f"{k}={v:.4f}" for k, v in metrics.items()),
                    file=sys.stderr,
                )
            results[config_name] = config_results

    # Format report
    lines: list[str] = []
    lines.append("=== Wave Readiness Flags — Strict Siliconflow Suite Eval ===")
    lines.append(f"4 strict suites: {', '.join(STRICT_SUITES)}")
    lines.append(f"4 metrics: precision_at_k / recall_at_k / mrr / hit_at_k")
    lines.append(f"5 configs: {CONFIG_NAMES}")
    lines.append("")

    # Absolute table
    lines.append("--- Absolute metrics ---")
    header = f"{'config':<20}" + "".join(f"{s[:18]:>20}" for s in STRICT_SUITES)
    lines.append(header)
    for cn in configs_to_run:
        row = f"{cn:<20}"
        for s in STRICT_SUITES:
            m = results[cn].get(s, {})
            cell = "/".join(f"{m.get(k, 0):.2f}" for k in ("precision_at_k", "recall_at_k", "mrr", "hit_at_k"))
            row += f"{cell:>20}"
        lines.append(row)
    lines.append("(cells: precision/recall/mrr/hit)")
    lines.append("")

    # Delta table vs baseline
    if "baseline" in results:
        baseline = results["baseline"]
        for cn in configs_to_run:
            if cn == "baseline":
                continue
            lines.append(f"--- Delta: {cn} - baseline ---")
            lines.append(f"{'suite':<28}{'precision':>12}{'recall':>12}{'mrr':>12}{'hit':>12}")
            for s in STRICT_SUITES:
                bm = baseline.get(s, {})
                cm = results[cn].get(s, {})
                cells = []
                for m in ("precision_at_k", "recall_at_k", "mrr", "hit_at_k"):
                    d = float(cm.get(m, 0)) - float(bm.get(m, 0))
                    sign = "+" if d >= 0 else ""
                    cells.append(f"{sign}{d:>11.4f}")
                lines.append(f"{s:<28}{cells[0]:>12}{cells[1]:>12}{cells[2]:>12}{cells[3]:>12}")
            lines.append("")

        # D3 per-flag judgments (only when each "only-X" config exists)
        lines.append("--- Per-flag readiness judgment (D3 rule: flip_on if ≥2 metric/≥2 suite ≥+0.03 AND no metric regressed > 0.05) ---")
        for flag_name, config_name in [
            ("cross_domain_resonance_enabled", "only-resonance"),
            ("intrinsic_residuals_enabled", "only-residuals"),
            ("geodesic_rerank_enabled", "only-geodesic"),
        ]:
            if config_name not in results:
                lines.append(f"  {flag_name}: skipped (config '{config_name}' not run)")
                continue
            deltas = {}
            for s in STRICT_SUITES:
                bm = baseline.get(s, {})
                cm = results[config_name].get(s, {})
                deltas[s] = {
                    m: round(float(cm.get(m, 0)) - float(bm.get(m, 0)), 6)
                    for m in ("precision_at_k", "recall_at_k", "mrr", "hit_at_k")
                }
            verdict, reason = _judge_flag(flag_name, deltas)
            lines.append(f"  {flag_name}: {verdict.upper()} — {reason}")
        lines.append("")

    report = "\n".join(lines)
    print(report)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report + "\n", encoding="utf-8")
        print(f"\n[written] {args.output}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
