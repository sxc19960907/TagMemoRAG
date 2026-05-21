from __future__ import annotations

import json
import sys

from tagmemorag.eval.dataset import EvalThresholds
from tagmemorag.production_pilot import PilotStage, ProductionPilotReport
from tagmemorag.production_provider_verify import run_production_provider_verify, write_verify_report


def _env() -> dict[str, str]:
    return {
        "SILICONFLOW_API_KEY": "sf-secret",
        "DEEPSEEK_API_KEY": "deepseek-secret",
        "TAGMEMORAG_S3_ACCESS_KEY": "tagmemorag",
        "TAGMEMORAG_S3_SECRET_KEY": "tagmemorag-secret",
    }


def _clear_provider_env(monkeypatch):
    for name in (
        "TAGMEMORAG__MODEL__PROVIDER",
        "TAGMEMORAG__RERANKER__ENABLED",
        "TAGMEMORAG__ANSWER__ENABLED",
        "TAGMEMORAG__AGENTIC__MODE",
        "TAGMEMORAG__AGENTIC__DECISION__ENABLED",
        "TAGMEMORAG__MANUAL_LIBRARY__BLOB_BACKEND",
    ):
        monkeypatch.delenv(name, raising=False)


class _Completed:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_verify_smoke_check_only_skips_nested_smoke(monkeypatch):
    _clear_provider_env(monkeypatch)
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return _Completed()

    result = run_production_provider_verify(
        level="smoke",
        config_path="examples/config/production-provider-verification.yaml",
        env=_env(),
        runner=fake_run,
        ensure_bucket_step=lambda cfg, env: {"name": "s3_bucket", "status": "passed", "detail": {"action": "exists"}},
        check_only=True,
    )

    assert result.status == "passed"
    assert result.smoke_exit_code is None
    assert calls == [["docker", "compose", "--profile", "providers", "up", "-d", "qdrant", "minio"]]
    assert "decision" not in {check["name"] for check in result.checks}


def test_verify_decision_check_runs_when_agentic_enabled(monkeypatch, tmp_path):
    _clear_provider_env(monkeypatch)
    config = tmp_path / "agentic.yaml"
    config.write_text(
        """
model:
  provider: hashing
answer:
  provider: openai_compatible
  model_id: answer-model
  api_key_env: ANSWER_KEY
agentic:
  mode: agentic
  decision:
    provider: openai_compatible
    api_key_env: DECISION_KEY
""",
        encoding="utf-8",
    )

    result = run_production_provider_verify(
        level="smoke",
        config_path=config,
        env={**_env(), "DECISION_KEY": "decision-secret"},
        start_docker=False,
        ensure_bucket=False,
        check_only=True,
    )

    checks = {check["name"]: check for check in result.checks}
    assert result.status == "passed"
    assert checks["decision"]["status"] == "passed"
    assert checks["decision"]["detail"]["api_key_env"] == "DECISION_KEY"
    assert checks["decision"]["detail"]["model_configured"] is True
    assert "decision-secret" not in result.to_json()
    assert "| `decision` | `passed` |" in result.to_markdown()


def test_verify_decision_env_is_required_when_decision_enabled(monkeypatch, tmp_path):
    _clear_provider_env(monkeypatch)
    config = tmp_path / "decision.yaml"
    config.write_text(
        """
model:
  provider: hashing
answer:
  provider: openai_compatible
  model_id: answer-model
  api_key_env: ANSWER_KEY
agentic:
  decision:
    enabled: true
    provider: openai_compatible
    api_key_env: DECISION_MISSING
""",
        encoding="utf-8",
    )

    result = run_production_provider_verify(
        level="smoke",
        config_path=config,
        env=_env(),
        start_docker=False,
        ensure_bucket=False,
        check_only=True,
    )

    required = next(check for check in result.checks if check["name"] == "required_env")
    assert result.status == "failed"
    assert "DECISION_MISSING" in required["detail"]["missing"]


def test_verify_smoke_builds_sanitized_nested_command(monkeypatch, tmp_path):
    _clear_provider_env(monkeypatch)
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return _Completed()

    result = run_production_provider_verify(
        level="smoke",
        config_path="examples/config/production-provider-verification.yaml",
        kb_name="kb-live",
        manual_paths=["a.pdf", "b.pdf"],
        metadata_path="manuals.json",
        workdir=tmp_path / "work",
        output_path=tmp_path / "nested.json",
        output_format="markdown",
        question="怎么排水？",
        env=_env(),
        runner=fake_run,
        ensure_bucket_step=lambda cfg, env: {"name": "s3_bucket", "status": "passed", "detail": {"action": "exists"}},
    )

    assert result.status == "passed"
    assert result.smoke_exit_code == 0
    smoke_cmd = calls[1]
    assert smoke_cmd[:4] == [sys.executable, "-m", "tagmemorag", "production-provider"]
    assert smoke_cmd.count("--manual") == 2
    assert "--reset-qdrant-collection" in smoke_cmd
    serialized = result.to_json()
    assert "sf-secret" not in serialized
    assert "deepseek-secret" not in serialized
    assert "tagmemorag-secret" not in serialized


