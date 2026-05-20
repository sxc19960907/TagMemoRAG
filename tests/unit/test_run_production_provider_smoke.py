from __future__ import annotations

import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import run_production_provider_smoke as runner  # noqa: E402


def _clear_provider_env(monkeypatch):
    for name in (
        "TAGMEMORAG__MODEL__PROVIDER",
        "TAGMEMORAG__RERANKER__ENABLED",
        "TAGMEMORAG__ANSWER__ENABLED",
        "TAGMEMORAG__MANUAL_LIBRARY__BLOB_BACKEND",
    ):
        monkeypatch.delenv(name, raising=False)


def _env() -> dict[str, str]:
    return {
        "SILICONFLOW_API_KEY": "sf-secret",
        "DEEPSEEK_API_KEY": "deepseek-secret",
        "TAGMEMORAG_S3_ACCESS_KEY": "tagmemorag",
        "TAGMEMORAG_S3_SECRET_KEY": "tagmemorag-secret",
    }


def test_required_env_failure_is_sanitized(monkeypatch):
    _clear_provider_env(monkeypatch)
    result = runner.run_operator_smoke(
        config_path="examples/config/production-provider-verification.yaml",
        env={},
        start_docker=False,
        ensure_bucket=False,
    )

    body = result.to_dict()
    assert body["status"] == "failed"
    env_check = body["checks"][0]
    assert env_check["name"] == "required_env"
    assert set(env_check["detail"]["missing"]) == {
        "SILICONFLOW_API_KEY",
        "DEEPSEEK_API_KEY",
        "TAGMEMORAG_S3_ACCESS_KEY",
        "TAGMEMORAG_S3_SECRET_KEY",
    }
    serialized = json.dumps(body)
    assert "sf-secret" not in serialized
    assert "deepseek-secret" not in serialized
    assert "tagmemorag-secret" not in serialized


def test_check_only_skips_docker_and_bucket_when_requested(monkeypatch):
    _clear_provider_env(monkeypatch)
    result = runner.run_operator_smoke(
        config_path="examples/config/production-provider-verification.yaml",
        env=_env(),
        start_docker=False,
        ensure_bucket=False,
        check_only=True,
    )

    body = result.to_dict()
    assert body["status"] == "passed"
    checks = {check["name"]: check for check in body["checks"]}
    assert checks["required_env"]["status"] == "passed"
    assert checks["docker_providers"]["status"] == "skipped"
    assert checks["s3_bucket"]["status"] == "skipped"
    assert body["smoke_exit_code"] is None


def test_runner_builds_reset_smoke_command(monkeypatch, tmp_path):
    _clear_provider_env(monkeypatch)
    calls = []

    class Completed:
        returncode = 0

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return Completed()

    monkeypatch.setattr(runner, "_ensure_bucket_step", lambda cfg, env: {"name": "s3_bucket", "status": "passed", "detail": {"action": "exists"}})

    result = runner.run_operator_smoke(
        config_path="examples/config/production-provider-verification.yaml",
        kb_name="kb-live",
        manual_paths=["a.pdf", "b.pdf"],
        metadata_path="manuals.json",
        metadata_format="json",
        workdir=tmp_path / "work",
        output_path=tmp_path / "report.json",
        output_format="markdown",
        question="怎么排水？",
        start_docker=True,
        ensure_bucket=True,
        reset_qdrant=True,
        env=_env(),
        runner=fake_run,
    )

    assert result.status == "passed"
    docker_cmd = calls[0][0]
    smoke_cmd = calls[1][0]
    assert docker_cmd == ["docker", "compose", "--profile", "providers", "up", "-d", "qdrant", "minio"]
    assert smoke_cmd[:4] == [sys.executable, "-m", "tagmemorag", "production-provider"]
    assert "--reset-qdrant-collection" in smoke_cmd
    assert smoke_cmd.count("--manual") == 2
    assert ["--metadata", "manuals.json", "--metadata-format", "json"] == smoke_cmd[smoke_cmd.index("--metadata") : smoke_cmd.index("--metadata") + 4]
    assert str(tmp_path / "report.json") in smoke_cmd
    serialized = result.to_json()
    assert "sf-secret" not in serialized
    assert "deepseek-secret" not in serialized
