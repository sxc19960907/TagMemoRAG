"""Compatibility wrapper for the production-provider smoke verification path.

Prefer `python -m tagmemorag production-provider verify --level smoke` for new
operator workflows. This script remains for existing automation and delegates to
the shared product implementation. It never prints secret values.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
import os
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tagmemorag.production_provider_verify import (  # noqa: E402
    DEFAULT_VERIFY_CONFIG as DEFAULT_CONFIG,
    DEFAULT_VERIFY_MANUAL as DEFAULT_MANUAL,
    DEFAULT_VERIFY_OUTPUT as DEFAULT_OUTPUT,
    DEFAULT_VERIFY_QUESTION as DEFAULT_QUESTION,
    DEFAULT_VERIFY_WORKDIR as DEFAULT_WORKDIR,
    LEGACY_SMOKE_RUNNER_SCHEMA_VERSION,
    ProductionProviderVerifyReport as RunnerResult,
    _ensure_bucket_step,
    _required_env_names,
    _smoke_command,
    run_operator_smoke as _shared_run_operator_smoke,
)


def run_operator_smoke(**kwargs):
    kwargs.setdefault("ensure_bucket_step", _ensure_bucket_step)
    return replace(_shared_run_operator_smoke(**kwargs), schema_version=LEGACY_SMOKE_RUNNER_SCHEMA_VERSION)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--kb", default="default")
    parser.add_argument("--manual", action="append", default=[])
    parser.add_argument("--metadata", default=None)
    parser.add_argument("--metadata-format", choices=["json", "jsonl", "csv"], default="json")
    parser.add_argument("--workdir", default=DEFAULT_WORKDIR)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    parser.add_argument("--question", default=DEFAULT_QUESTION)
    parser.add_argument("--skip-docker", action="store_true", default=False)
    parser.add_argument("--skip-bucket", action="store_true", default=False)
    parser.add_argument("--no-reset-qdrant", action="store_true", default=False)
    parser.add_argument("--check-only", action="store_true", default=False)
    args = parser.parse_args(argv)

    result = run_operator_smoke(
        config_path=args.config,
        kb_name=args.kb,
        manual_paths=args.manual or [DEFAULT_MANUAL],
        metadata_path=args.metadata,
        metadata_format=args.metadata_format,
        workdir=args.workdir,
        output_path=args.output,
        output_format=args.format,
        question=args.question,
        start_docker=not args.skip_docker,
        ensure_bucket=not args.skip_bucket,
        reset_qdrant=not args.no_reset_qdrant,
        check_only=args.check_only,
        env=os.environ,
    )
    print(result.to_json())
    return 0 if result.status == "passed" else 1


__all__ = [
    "DEFAULT_CONFIG",
    "DEFAULT_MANUAL",
    "DEFAULT_OUTPUT",
    "DEFAULT_WORKDIR",
    "RunnerResult",
    "_ensure_bucket_step",
    "_required_env_names",
    "_smoke_command",
    "run_operator_smoke",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