def test_docker_failure_with_passing_downstream_is_warning_and_diagnosed(monkeypatch, tmp_path):
    _clear_provider_env(monkeypatch)
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[0] == "docker":
            return _Completed(
                1,
                stdout="starting qdrant",
                stderr="port already allocated; token sk-x",
            )
        return _Completed()

    result = run_production_provider_verify(
        level="smoke",
        config_path="examples/config/production-provider-verification.yaml",
        workdir=tmp_path / "work",
        output_path=tmp_path / "nested.json",
        env=_env(),
        runner=fake_run,
        ensure_bucket_step=lambda cfg, env: {"name": "s3_bucket", "status": "passed", "detail": {"action": "exists"}},
    )

    assert result.status == "warning"
    checks = {check["name"]: check for check in result.checks}
    assert checks["docker_providers"]["status"] == "failed"
    assert checks["docker_providers"]["detail"]["stdout_tail"] == "starting qdrant"
    assert checks["docker_providers"]["detail"]["stderr_tail"] == "port already allocated; token sk-..."
    serialized = result.to_json()
    assert "sk-x" not in serialized


def test_docker_failure_stays_failed_in_check_only(monkeypatch):
    _clear_provider_env(monkeypatch)

    def fake_run(cmd, **kwargs):
        return _Completed(1, stderr="port already allocated")

    result = run_production_provider_verify(
        level="smoke",
        config_path="examples/config/production-provider-verification.yaml",
        env=_env(),
        runner=fake_run,
        ensure_bucket_step=lambda cfg, env: {"name": "s3_bucket", "status": "passed", "detail": {"action": "exists"}},
        check_only=True,
    )

    assert result.status == "failed"
    checks = {check["name"]: check for check in result.checks}
    assert checks["docker_providers"]["detail"]["stderr_tail"] == "port already allocated"


def test_docker_failure_and_nested_smoke_failure_stays_failed(monkeypatch, tmp_path):
    _clear_provider_env(monkeypatch)

    def fake_run(cmd, **kwargs):
        if cmd[0] == "docker":
            return _Completed(1, stderr="port already allocated")
        return _Completed(1, stderr="provider probe failed")

    result = run_production_provider_verify(
        level="smoke",
        config_path="examples/config/production-provider-verification.yaml",
        workdir=tmp_path / "work",
        output_path=tmp_path / "nested.json",
        env=_env(),
        runner=fake_run,
        ensure_bucket_step=lambda cfg, env: {"name": "s3_bucket", "status": "passed", "detail": {"action": "exists"}},
    )

    assert result.status == "failed"
    checks = {check["name"]: check for check in result.checks}
    assert checks["docker_providers"]["status"] == "failed"
    assert checks["production_provider_smoke"]["status"] == "failed"


def test_verify_pilot_runs_after_smoke_and_writes_pilot_report(monkeypatch, tmp_path):
    _clear_provider_env(monkeypatch)
    pilot_calls = []

    def fake_run(cmd, **kwargs):
        return _Completed()

    def fake_pilot_runner(**kwargs):
        pilot_calls.append(kwargs)
        return ProductionPilotReport(
            status="passed",
            config_path=str(kwargs["config_path"]),
            suite_path=str(kwargs["suite_path"]),
            docs_path=str(kwargs["docs_path"]),
            workdir=str(kwargs["workdir"]),
            stages=[PilotStage("eval", "passed", {"cases": 1})],
            next_steps=[],
        )

    pilot_output = tmp_path / "pilot.json"
    thresholds = EvalThresholds(min_recall_at_k=0.81, min_mrr=0.82, min_hit_at_k=0.83)
    result = run_production_provider_verify(
        level="pilot",
        config_path="examples/config/production-provider-verification.yaml",
        env=_env(),
        runner=fake_run,
        ensure_bucket_step=lambda cfg, env: {"name": "s3_bucket", "status": "passed", "detail": {"action": "exists"}},
        pilot_suite_path="suite.jsonl",
        pilot_docs_path="docs",
        pilot_workdir=tmp_path / "pilot-work",
        pilot_output_path=pilot_output,
        pilot_thresholds=thresholds,
        pilot_hashing_baseline_path="hashing.json",
        pilot_production_baseline_path="prod.json",
        pilot_informational_suites=["stress.jsonl"],
        pilot_accepted_suites=["accepted.jsonl"],
        pilot_runner=fake_pilot_runner,
    )

    assert result.status == "passed"
    assert result.pilot_status == "passed"
    assert pilot_output.exists()
    assert pilot_calls[0]["thresholds"] == thresholds
    assert pilot_calls[0]["informational_suites"] == ["stress.jsonl"]
    assert pilot_calls[0]["accepted_suites"] == ["accepted.jsonl"]
    checks = {check["name"]: check for check in result.checks}
    assert checks["production_pilot"]["status"] == "passed"


def test_verify_pilot_does_not_run_when_smoke_fails(monkeypatch):
    _clear_provider_env(monkeypatch)
    pilot_calls = []
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return _Completed(1 if "production-provider" in cmd else 0)

    result = run_production_provider_verify(
        level="pilot",
        config_path="examples/config/production-provider-verification.yaml",
        env=_env(),
        runner=fake_run,
        ensure_bucket_step=lambda cfg, env: {"name": "s3_bucket", "status": "passed", "detail": {"action": "exists"}},
        pilot_runner=lambda **kwargs: pilot_calls.append(kwargs),  # type: ignore[arg-type]
    )

    assert result.status == "failed"
    assert result.smoke_exit_code == 1
    assert pilot_calls == []
    assert calls[-1][:4] == [sys.executable, "-m", "tagmemorag", "production-provider"]


def test_write_verify_report_json(monkeypatch, tmp_path):
    _clear_provider_env(monkeypatch)
    result = run_production_provider_verify(
        level="smoke",
        config_path="examples/config/production-provider-verification.yaml",
        env={},
        start_docker=False,
        ensure_bucket=False,
    )

    output = tmp_path / "verify.json"
    write_verify_report(result, output)

    body = json.loads(output.read_text(encoding="utf-8"))
    assert body["schema_version"] == "production_provider_verify.v1"
    assert body["status"] == "failed"
