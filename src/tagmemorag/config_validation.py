from __future__ import annotations

from dataclasses import dataclass, field
import importlib.util
import os
from pathlib import Path
import shutil
from typing import Any

from .config import Settings, load_config

CONFIG_VALIDATION_SCHEMA_VERSION = "config_validation.v1"


@dataclass
class ConfigValidationCheck:
    name: str
    status: str
    detail: dict[str, Any] = field(default_factory=dict)
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name,
            "status": self.status,
            "detail": dict(self.detail),
        }
        if self.message:
            payload["message"] = self.message
        return payload


@dataclass
class ConfigValidationReport:
    status: str
    config_path: str
    profile: dict[str, Any]
    checks: list[ConfigValidationCheck]
    schema_version: str = CONFIG_VALIDATION_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "config_path": self.config_path,
            "profile": dict(self.profile),
            "checks": [check.to_dict() for check in self.checks],
        }


def validate_config(path: str | Path = "config.yaml") -> ConfigValidationReport:
    config_path = str(path)
    checks: list[ConfigValidationCheck] = []
    try:
        cfg = load_config(path)
    except Exception as exc:  # noqa: BLE001
        checks.append(
            ConfigValidationCheck(
                "config_load",
                "failed",
                {"error_type": type(exc).__name__},
                "Config could not be loaded.",
            )
        )
        return ConfigValidationReport(
            status="failed",
            config_path=config_path,
            profile={},
            checks=checks,
        )

    checks.append(ConfigValidationCheck("config_load", "passed", {"exists": Path(path).exists()}))
    checks.extend(_local_path_checks(cfg))
    checks.extend(_remote_env_checks(cfg))
    checks.extend(_dependency_checks(cfg))
    checks.extend(_system_command_checks(cfg))
    checks.extend(_auth_observability_checks(cfg))
    return ConfigValidationReport(
        status=_aggregate_status(checks),
        config_path=config_path,
        profile=_profile(cfg),
        checks=checks,
    )


def _profile(cfg: Settings) -> dict[str, Any]:
    return {
        "model_provider": cfg.model.provider,
        "vector_store": cfg.vector_store.provider,
        "registry_backend": cfg.manual_library.registry_backend,
        "blob_backend": cfg.manual_library.blob_backend,
        "answer_enabled": cfg.answer.enabled,
        "answer_provider": cfg.answer.provider,
        "reranker_enabled": cfg.reranker.enabled,
        "assets_enabled": cfg.assets.enabled,
    }


def _local_path_checks(cfg: Settings) -> list[ConfigValidationCheck]:
    checks = [
        _ensure_dir_check("storage.data_dir", cfg.storage.data_dir),
        _ensure_dir_check("manual_library.root_dir", cfg.manual_library.root_dir),
    ]
    if cfg.manual_library.blob_backend == "local":
        checks.append(_ensure_dir_check("manual_library.blob_root_dir", cfg.manual_library.blob_root_dir))
    if cfg.manual_library.registry_backend == "sqlite":
        checks.append(_ensure_parent_check("manual_library.registry_path", cfg.manual_library.registry_path))
    if cfg.assets.enabled and cfg.assets.store_backend == "local":
        checks.append(_ensure_dir_check("assets.root_dir", cfg.assets.root_dir))
    return checks


def _ensure_dir_check(field: str, value: str) -> ConfigValidationCheck:
    path = Path(value).expanduser()
    try:
        path.mkdir(parents=True, exist_ok=True)
        writable = os.access(path, os.W_OK)
    except Exception as exc:  # noqa: BLE001
        return ConfigValidationCheck(
            "local_path",
            "failed",
            {"field": field, "error_type": type(exc).__name__},
            "Local directory could not be created or accessed.",
        )
    if not writable:
        return ConfigValidationCheck(
            "local_path",
            "failed",
            {"field": field, "writable": False},
            "Local directory is not writable.",
        )
    return ConfigValidationCheck("local_path", "passed", {"field": field, "writable": True})


def _ensure_parent_check(field: str, value: str) -> ConfigValidationCheck:
    path = Path(value).expanduser()
    return _ensure_dir_check(f"{field}.parent", str(path.parent))


