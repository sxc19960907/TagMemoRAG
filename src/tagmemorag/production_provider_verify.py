from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Callable, Iterable, Mapping

from .config import Settings, load_config
from .eval.dataset import EvalThresholds
from .production_pilot import (
    DEFAULT_PILOT_DOCS,
    DEFAULT_PILOT_SUITE,
    DEFAULT_PILOT_THRESHOLDS,
    ProductionPilotReport,
    run_production_pilot,
    write_pilot_report,
)

VERIFY_SCHEMA_VERSION = "production_provider_verify.v1"
LEGACY_SMOKE_RUNNER_SCHEMA_VERSION = "production_provider_smoke_runner.v1"
DEFAULT_VERIFY_CONFIG = "examples/config/production-provider-verification.yaml"
DEFAULT_VERIFY_MANUAL = "product_manuals/washer/ASKO W6564.pdf"
DEFAULT_VERIFY_WORKDIR = ".tmp/production-provider-verification/operator-smoke"
DEFAULT_VERIFY_OUTPUT = ".tmp/production-provider-verification/operator-smoke-report.json"
DEFAULT_VERIFY_QUESTION = "ASKO W6564 洗衣机不排水时应该检查什么？"

Runner = Callable[..., Any]
PilotRunner = Callable[..., ProductionPilotReport]
BucketStep = Callable[[Settings, Mapping[str, str]], dict[str, Any]]


@dataclass(frozen=True)
class ProductionProviderVerifyReport:
    status: str
    level: str
    config_path: str
    output_path: str
    checks: list[dict[str, Any]]
    smoke_exit_code: int | None = None
    pilot_status: str | None = None
    schema_version: str = VERIFY_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "status": self.status,
            "level": self.level,
            "config_path": self.config_path,
            "output_path": self.output_path,
            "checks": list(self.checks),
            "smoke_exit_code": self.smoke_exit_code,
        }
        if self.pilot_status is not None:
            payload["pilot_status"] = self.pilot_status
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)

    def to_markdown(self) -> str:
        lines = [
            "# TagMemoRAG Production Provider Verify Report",
            "",
            f"- Status: `{self.status}`",
            f"- Level: `{self.level}`",
            f"- Config: `{self.config_path}`",
            f"- Output: `{self.output_path}`",
        ]
        if self.smoke_exit_code is not None:
            lines.append(f"- Smoke exit code: `{self.smoke_exit_code}`")
        if self.pilot_status is not None:
            lines.append(f"- Pilot status: `{self.pilot_status}`")
        lines.extend(["", "| Check | Status | Detail |", "| --- | --- | --- |"])
        for check in self.checks:
            detail = _compact_detail(dict(check.get("detail", {})))
            error = check.get("error")
            if isinstance(error, dict):
                reason = f"{error.get('type', 'Error')}:{error.get('reason', '')}"
                detail = f"{detail}; error={reason}".strip("; ")
            lines.append(f"| `{check.get('name', '')}` | `{check.get('status', '')}` | {detail} |")
        return "\n".join(lines) + "\n"


RunnerResult = ProductionProviderVerifyReport


