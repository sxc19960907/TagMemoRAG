from __future__ import annotations

import json

from tagmemorag import cli
from tagmemorag.production_provider_verify import ProductionProviderVerifyReport


def test_cli_production_provider_verify_forwards_options(monkeypatch, capsys):
    calls = []

    def fake_verify(**kwargs):
        calls.append(kwargs)
        return ProductionProviderVerifyReport(
            status="passed",
            level=kwargs["level"],
            config_path=str(kwargs["config_path"]),
            output_path=str(kwargs["output_path"]),
            checks=[],
        )

    monkeypatch.setattr(cli, "run_production_provider_verify", fake_verify)

    exit_code = cli.main(
        [
            "production-provider",
            "verify",
            "--level",
            "pilot",
            "--config",
            "config.yaml",
            "--manual",
            "a.pdf",
            "--skip-docker",
            "--skip-bucket",
            "--no-reset-qdrant",
            "--pilot-suite",
            "suite.jsonl",
            "--pilot-docs",
            "docs",
            "--pilot-informational-suites",
            "stress.jsonl",
            "--pilot-accepted-suites",
            "accepted.jsonl",
        ]
    )

    assert exit_code == 0
    body = json.loads(capsys.readouterr().out)
    assert body["level"] == "pilot"
    assert calls[0]["level"] == "pilot"
    assert calls[0]["manual_paths"] == ["a.pdf"]
    assert calls[0]["start_docker"] is False
    assert calls[0]["ensure_bucket"] is False
    assert calls[0]["reset_qdrant"] is False
    assert calls[0]["pilot_suite_path"] == "suite.jsonl"
    assert calls[0]["pilot_docs_path"] == "docs"
    assert calls[0]["pilot_informational_suites"] == ["stress.jsonl"]
    assert calls[0]["pilot_accepted_suites"] == ["accepted.jsonl"]


def test_cli_production_provider_verify_writes_summary(monkeypatch, tmp_path, capsys):
    def fake_verify(**kwargs):
        return ProductionProviderVerifyReport(
            status="passed",
            level=kwargs["level"],
            config_path=str(kwargs["config_path"]),
            output_path=str(kwargs["output_path"]),
            checks=[],
        )

    monkeypatch.setattr(cli, "run_production_provider_verify", fake_verify)

    verify_output = tmp_path / "verify.json"
    exit_code = cli.main(
        [
            "production-provider",
            "verify",
            "--verify-output",
            str(verify_output),
        ]
    )

    assert exit_code == 0
    assert capsys.readouterr().out == ""
    body = json.loads(verify_output.read_text(encoding="utf-8"))
    assert body["schema_version"] == "production_provider_verify.v1"
