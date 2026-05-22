from __future__ import annotations

from argparse import Namespace
import json

from tagmemorag.cli_feedback import run_feedback_command


def test_run_feedback_command_lists_rows(monkeypatch, tmp_path, capsys):
    config = tmp_path / "config.yaml"
    config.write_text("model:\n  name: hashing\n  dim: 64\n", encoding="utf-8")
    calls = {}

    class Row:
        def to_dict(self):
            return {"feedback_id": "fb-1"}

    def fake_list_feedback(kb_name, cfg, *, status, outcome, query, limit):
        calls["args"] = {
            "kb_name": kb_name,
            "status": status,
            "outcome": outcome,
            "query": query,
            "limit": limit,
            "model": cfg.model.name,
        }
        return [Row()]

    monkeypatch.setattr("tagmemorag.cli_feedback.list_feedback", fake_list_feedback)

    code = run_feedback_command(
        Namespace(
            feedback_command="list",
            config=str(config),
            kb="default",
            status="new",
            outcome=None,
            query="steam",
            limit=3,
        )
    )

    assert code == 0
    assert calls["args"] == {
        "kb_name": "default",
        "status": "new",
        "outcome": None,
        "query": "steam",
        "limit": 3,
        "model": "hashing",
    }
    assert json.loads(capsys.readouterr().out) == {"kb_name": "default", "feedback": [{"feedback_id": "fb-1"}]}


def test_run_feedback_command_unknown_subcommand_returns_one(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("model:\n  name: hashing\n  dim: 64\n", encoding="utf-8")

    code = run_feedback_command(Namespace(feedback_command="missing", config=str(config)))

    assert code == 1