def run_production_provider_verify(
    *,
    level: str = "smoke",
    config_path: str | Path = DEFAULT_VERIFY_CONFIG,
    kb_name: str = "default",
    manual_paths: list[str] | None = None,
    metadata_path: str | None = None,
    metadata_format: str = "json",
    workdir: str | Path = DEFAULT_VERIFY_WORKDIR,
    output_path: str | Path = DEFAULT_VERIFY_OUTPUT,
    output_format: str = "json",
    question: str = DEFAULT_VERIFY_QUESTION,
    start_docker: bool = True,
    ensure_bucket: bool = True,
    reset_qdrant: bool = True,
    check_only: bool = False,
    env: Mapping[str, str] | None = None,
    runner: Runner = subprocess.run,
    ensure_bucket_step: BucketStep | None = None,
    pilot_suite_path: str | Path = DEFAULT_PILOT_SUITE,
    pilot_docs_path: str | Path | None = DEFAULT_PILOT_DOCS,
    pilot_workdir: str | Path | None = None,
    pilot_output_path: str | Path | None = None,
    pilot_output_format: str = "json",
    pilot_top_k: int | None = None,
    pilot_source_k: int | None = None,
    pilot_thresholds: EvalThresholds = DEFAULT_PILOT_THRESHOLDS,
    pilot_hashing_baseline_path: str | Path | None = None,
    pilot_production_baseline_path: str | Path | None = None,
    pilot_informational_suites: Iterable[str] | None = None,
    pilot_accepted_suites: Iterable[str] | None = None,
    pilot_runner: PilotRunner = run_production_pilot,
) -> ProductionProviderVerifyReport:
    if level not in {"smoke", "pilot"}:
        raise ValueError("level must be 'smoke' or 'pilot'")
    env_map = dict(os.environ if env is None else env)
    cfg = load_config(config_path)
    checks: list[dict[str, Any]] = []

    env_check = _required_env_check(cfg, env_map)
    checks.append(env_check)
    if env_check["status"] == "failed":
        return ProductionProviderVerifyReport("failed", level, str(config_path), str(output_path), checks)

    if start_docker:
        checks.append(_run_step("docker_providers", _docker_command(), runner=runner))
    else:
        checks.append({"name": "docker_providers", "status": "skipped", "detail": {"reason": "skip_docker"}})

    decision_check = _decision_check(cfg, env_map)
    if decision_check is not None:
        checks.append(decision_check)

    bucket_step = ensure_bucket_step or _ensure_bucket_step
    if ensure_bucket:
        checks.append(bucket_step(cfg, env_map))
    else:
        checks.append({"name": "s3_bucket", "status": "skipped", "detail": {"reason": "skip_bucket"}})

    if check_only:
        return ProductionProviderVerifyReport(_aggregate(checks), level, str(config_path), str(output_path), checks)

    smoke_cmd = _smoke_command(
        config_path=str(config_path),
        kb_name=kb_name,
        manual_paths=manual_paths or [DEFAULT_VERIFY_MANUAL],
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
    smoke_exit_code = int(smoke["detail"].get("exit_code", 1))
    status = _aggregate_verify_checks(checks)
    if level == "smoke" or status == "failed":
        return ProductionProviderVerifyReport(
            status,
            level,
            str(config_path),
            str(output_path),
            checks,
            smoke_exit_code=smoke_exit_code,
        )

    pilot_report = pilot_runner(
        config_path=config_path,
        suite_path=pilot_suite_path,
        docs_path=pilot_docs_path,
        workdir=pilot_workdir,
        top_k=pilot_top_k,
        source_k=pilot_source_k,
        thresholds=pilot_thresholds,
        hashing_baseline_path=pilot_hashing_baseline_path,
        production_baseline_path=pilot_production_baseline_path,
        informational_suites=pilot_informational_suites,
        accepted_suites=pilot_accepted_suites,
    )
    if pilot_output_path:
        write_pilot_report(pilot_report, pilot_output_path, fmt=pilot_output_format)
    checks.append(_pilot_check(pilot_report, pilot_output_path=pilot_output_path))
    return ProductionProviderVerifyReport(
        _aggregate_verify_checks(checks),
        level,
        str(config_path),
        str(output_path),
        checks,
        smoke_exit_code=smoke_exit_code,
        pilot_status=pilot_report.status,
    )


def run_operator_smoke(**kwargs: Any) -> ProductionProviderVerifyReport:
    return run_production_provider_verify(level="smoke", **kwargs)


def write_verify_report(report: ProductionProviderVerifyReport, path: str | Path, *, fmt: str = "json") -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "json":
        text = report.to_json()
    elif fmt == "markdown":
        text = report.to_markdown()
    else:
        raise ValueError("fmt must be 'json' or 'markdown'")
    output_path.write_text(text + ("" if text.endswith("\n") else "\n"), encoding="utf-8")


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
    decision_cfg = cfg.agentic.decision
    if _decision_check_required(cfg) and decision_cfg.provider == "openai_compatible":
        names.append(_decision_api_key_env(cfg))
    if cfg.manual_library.blob_backend == "s3":
        names.append(cfg.manual_library.s3_access_key_env)
        names.append(cfg.manual_library.s3_secret_key_env)
        if cfg.manual_library.s3_session_token_env:
            names.append(cfg.manual_library.s3_session_token_env)
    return sorted(dict.fromkeys(name for name in names if name))


def _decision_check_required(cfg: Settings) -> bool:
    return cfg.agentic.mode != "classic" or cfg.agentic.decision.enabled


def _decision_api_key_env(cfg: Settings) -> str:
    return cfg.agentic.decision.api_key_env or cfg.answer.api_key_env


def _decision_model_id(cfg: Settings) -> str:
    return cfg.agentic.decision.model_id or cfg.answer.model_id


def _decision_base_url(cfg: Settings) -> str:
    return cfg.agentic.decision.base_url or cfg.answer.base_url


def _decision_check(cfg: Settings, env: Mapping[str, str]) -> dict[str, Any] | None:
    if not _decision_check_required(cfg):
        return None
    decision_cfg = cfg.agentic.decision
    provider = decision_cfg.provider
    detail: dict[str, Any] = {
        "mode": cfg.agentic.mode,
        "decision_enabled": bool(decision_cfg.enabled),
        "provider": provider,
        "tool_schema_mode": decision_cfg.tool_schema_mode,
        "json_strict": bool(decision_cfg.json_strict),
    }
    if provider == "noop":
        return {"name": "decision", "status": "passed", "detail": {**detail, "reason": "noop_provider"}}
    if provider != "openai_compatible":
        return {
            "name": "decision",
            "status": "failed",
            "detail": detail,
            "error": {"type": "InvalidConfig", "reason": "unsupported_decision_provider"},
        }
    env_name = _decision_api_key_env(cfg)
    model_id = _decision_model_id(cfg)
    base_url = _decision_base_url(cfg)
    detail.update(
        {
            "api_key_env": env_name,
            "api_key_present": bool(env.get(env_name)),
            "model_configured": bool(model_id),
            "base_url_configured": bool(base_url),
            "max_output_tokens": int(decision_cfg.max_output_tokens),
        }
    )
    if not env_name or not env.get(env_name):
        return {
            "name": "decision",
            "status": "failed",
            "detail": detail,
            "error": {"type": "MissingEnv", "reason": "decision_env_var_missing"},
        }
    if not model_id:
        return {
            "name": "decision",
            "status": "failed",
            "detail": detail,
            "error": {"type": "InvalidConfig", "reason": "decision_model_missing"},
        }
    return {"name": "decision", "status": "passed", "detail": detail}


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


def _run_step(name: str, cmd: list[str], *, runner: Runner = subprocess.run) -> dict[str, Any]:
    completed = runner(cmd, cwd=str(_repo_root()), text=True, capture_output=True)
    detail = {
        "command": _sanitize_command(cmd),
        "exit_code": int(completed.returncode),
    }
    if completed.returncode:
        stdout_tail = _bounded_output_tail(getattr(completed, "stdout", ""))
        stderr_tail = _bounded_output_tail(getattr(completed, "stderr", ""))
        if stdout_tail:
            detail["stdout_tail"] = stdout_tail
        if stderr_tail:
            detail["stderr_tail"] = stderr_tail
    return {
        "name": name,
        "status": "passed" if completed.returncode == 0 else "failed",
        "detail": detail,
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
        return {
            "name": "s3_bucket",
            "status": "failed",
            "detail": {"bucket": cfg.manual_library.s3_bucket},
            "error": {"type": "ImportError", "reason": type(exc).__name__},
        }
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
        return {
            "name": "s3_bucket",
            "status": "failed",
            "detail": {"bucket": cfg.manual_library.s3_bucket},
            "error": {"type": type(exc).__name__, "reason": _safe_reason(str(exc))},
        }


def _pilot_check(report: ProductionPilotReport, *, pilot_output_path: str | Path | None) -> dict[str, Any]:
    return {
        "name": "production_pilot",
        "status": report.status,
        "detail": {
            "schema_version": report.schema_version,
            "workdir": report.workdir,
            "output_path": str(pilot_output_path) if pilot_output_path else None,
            "stages": _count_statuses([stage.status for stage in report.stages]),
        },
        **({"error": {"type": "PilotFailed", "reason": "production_pilot"}} if report.status == "failed" else {}),
    }


def _aggregate(checks: list[dict[str, Any]]) -> str:
    statuses = {check["status"] for check in checks}
    if "failed" in statuses:
        return "failed"
    if "warning" in statuses:
        return "warning"
    return "passed"


def _aggregate_verify_checks(checks: list[dict[str, Any]]) -> str:
    statuses = {check["status"] for check in checks}
    if "failed" not in statuses:
        return _aggregate(checks)
    by_name = {str(check.get("name")): check for check in checks}
    failed = {name for name, check in by_name.items() if check.get("status") == "failed"}
    docker_only_failed = failed == {"docker_providers"}
    downstream_passed = all(
        by_name.get(name, {}).get("status") == "passed"
        for name in ("s3_bucket", "production_provider_smoke")
    )
    if docker_only_failed and downstream_passed:
        return "warning"
    return "failed"


def _count_statuses(statuses: Iterable[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for status in statuses:
        counts[status] = counts.get(status, 0) + 1
    return counts


def _sanitize_command(cmd: list[str]) -> list[str]:
    return [part if not str(part).startswith("sk-") else "sk-..." for part in cmd]


def _bounded_output_tail(value: Any, *, limit: int = 320) -> str:
    text = _sanitize_output_text(str(value or ""))
    if len(text) <= limit:
        return text
    return text[-limit:]


def _sanitize_output_text(value: str) -> str:
    text = " ".join(str(value or "").split())
    text = re.sub(r"sk-[A-Za-z0-9._-]+", "sk-...", text)
    return text


def _safe_reason(reason: str) -> str:
    return " ".join(str(reason or "").split())[:160] or "production_provider_verify_failed"


def _compact_detail(detail: dict[str, Any]) -> str:
    if not detail:
        return ""
    return "; ".join(f"{key}={json.dumps(value, ensure_ascii=False, sort_keys=True)}" for key, value in detail.items())


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


__all__ = [
    "DEFAULT_VERIFY_CONFIG",
    "DEFAULT_VERIFY_MANUAL",
    "DEFAULT_VERIFY_OUTPUT",
    "DEFAULT_VERIFY_QUESTION",
    "DEFAULT_VERIFY_WORKDIR",
    "LEGACY_SMOKE_RUNNER_SCHEMA_VERSION",
    "ProductionProviderVerifyReport",
    "RunnerResult",
    "_docker_command",
    "_ensure_bucket_step",
    "_required_env_names",
    "_smoke_command",
    "run_operator_smoke",
    "run_production_provider_verify",
    "write_verify_report",
]
