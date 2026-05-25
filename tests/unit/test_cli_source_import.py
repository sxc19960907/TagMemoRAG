from __future__ import annotations

from argparse import Namespace
import json

from tagmemorag.cli_source_import import run_knowledge_command, run_manualslib_command
from tagmemorag.manualslib_opencli_import import ManualslibOpenCLIError


def test_run_knowledge_command_value_error_returns_failure_json(monkeypatch, capsys):
    def fake_import_public_web(*args, **kwargs):
        raise ValueError("at least one url is required")

    monkeypatch.setattr("tagmemorag.cli_source_import.import_public_web", fake_import_public_web)

    code = run_knowledge_command(
        Namespace(
            knowledge_command="sample-web",
            url=[],
            output_dir=None,
            kb="default",
            domain="public_web",
            doc_type="web_page",
            tag=[],
            preview=False,
            timeout_seconds=20.0,
        )
    )

    assert code == 2
    body = json.loads(capsys.readouterr().err)
    assert body == {
        "schema_version": "public_web_import.v1",
        "status": "failed",
        "error": {"message": "at least one url is required"},
    }


def test_run_manualslib_command_opencli_error_returns_serialized_error(monkeypatch, capsys):
    def fake_import_from_opencli(**kwargs):
        raise ManualslibOpenCLIError("opencli returned exit code 66", command=["opencli"], stderr="missing")

    monkeypatch.setattr("tagmemorag.cli_source_import.import_from_opencli", fake_import_from_opencli)

    code = run_manualslib_command(
        Namespace(
            manualslib_command="import-opencli",
            brand="hisense",
            category=None,
            limit=20,
            output_dir=None,
            preview=True,
            max_pages=None,
            timeout_seconds=20.0,
        )
    )

    assert code == 2
    body = json.loads(capsys.readouterr().err)
    assert body["schema_version"] == "manualslib_opencli_import.v1"
    assert body["status"] == "failed"
    assert body["error"]["stderr"] == "missing"
