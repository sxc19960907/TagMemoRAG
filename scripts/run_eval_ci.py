"""CI entry point: run every eval suite under tests/fixtures/eval/ with hashing
embedder and the baseline-derived suite thresholds. Exit non-zero if any suite
fails. Used by .github/workflows/quality.yml.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SUITE_DIR = REPO_ROOT / "tests" / "fixtures" / "eval"
BASELINE_PATH = SUITE_DIR / "baselines" / "hashing.json"
DEFAULT_DOCS_DIR = REPO_ROOT / "tests" / "fixtures" / "product_manuals"

SUITE_DOCS_OVERRIDES = {
    "coffee.jsonl": REPO_ROOT / "tests" / "fixtures",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=BASELINE_PATH)
    parser.add_argument("--suite-dir", type=Path, default=SUITE_DIR)
    parser.add_argument(
        "--geodesic",
        action="store_true",
        help="Run with Phase 4 geodesic_rerank_enabled=true (informational; "
        "does NOT change the baseline gate — recall delta is recorded for ops review).",
    )
    args = parser.parse_args(argv)

    if not args.baseline.exists():
        print(f"baseline missing: {args.baseline}", file=sys.stderr)
        print("regenerate with: uv run python scripts/build_eval_baseline.py --embedder hashing --output " f"{args.baseline}", file=sys.stderr)
        return 1

    suites = sorted(p for p in args.suite_dir.iterdir() if p.is_file() and p.suffix == ".jsonl")
    if not suites:
        print(f"no suites under {args.suite_dir}", file=sys.stderr)
        return 1

    failed: list[str] = []
    with tempfile.TemporaryDirectory(prefix="ci-eval-") as tmp:
        tmp_root = Path(tmp)
        config_path = tmp_root / "ci-hashing.yaml"
        config_path.write_text(_hashing_config_yaml(tmp_root / "data", geodesic=args.geodesic), encoding="utf-8")
        for suite in suites:
            data_dir = tmp_root / suite.stem
            docs_for_suite = SUITE_DOCS_OVERRIDES.get(suite.name, DEFAULT_DOCS_DIR)
            cmd = [
                sys.executable,
                "-m",
                "tagmemorag",
                "eval",
                "run",
                "--suite",
                str(suite),
                "--docs",
                str(docs_for_suite),
                "--config",
                str(config_path),
                "--baseline",
                str(args.baseline),
                "--eval-data-dir",
                str(data_dir),
            ]
            result = subprocess.run(cmd, text=True, capture_output=True)
            tail = (result.stdout or "").strip().splitlines()[-1:] or [""]
            print(f"[{suite.name}] {tail[0]}")
            if result.returncode != 0:
                failed.append(suite.name)
                if result.stderr:
                    print(result.stderr, file=sys.stderr)
            shutil.rmtree(data_dir, ignore_errors=True)

    if failed:
        if args.geodesic:
            # Phase 4 D6: enabled-on column is informational only — record the
            # delta but never block CI on it. Recovery is the responsibility
            # of the readiness task, not the algorithm-introduction task.
            print(
                f"\n[geodesic enabled-on] {len(failed)} suite(s) below baseline: {failed}",
                file=sys.stderr,
            )
            print(
                "[geodesic enabled-on] not gating CI (Phase 4 default-off + informational policy)",
                file=sys.stderr,
            )
            return 0
        print(f"\nFAILED suites: {failed}", file=sys.stderr)
        return 1
    print(f"\nAll {len(suites)} eval suites passed (baseline = {args.baseline.name})")
    return 0


def _hashing_config_yaml(data_dir: Path, *, geodesic: bool = False) -> str:
    base = (
        "model:\n"
        "  provider: hashing\n"
        "  dim: 64\n"
        "  batch_size: 16\n"
        "storage:\n"
        f"  data_dir: {data_dir}\n"
        "wave_phase1:\n"
        "  spike_enabled: true\n"
    )
    if geodesic:
        base += (
            "  geodesic_rerank_enabled: true\n"
            "  geodesic_alpha: 0.3\n"
            "  geodesic_min_geo_samples: 2\n"
            "  geodesic_oversample_factor: 2.0\n"
        )
    return base


if __name__ == "__main__":
    raise SystemExit(main())
