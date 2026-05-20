"""One-command local production-provider smoke runner.

This script wraps the operator chores around `tagmemorag production-provider
smoke`: environment checks, local Docker provider startup, MinIO bucket setup,
and a reset-Qdrant smoke run. It never prints secret values.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tagmemorag.config import Settings, load_config  # noqa: E402

DEFAULT_CONFIG = "examples/config/production-provider-verification.yaml"
DEFAULT_MANUAL = "product_manuals/washer/ASKO W6564.pdf"
DEFAULT_WORKDIR = ".tmp/production-provider-verification/operator-smoke"
DEFAULT_OUTPUT = ".tmp/production-provider-verification/operator-smoke-report.json"
DEFAULT_QUESTION = "ASKO W6564 洗衣机不排水时应该检查什么？"


@dataclass(frozen=True)
class RunnerResult:
    status: str
    config_path: str
    output_path: str
    checks: list[dict[str, Any]]
    smoke_exit_code: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "production_provider_smoke_runner.v1",
            "status": self.status,
            "config_path": self.config_path,
            "output_path": self.output_path,
            "checks": list(self.checks),
            "smoke_exit_code": self.smoke_exit_code,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)


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


def run_operator_smoke(
    *,
    config_path: str | Path = DEFAULT_CONFIG,
    kb_name: str = "default",
    manual_paths: list[str] | None = None,
    metadata_path: str | None = None,
    metadata_format: str = "json",
    workdir: str | Path = DEFAULT_WORKDIR,
    output_path: str | Path = DEFAULT_OUTPUT,
    output_format: str = "json",
    question: str = DEFAULT_QUESTION,
    start_docker: bool = True,
    ensure_bucket: bool = True,
    reset_qdrant: bool = True,
    check_only: bool = False,
    env: Mapping[str, str] | None = None,
    runner=subprocess.run,
) -> RunnerResult:
    env_map = dict(env or {})
    cfg = load_config(config_path)
    checks: list[dict[str, Any]] = []

    env_check = _required_env_check(cfg, env_map)
    checks.append(env_check)
    if env_check["status"] == "failed":
        return RunnerResult("failed", str(config_path), str(output_path), checks)

    if start_docker:
        checks.append(_run_step("docker_providers", _docker_command(), runner=runner))
    else:
        checks.append({"name": "docker_providers", "status": "skipped", "detail": {"reason": "skip_docker"}})

    if ensure_bucket:
        checks.append(_ensure_bucket_step(cfg, env_map))
    else:
        checks.append({"name": "s3_bucket", "status": "skipped", "detail": {"reason": "skip_bucket"}})

    if check_only:
        return RunnerResult(_aggregate(checks), str(config_path), str(output_path), checks)

    smoke_cmd = _smoke_command(
        config_path=str(config_path),
        kb_name=kb_name,
        manual_paths=manual_paths or [DEFAULT_MANUAL],
        metadata_path=metadata_path,
        metadata_format=metadata_format,
        workdir=str(workdir),
        output_path=str(output_path),
        output_format=output_format,
        question=question,
        reset_qdrant=reset_qdrant,
    )
    smoke = _run_step("production_provider_smoke", smoke_cmd, runner=runner)
    checks.append(smoke)
    return RunnerResult(_aggregate(checks), str(config_path), str(output_path), checks, smoke_exit_code=int(smoke["detail"].get("exit_code", 1)))


def _required_env_check(cfg: Settings, env: Mapping[str, str]) -> dict[str, Any]:
    required = _required_env_names(cfg)
    missing = [name for name in required if not env.get(name)]
    return {
        "name": "required_env",
        "status": "failed" if missing else "passed",
        "detail": {
            "required": required,
            "present": [name for name in required if name not in missing],
            "missing": missing,
        },
        **({"error": {"type": "MissingEnv", "reason": "required_env_var_missing"}} if missing else {}),
    }


def _required_env_names(cfg: Settings) -> list[str]:
    names = []
    if cfg.model.provider == "http":
        names.append(cfg.model.api_key_env)
    if cfg.reranker.enabled and cfg.reranker.provider == "siliconflow":
        names.append(cfg.reranker.api_key_env)
    if cfg.answer.enabled and cfg.answer.provider == "openai_compatible":
        names.append(cfg.answer.api_key_env)
    if cfg.manual_library.blob_backend == "s3":
        names.append(cfg.manual_library.s3_access_key_env)
        names.append(cfg.manual_library.s3_secret_key_env)
        if cfg.manual_library.s3_session_token_env:
            names.append(cfg.manual_library.s3_session_token_env)
    return sorted(dict.fromkeys(name for name in names if name))


def _docker_command() -> list[str]:
    return ["docker", "compose", "--profile", "providers", "up", "-d", "qdrant", "minio"]


def _smoke_command(
    *,
    config_path: str,
    kb_name: str,
    manual_paths: list[str],
    metadata_path: str | None,
    metadata_format: str,
    workdir: str,
    output_path: str,
    output_format: str,
    question: str,
    reset_qdrant: bool,
) -> list[str]:
    cmd = [
        sys.executable,
        "-m",
        "tagmemorag",
        "production-provider",
        "smoke",
        "--config",
        config_path,
        "--kb",
        kb_name,
        "--workdir",
        workdir,
        "--output",
        output_path,
        "--format",
        output_format,
        "--question",
        question,
    ]
    for manual in manual_paths:
        cmd.extend(["--manual", manual])
    if metadata_path:
        cmd.extend(["--metadata", metadata_path, "--metadata-format", metadata_format])
    if reset_qdrant:
        cmd.append("--reset-qdrant-collection")
    return cmd


def _run_step(name: str, cmd: list[str], *, runner=subprocess.run) -> dict[str, Any]:
    completed = runner(cmd, cwd=str(REPO_ROOT), text=True, capture_output=True)
    return {
        "name": name,
        "status": "passed" if completed.returncode == 0 else "failed",
        "detail": {
            "command": _sanitize_command(cmd),
            "exit_code": int(completed.returncode),
        },
        **({"error": {"type": "CommandFailed", "reason": name}} if completed.returncode else {}),
    }


def _ensure_bucket_step(cfg: Settings, env: Mapping[str, str]) -> dict[str, Any]:
    if cfg.manual_library.blob_backend != "s3":
        return {"name": "s3_bucket", "status": "skipped", "detail": {"reason": "blob_backend_not_s3"}}
    try:
        import boto3
        from botocore.client import Config
        from botocore.exceptions import ClientError
    except ImportError as exc:
        return {"name": "s3_bucket", "status": "failed", "detail": {"bucket": cfg.manual_library.s3_bucket}, "error": {"type": "ImportError", "reason": type(exc).__name__}}
    try:
        client = boto3.client(
            "s3",
            endpoint_url=cfg.manual_library.s3_endpoint_url or None,
            aws_access_key_id=env.get(cfg.manual_library.s3_access_key_env),
            aws_secret_access_key=env.get(cfg.manual_library.s3_secret_key_env),
            aws_session_token=env.get(cfg.manual_library.s3_session_token_env) if cfg.manual_library.s3_session_token_env else None,
            region_name=cfg.manual_library.s3_region or "us-east-1",
            config=Config(s3={"addressing_style": cfg.manual_library.s3_addressing_style}),
        )
        try:
            client.head_bucket(Bucket=cfg.manual_library.s3_bucket)
            action = "exists"
        except ClientError:
            client.create_bucket(Bucket=cfg.manual_library.s3_bucket)
            action = "created"
        return {"name": "s3_bucket", "status": "passed", "detail": {"bucket": cfg.manual_library.s3_bucket, "action": action}}
    except Exception as exc:  # noqa: BLE001
        return {"name": "s3_bucket", "status": "failed", "detail": {"bucket": cfg.manual_library.s3_bucket}, "error": {"type": type(exc).__name__, "reason": _safe_reason(str(exc))}}


def _aggregate(checks: list[dict[str, Any]]) -> str:
    statuses = {check["status"] for check in checks}
    if "failed" in statuses:
        return "failed"
    if "warning" in statuses:
        return "warning"
    return "passed"


def _sanitize_command(cmd: list[str]) -> list[str]:
    return [part if not str(part).startswith("sk-") else "sk-..." for part in cmd]


def _safe_reason(reason: str) -> str:
    return " ".join(str(reason or "").split())[:160] or "production_provider_smoke_runner_failed"


__all__ = [
    "DEFAULT_CONFIG",
    "DEFAULT_MANUAL",
    "DEFAULT_OUTPUT",
    "DEFAULT_WORKDIR",
    "RunnerResult",
    "_required_env_names",
    "_smoke_command",
    "run_operator_smoke",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
