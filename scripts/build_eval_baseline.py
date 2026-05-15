"""Generate or refresh `tests/fixtures/eval/baselines/<embedder>.json`.

The script runs every jsonl suite under `tests/fixtures/eval/` (excluding the
baselines/ subdirectory) through the eval runner, captures the suite-level
aggregate metrics, and writes a deterministic JSON snapshot used by the
quality CI to derive `baseline - 0.02` thresholds.

Usage:
    uv run python scripts/build_eval_baseline.py \\
        --embedder hashing \\
        --output tests/fixtures/eval/baselines/hashing.json

For SiliconFlow runs, set SILICONFLOW_API_KEY first; the script will pick up
the project's default model config.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
SUITE_DIR = REPO_ROOT / "tests" / "fixtures" / "eval"
DEFAULT_DOCS_DIR = REPO_ROOT / "tests" / "fixtures" / "product_manuals"

# Per-suite docs override. Falls back to DEFAULT_DOCS_DIR.
SUITE_DOCS_OVERRIDES = {
    "coffee.jsonl": REPO_ROOT / "tests" / "fixtures",
}

sys.path.insert(0, str(REPO_ROOT / "src"))

from tagmemorag.config import Settings, StorageConfig  # noqa: E402
from tagmemorag.eval.dataset import EvalThresholds  # noqa: E402
from tagmemorag.eval.runner import run_eval  # noqa: E402

EMBEDDER_HASHING = "hashing"
EMBEDDER_SILICONFLOW = "siliconflow"
SUPPORTED_EMBEDDERS = (EMBEDDER_HASHING, EMBEDDER_SILICONFLOW)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--embedder", choices=SUPPORTED_EMBEDDERS, required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--docs", type=Path, default=DEFAULT_DOCS_DIR)
    parser.add_argument("--suite-dir", type=Path, default=SUITE_DIR)
    spike_group = parser.add_mutually_exclusive_group()
    spike_group.add_argument(
        "--spike-on",
        dest="spike",
        action="store_true",
        help="Enable wave_phase1.spike_enabled when capturing the baseline (default).",
    )
    spike_group.add_argument(
        "--spike-off",
        dest="spike",
        action="store_false",
        help="Disable wave_phase1.spike_enabled when capturing the baseline.",
    )
    parser.set_defaults(spike=True)
    args = parser.parse_args(argv)

    cfg = _build_config(args.embedder, spike_enabled=args.spike)
    suites = sorted(_iter_suites(args.suite_dir))
    if not suites:
        print(f"no suites found under {args.suite_dir}", file=sys.stderr)
        return 1

    suite_metrics: dict[str, dict[str, float]] = {}
    with tempfile.TemporaryDirectory(prefix="eval-baseline-") as tmp:
        tmp_root = Path(tmp)
        for suite_path in suites:
            suite_data_dir = tmp_root / suite_path.stem
            suite_cfg = _clone_with_data_dir(cfg, suite_data_dir)
            docs_for_suite = SUITE_DOCS_OVERRIDES.get(suite_path.name, args.docs)
            report = run_eval(
                cfg=suite_cfg,
                suite_path=suite_path,
                docs_path=docs_for_suite,
                eval_data_dir=str(suite_data_dir),
                thresholds=EvalThresholds(),
            )
            suite_metrics[suite_path.name] = _round_metrics(report.summary.metrics.to_dict())
            shutil.rmtree(suite_data_dir, ignore_errors=True)

    payload = {
        "embedder": args.embedder,
        "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "config_hash": _config_hash(args.embedder, cfg, suites),
        "thresholds_applied": {"floor_delta": 0.02},
        "suites": dict(sorted(suite_metrics.items())),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {args.output} with {len(suite_metrics)} suite(s)")
    return 0


def _build_config(embedder: str, *, spike_enabled: bool = True) -> Settings:
    if embedder == EMBEDDER_HASHING:
        return Settings(
            model={"provider": "hashing", "dim": 64, "batch_size": 16},
            wave_phase1={"spike_enabled": spike_enabled},
        )
    if embedder == EMBEDDER_SILICONFLOW:
        if not os.environ.get("SILICONFLOW_API_KEY"):
            raise SystemExit("SILICONFLOW_API_KEY is required for the siliconflow baseline")
        return Settings(
            model={
                "provider": "http",
                "name": "BAAI/bge-small-zh-v1.5",
                "dim": 384,
                "base_url": "https://api.siliconflow.cn/v1",
                "api_key_env": "SILICONFLOW_API_KEY",
                "normalize": True,
            },
            wave_phase1={"spike_enabled": spike_enabled},
        )
    raise ValueError(f"unsupported embedder: {embedder}")


def _clone_with_data_dir(cfg: Settings, data_dir: Path) -> Settings:
    cloned = cfg.model_copy(deep=True)
    cloned.storage = StorageConfig(data_dir=str(data_dir), schema_version=cfg.storage.schema_version)
    return cloned


def _iter_suites(suite_dir: Path) -> Iterable[Path]:
    for path in suite_dir.iterdir():
        if path.is_file() and path.suffix == ".jsonl":
            yield path


def _round_metrics(metrics: dict[str, float]) -> dict[str, float]:
    return {key: round(float(value), 6) for key, value in metrics.items()}


def _config_hash(embedder: str, cfg: Settings, suites: list[Path]) -> str:
    h = hashlib.sha256()
    h.update(f"embedder={embedder}\n".encode())
    h.update(f"model_dim={cfg.model.dim}\n".encode())
    h.update(f"model_provider={cfg.model.provider}\n".encode())
    h.update(f"parser_max={cfg.parser.max_chars}\n".encode())
    h.update(f"parser_min={cfg.parser.min_chars}\n".encode())
    h.update(f"search_top_k={cfg.search.top_k}\n".encode())
    h.update(f"search_steps={cfg.search.steps}\n".encode())
    h.update(f"search_decay={cfg.search.decay}\n".encode())
    h.update(f"search_aggregate={cfg.search.aggregate}\n".encode())
    h.update(f"tag_boost={cfg.search.tag_boost}\n".encode())
    h.update(f"metadata_field_boost={cfg.search.metadata_field_boost}\n".encode())
    h.update(f"lexical_enabled={cfg.search.lexical_enabled}\n".encode())
    h.update(f"spike_enabled={cfg.wave_phase1.spike_enabled}\n".encode())
    for suite_path in suites:
        digest = hashlib.sha256(suite_path.read_bytes()).hexdigest()
        h.update(f"{suite_path.name}={digest}\n".encode())
    return f"sha256:{h.hexdigest()}"


if __name__ == "__main__":
    raise SystemExit(main())
