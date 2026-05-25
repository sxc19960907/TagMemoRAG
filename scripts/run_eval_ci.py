"""CI entry point: run every eval suite under tests/fixtures/eval/ with the
selected embedder and the baseline-derived suite thresholds. Exit non-zero
if any suite fails. Used by .github/workflows/quality.yml.

Default --embedder=hashing (offline, fast, used as the always-on PR gate).
Use --embedder=siliconflow with --baseline=tests/fixtures/eval/baselines/siliconflow.json
for readiness / pre-release validation against the production embedder.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SUITE_DIR = REPO_ROOT / "tests" / "fixtures" / "eval"
BASELINE_PATH = SUITE_DIR / "baselines" / "hashing.json"
DEFAULT_DOCS_DIR = REPO_ROOT / "tests" / "fixtures" / "product_manuals"
DEFAULT_EXCLUDED_SUITES = {"general_web.jsonl", "mixed_knowledge.jsonl", "realmanuals.jsonl"}

EMBEDDER_HASHING = "hashing"
EMBEDDER_SILICONFLOW = "siliconflow"
SUPPORTED_EMBEDDERS = (EMBEDDER_HASHING, EMBEDDER_SILICONFLOW)

SUITE_DOCS_OVERRIDES = {
    "coffee.jsonl": REPO_ROOT / "tests" / "fixtures",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=BASELINE_PATH)
    parser.add_argument("--suite-dir", type=Path, default=SUITE_DIR)
    parser.add_argument(
        "--embedder",
        choices=SUPPORTED_EMBEDDERS,
        default=EMBEDDER_HASHING,
        help="Embedder to use for the CI run; must match the baseline JSON's embedder field.",
    )
    parser.add_argument(
        "--no-default-thresholds",
        action="store_true",
        default=True,
        help="Skip the project-wide DEFAULT_THRESHOLDS floor (recall/mrr/hit ≥ 0.8) and "
        "rely solely on baseline-derived thresholds (default ON since "
        "eval-fixture-rewrite Phase A widened the answer sets beyond what "
        "64-dim hashing recall fully covers).",
    )
    parser.add_argument(
        "--with-default-thresholds",
        dest="no_default_thresholds",
        action="store_false",
        help="Enforce the project-wide DEFAULT_THRESHOLDS floor (recall/mrr/hit ≥ 0.8). "
        "Use this only when the entire fixture suite has been re-authored to satisfy "
        "the floor under the chosen embedder.",
    )
    parser.add_argument(
        "--informational-suites",
        default="",
        help="Comma-separated suite filenames whose failures don't gate CI. Used for "
        "stress-test suites (e.g. cross_kb_negatives) where fail is a known production "
        "embedder limitation, not a regression. Empty = none informational.",
    )
    parser.add_argument(
        "--geodesic",
        action="store_true",
        help="Run with Phase 4 geodesic_rerank_enabled=true (informational; "
        "does NOT change the baseline gate — recall delta is recorded for ops review).",
    )
    args = parser.parse_args(argv)

    if not args.baseline.exists():
        print(f"baseline missing: {args.baseline}", file=sys.stderr)
        print(
            "regenerate with: uv run python scripts/build_eval_baseline.py "
            f"--embedder {args.embedder} --output {args.baseline}",
            file=sys.stderr,
        )
        return 1

    baseline_payload = _load_baseline(args.baseline)
    suites = _iter_gated_suites(args.suite_dir, baseline_payload=baseline_payload)
    if not suites:
        print(f"no suites under {args.suite_dir}", file=sys.stderr)
        return 1

    informational = {
        s.strip() for s in args.informational_suites.split(",") if s.strip()
    }

    failed: list[str] = []
    informational_failed: list[str] = []
    with tempfile.TemporaryDirectory(prefix="ci-eval-") as tmp:
        tmp_root = Path(tmp)
        config_path = tmp_root / f"ci-{args.embedder}.yaml"
        config_path.write_text(
            _config_yaml(tmp_root / "data", embedder=args.embedder, geodesic=args.geodesic),
            encoding="utf-8",
        )
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
            if args.no_default_thresholds:
                cmd.extend([
                    "--min-recall-at-k", "0.0",
                    "--min-mrr", "0.0",
                    "--min-hit-at-k", "0.0",
                ])
            result = subprocess.run(cmd, text=True, capture_output=True)
            tail = (result.stdout or "").strip().splitlines()[-1:] or [""]
            tag = " [informational]" if suite.name in informational else ""
            print(f"[{suite.name}]{tag} {tail[0]}")
            if result.returncode != 0:
                if suite.name in informational:
                    informational_failed.append(suite.name)
                else:
                    failed.append(suite.name)
                if result.stderr:
                    print(result.stderr, file=sys.stderr)
            shutil.rmtree(data_dir, ignore_errors=True)

    if informational_failed:
        print(
            f"\n[informational] {len(informational_failed)} stress-test suite(s) failed (not gating CI): "
            f"{informational_failed}",
            file=sys.stderr,
        )

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


def _config_yaml(data_dir: Path, *, embedder: str = EMBEDDER_HASHING, geodesic: bool = False) -> str:
    """Generate the YAML config consumed by `tagmemorag eval run`.

    Hashing path is byte-equivalent to the previous `_hashing_config_yaml`
    output (master baseline invariance). Siliconflow path requires
    SILICONFLOW_API_KEY in the env; the YAML references it by name, never
    inlines the secret.
    """
    if embedder == EMBEDDER_HASHING:
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
    elif embedder == EMBEDDER_SILICONFLOW:
        base = (
            "model:\n"
            "  provider: http\n"
            "  name: Qwen/Qwen3-Embedding-8B\n"
            "  dim: 4096\n"
            "  base_url: https://api.siliconflow.cn/v1\n"
            "  api_key_env: SILICONFLOW_API_KEY\n"
            "  normalize: true\n"
            "storage:\n"
            f"  data_dir: {data_dir}\n"
            "wave_phase1:\n"
            "  spike_enabled: true\n"
        )
    else:
        raise ValueError(f"unsupported embedder: {embedder}")

    if geodesic:
        base += (
            "  geodesic_rerank_enabled: true\n"
            "  geodesic_alpha: 0.3\n"
            "  geodesic_min_geo_samples: 2\n"
            "  geodesic_oversample_factor: 2.0\n"
        )
    return base


def _load_baseline(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"baseline is not valid JSON: {path}: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"baseline root must be a JSON object: {path}")
    return data


def _iter_gated_suites(suite_dir: Path, *, baseline_payload: dict | None = None) -> list[Path]:
    """Return suites covered by the baseline gate.

    `realmanuals.jsonl` is an informational production-PDF diagnostic fixture
    evaluated by `scripts/diag_realmanuals_eval.py`. `general_web.jsonl` and
    `mixed_knowledge.jsonl` depend on a reproducible but network-seeded `.tmp`
    corpus from `scripts/seed_general_web_eval.sh`, so they are run as explicit
    benchmarks, not by the strict fixture-only hashing baseline CI.

    New eval suites must be added to the baseline before they enter this strict
    PR gate. Suites with their own baseline format, such as agentic loop
    diagnostics, can live under the same fixture directory without blocking this
    baseline-derived gate.
    """
    baseline_suites = None
    if baseline_payload is not None:
        raw_suites = baseline_payload.get("suites")
        if not isinstance(raw_suites, dict):
            raise SystemExit("baseline must contain a 'suites' object")
        baseline_suites = set(raw_suites)
    return sorted(
        p
        for p in suite_dir.iterdir()
        if p.is_file()
        and p.suffix == ".jsonl"
        and p.name not in DEFAULT_EXCLUDED_SUITES
        and (baseline_suites is None or p.name in baseline_suites)
    )


if __name__ == "__main__":
    raise SystemExit(main())