def _remote_env_checks(cfg: Settings) -> list[ConfigValidationCheck]:
    checks: list[ConfigValidationCheck] = []
    if cfg.model.provider == "http":
        checks.append(_env_check("model.api_key_env", cfg.model.api_key_env, "model.provider=http"))
    if cfg.reranker.enabled and cfg.reranker.provider == "siliconflow":
        checks.append(_env_check("reranker.api_key_env", cfg.reranker.api_key_env, "reranker.enabled=true"))
    if cfg.answer.enabled and cfg.answer.provider == "openai_compatible":
        checks.append(_env_check("answer.api_key_env", cfg.answer.api_key_env, "answer.provider=openai_compatible"))
    if cfg.manual_library.blob_backend == "s3":
        if not cfg.manual_library.s3_bucket.strip():
            checks.append(
                ConfigValidationCheck(
                    "s3_config",
                    "failed",
                    {"field": "manual_library.s3_bucket", "blob_backend": "s3"},
                    "S3 blob storage requires a bucket.",
                )
            )
        else:
            checks.append(
                ConfigValidationCheck(
                    "s3_config",
                    "passed",
                    {"field": "manual_library.s3_bucket", "configured": True},
                )
            )
        for field, env_name in (
            ("manual_library.s3_access_key_env", cfg.manual_library.s3_access_key_env),
            ("manual_library.s3_secret_key_env", cfg.manual_library.s3_secret_key_env),
        ):
            if env_name.strip():
                checks.append(_env_check(field, env_name, "manual_library.blob_backend=s3"))
    return checks


def _env_check(field: str, env_name: str, reason: str) -> ConfigValidationCheck:
    name = str(env_name or "").strip()
    if not name:
        return ConfigValidationCheck(
            "env_var",
            "warning",
            {"field": field, "env": "", "reason": reason},
            "Env var name is empty; runtime may rely on a provider default credential chain.",
        )
    present = bool(os.environ.get(name))
    return ConfigValidationCheck(
        "env_var",
        "passed" if present else "failed",
        {"field": field, "env": name, "present": present, "reason": reason},
        "" if present else "Required environment variable is not set.",
    )


def _dependency_checks(cfg: Settings) -> list[ConfigValidationCheck]:
    checks: list[ConfigValidationCheck] = []
    if cfg.vector_store.provider == "qdrant":
        checks.append(_dependency_check("qdrant-client", "qdrant_client", "vector_store.provider=qdrant"))
    if cfg.manual_library.blob_backend == "s3":
        checks.append(_dependency_check("boto3", "boto3", "manual_library.blob_backend=s3"))
    return checks


def _dependency_check(name: str, module: str, reason: str) -> ConfigValidationCheck:
    available = importlib.util.find_spec(module) is not None
    return ConfigValidationCheck(
        "dependency",
        "passed" if available else "warning",
        {"dependency": name, "available": available, "reason": reason},
        "" if available else "Optional dependency is not importable in this environment.",
    )


def _system_command_checks(cfg: Settings) -> list[ConfigValidationCheck]:
    if not (cfg.ocr.enabled and cfg.ocr.provider == "tesseract_cli"):
        return []
    return [
        _command_check("ocr.pdf_renderer_command", cfg.ocr.pdf_renderer_command, "ocr.provider=tesseract_cli"),
        _command_check("ocr.tesseract_command", cfg.ocr.tesseract_command, "ocr.provider=tesseract_cli"),
    ]


def _command_check(field: str, command: str, reason: str) -> ConfigValidationCheck:
    command_name = Path(str(command or "").strip()).name
    available = bool(command_name and shutil.which(str(command).strip()))
    return ConfigValidationCheck(
        "system_command",
        "passed" if available else "warning",
        {"field": field, "command": command_name, "available": available, "reason": reason},
        "" if available else "Optional system command is not available in PATH.",
    )


def _auth_observability_checks(cfg: Settings) -> list[ConfigValidationCheck]:
    metrics_path = cfg.observability.metrics.path
    if cfg.auth.enabled and cfg.observability.metrics.enabled and metrics_path not in cfg.auth.public_paths:
        return [
            ConfigValidationCheck(
                "auth_metrics_public_path",
                "warning",
                {"metrics_path": metrics_path, "auth_enabled": True},
                "Metrics are enabled but the metrics path is not public.",
            )
        ]
    return [
        ConfigValidationCheck(
            "auth_metrics_public_path",
            "passed",
            {"metrics_path": metrics_path, "auth_enabled": cfg.auth.enabled},
        )
    ]


def _aggregate_status(checks: list[ConfigValidationCheck]) -> str:
    statuses = {check.status for check in checks}
    if "failed" in statuses:
        return "failed"
    if "warning" in statuses:
        return "warning"
    return "passed"


__all__ = [
    "CONFIG_VALIDATION_SCHEMA_VERSION",
    "ConfigValidationCheck",
    "ConfigValidationReport",
    "validate_config",
]
