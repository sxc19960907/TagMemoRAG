"""Generate or refresh `tests/fixtures/eval/baselines/<embedder>.json`.

The script runs every fixture-only jsonl suite under `tests/fixtures/eval/`
through the eval runner, captures the suite-level aggregate metrics, and writes
a deterministic JSON snapshot used by the quality CI to derive
`baseline - 0.02` thresholds.

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
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, TypeVar
from urllib.error import URLError

REPO_ROOT = Path(__file__).resolve().parents[1]
SUITE_DIR = REPO_ROOT / "tests" / "fixtures" / "eval"
DEFAULT_DOCS_DIR = REPO_ROOT / "tests" / "fixtures" / "product_manuals"

# Per-suite docs override. Falls back to DEFAULT_DOCS_DIR.
SUITE_DOCS_OVERRIDES = {
    "coffee.jsonl": REPO_ROOT / "tests" / "fixtures",
}

# Suites that are useful diagnostics but should not participate in fixture-only
# baseline generation.
DEFAULT_EXCLUDED_SUITES = {"general_web.jsonl", "mixed_knowledge.jsonl", "realmanuals.jsonl"}

sys.path.insert(0, str(REPO_ROOT / "src"))

from tagmemorag.config import Settings, StorageConfig  # noqa: E402
from tagmemorag.embedder import HttpEmbedder  # noqa: E402
from tagmemorag.errors import EmbeddingError  # noqa: E402
from tagmemorag.eval.dataset import EvalThresholds  # noqa: E402
from tagmemorag.eval.runner import run_eval  # noqa: E402

EMBEDDER_HASHING = "hashing"
EMBEDDER_SILICONFLOW = "siliconflow"
SUPPORTED_EMBEDDERS = (EMBEDDER_HASHING, EMBEDDER_SILICONFLOW)

# D5: Qwen3-Embedding-8B is the production text-RAG model target. 4096 dim,
# OpenAI-compatible /v1/embeddings endpoint on SiliconFlow.
SILICONFLOW_MODEL_NAME = "Qwen/Qwen3-Embedding-8B"
SILICONFLOW_MODEL_DIM = 4096
SILICONFLOW_BASE_URL = "https://api.siliconflow.cn/v1"
SILICONFLOW_API_KEY_ENV = "SILICONFLOW_API_KEY"

# D3: hard-error HTTP status codes that should not trigger retry.
_NON_RETRIABLE_STATUS_CODES = {400, 401, 403, 404, 422}

T = TypeVar("T")


def _build_config(embedder: str, *, spike_enabled: bool = True) -> Settings:
    if embedder == EMBEDDER_HASHING:
        return Settings(
            model={"provider": "hashing", "dim": 64, "batch_size": 16},
            wave_phase1={"spike_enabled": spike_enabled},
        )
    if embedder == EMBEDDER_SILICONFLOW:
        if not os.environ.get(SILICONFLOW_API_KEY_ENV):
            raise SystemExit(
                f"{SILICONFLOW_API_KEY_ENV} is required for the siliconflow baseline"
            )
        return Settings(
            model={
                "provider": "http",
                "name": SILICONFLOW_MODEL_NAME,
                "dim": SILICONFLOW_MODEL_DIM,
                "base_url": SILICONFLOW_BASE_URL,
                "api_key_env": SILICONFLOW_API_KEY_ENV,
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
        if (
            path.is_file()
            and path.suffix == ".jsonl"
            and path.name not in DEFAULT_EXCLUDED_SUITES
        ):
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


def _is_retriable(exc: BaseException) -> bool:
    """D3: classify whether to retry. Hard errors (auth / config / 4xx) bail
    out immediately; transient errors (5xx / 429 / network / timeout) retry.
    """
    if isinstance(exc, EmbeddingError):
        detail = exc.detail or {}
        status = detail.get("status_code")
        if isinstance(status, int) and status in _NON_RETRIABLE_STATUS_CODES:
            return False
        return True
    if isinstance(exc, (URLError, TimeoutError, OSError)):
        return True
    return False


def _with_retry(
    fn: Callable[[], T],
    *,
    max_attempts: int = 5,
    base_backoff: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
    log: Callable[[str], None] = lambda msg: print(msg, file=sys.stderr),
) -> T:
    """Run `fn` with exponential backoff (1s, 2s, 4s, 8s, 16s) on transient
    errors. Hard errors (401/403/etc.) bail out immediately. After
    `max_attempts` failed retries the last exception is re-raised.
    """
    last_exc: BaseException | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            if not _is_retriable(exc):
                raise
            if attempt >= max_attempts:
                break
            wait = base_backoff * (2 ** (attempt - 1))
            log(f"[retry] attempt {attempt}/{max_attempts} failed ({exc}); sleeping {wait:.1f}s")
            sleep(wait)
    assert last_exc is not None  # for type checker
    raise last_exc


def _smoke_check_siliconflow(cfg: Settings) -> None:
    """D5: single-query smoke before burning quota on a full capture run.

    Fails loud with category-specific stderr hints so the user can fix the
    config / env / network issue before the long capture begins.
    """
    if not os.environ.get(SILICONFLOW_API_KEY_ENV):
        print(
            f"[smoke] {SILICONFLOW_API_KEY_ENV} env var is not set. "
            f"`export {SILICONFLOW_API_KEY_ENV}=...` first.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    embedder = HttpEmbedder(
        cfg.model.name or SILICONFLOW_MODEL_NAME,
        base_url=cfg.model.base_url or SILICONFLOW_BASE_URL,
        api_key_env=cfg.model.api_key_env or SILICONFLOW_API_KEY_ENV,
        timeout_seconds=float(cfg.model.timeout_seconds or 30.0),
        batch_size=int(cfg.model.batch_size or 16),
        dim=int(cfg.model.dim),
        normalize=bool(cfg.model.normalize),
    )
    try:
        vec = embedder.encode_query("蒸汽很小")
    except EmbeddingError as exc:
        detail = exc.detail or {}
        status = detail.get("status_code")
        if status == 401:
            hint = "401 Unauthorized — check that SILICONFLOW_API_KEY is valid and not expired."
        elif status == 403:
            hint = "403 Forbidden — check that the API key has access to the requested model tier."
        elif status == 404:
            hint = (
                f"404 Not Found — model name '{cfg.model.name}' may be wrong or unavailable. "
                "Check siliconflow model catalog."
            )
        elif status in (429, 500, 502, 503, 504):
            hint = f"{status} transient error — retry later or check siliconflow status page."
        else:
            hint = f"EmbeddingError: {detail}"
        print(f"[smoke] siliconflow embedding endpoint check failed: {hint}", file=sys.stderr)
        raise SystemExit(2) from exc
    except Exception as exc:
        print(
            f"[smoke] siliconflow embedding endpoint check failed unexpectedly: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        raise SystemExit(2) from exc
    if vec.shape != (cfg.model.dim,):
        print(
            f"[smoke] dim mismatch: got {vec.shape}, expected ({cfg.model.dim},). "
            f"Update SILICONFLOW_MODEL_DIM or pick a different model.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    print(
        f"[smoke] siliconflow embedding endpoint OK — model={cfg.model.name} dim={vec.shape[0]}",
        file=sys.stderr,
    )


def _atomic_write_json(path: Path, payload: dict) -> None:
    """D6(h): write-to-tmp + replace so SIGINT mid-write doesn't leave a
    corrupted baseline file in fixtures.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(
            json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        tmp.replace(path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _print_delta_table(new_payload: dict, old_path: Path) -> None:
    """D4: print hashing vs siliconflow per-suite per-metric delta table."""
    if not old_path.exists():
        print(f"[compare-with] {old_path} does not exist, skipping delta table", file=sys.stderr)
        return
    old_payload = json.loads(old_path.read_text(encoding="utf-8"))
    new_suites = new_payload.get("suites", {})
    old_suites = old_payload.get("suites", {})
    suite_names = sorted(set(new_suites) | set(old_suites))

    metrics_seen: set[str] = set()
    for s in suite_names:
        metrics_seen.update(new_suites.get(s, {}).keys())
        metrics_seen.update(old_suites.get(s, {}).keys())
    metric_names = sorted(metrics_seen)

    print(f"\n=== Delta: {new_payload.get('embedder', '?')} - {old_payload.get('embedder', '?')} ===")
    header = f"{'suite':<28} " + " ".join(f"{m[:18]:>18}" for m in metric_names)
    print(header)
    print("-" * len(header))
    for s in suite_names:
        n = new_suites.get(s, {})
        o = old_suites.get(s, {})
        cells: list[str] = []
        for m in metric_names:
            nv = n.get(m)
            ov = o.get(m)
            if nv is None or ov is None:
                cells.append(f"{'-':>18}")
                continue
            delta = float(nv) - float(ov)
            sign = "+" if delta >= 0 else ""
            cells.append(f"{sign}{delta:>17.4f}")
        print(f"{s:<28} " + " ".join(cells))
    print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--embedder", choices=SUPPORTED_EMBEDDERS, required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--docs", type=Path, default=DEFAULT_DOCS_DIR)
    parser.add_argument("--suite-dir", type=Path, default=SUITE_DIR)
    parser.add_argument(
        "--compare-with",
        type=Path,
        default=None,
        help="Optional baseline JSON to diff against (prints per-suite per-metric delta).",
    )
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
    if args.embedder == EMBEDDER_SILICONFLOW:
        _smoke_check_siliconflow(cfg)

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

            def _run_suite(_suite_cfg=suite_cfg, _suite_path=suite_path,
                           _docs_path=docs_for_suite, _data_dir=suite_data_dir):
                return run_eval(
                    cfg=_suite_cfg,
                    suite_path=_suite_path,
                    docs_path=_docs_path,
                    eval_data_dir=str(_data_dir),
                    thresholds=EvalThresholds(),
                )

            report = _with_retry(_run_suite) if args.embedder == EMBEDDER_SILICONFLOW else _run_suite()
            suite_metrics[suite_path.name] = _round_metrics(report.summary.metrics.to_dict())
            shutil.rmtree(suite_data_dir, ignore_errors=True)

    payload = {
        "embedder": args.embedder,
        "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "config_hash": _config_hash(args.embedder, cfg, suites),
        "thresholds_applied": {"floor_delta": 0.02},
        "suites": dict(sorted(suite_metrics.items())),
    }
    _atomic_write_json(args.output, payload)
    print(f"wrote {args.output} with {len(suite_metrics)} suite(s)")

    if args.compare_with is not None:
        _print_delta_table(payload, args.compare_with)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
