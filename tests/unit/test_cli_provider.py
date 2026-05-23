from __future__ import annotations

from argparse import Namespace
import json

from tagmemorag.cli_provider import run_provider_command, run_production_provider_command


def test_run_provider_command_selects_all_by_default(monkeypatch, capsys):
    calls = {}

    class Report:
        status = "skipped"

        def to_dict(self):
            return {"schema_version": "provider_probe.v1", "status": self.status}

    def fake_run_provider_probe(config, *, selected, kb_name):
        calls["args"] = {"config": config, "selected": selected, "kb_name": kb_name}
        return Report()

    monkeypatch.setattr("tagmemorag.cli_provider.run_provider_probe", fake_run_provider_probe)

    code = run_provider_command(
        Namespace(
            provider_command="probe",
            config="config.yaml",
            kb="default",
            all=False,
            embedding=False,
            answer=False,
            reranker=False,
            qdrant=False,
            s3=False,
        )
    )

    assert code == 0
    assert calls["args"] == {"config": "config.yaml", "selected": ["all"], "kb_name": "default"}
    assert json.loads(capsys.readouterr().out)["status"] == "skipped"


def test_run_production_provider_command_smoke_exception_returns_two(monkeypatch, capsys):
    def fake_run_smoke(**kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("tagmemorag.cli_provider.run_production_provider_smoke", fake_run_smoke)

    code = run_production_provider_command(
        Namespace(
            production_provider_command="smoke",
            config="config.yaml",
            kb="default",
            manual=[],
            metadata=None,
            metadata_format="json",
            workdir=None,
            question="q",
            rebuild_mode="full",
            answer_top_k=6,
            answer_source_k=6,
            reset_qdrant_collection=False,
            output=None,
            format="json",
        )
    )

    assert code == 2
    assert "production-provider smoke error: RuntimeError: boom" in capsys.readouterr().err
