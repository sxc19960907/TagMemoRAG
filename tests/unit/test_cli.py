from __future__ import annotations

import json
import subprocess
import sys

from tagmemorag import cli


def test_cli_build_and_search_with_hashing_embedder(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "manual.md").write_text(
        "# 操作\n蒸汽功能可以打奶泡。\n# 清洗\n喷嘴堵塞需要清洗。\n# 故障\nE05 表示蒸汽异常。\n",
        encoding="utf-8",
    )
    config = tmp_path / "config.yaml"
    data_dir = tmp_path / "data"
    config.write_text(
        f"""
model:
  name: hashing
  dim: 64
storage:
  data_dir: {data_dir}
""",
        encoding="utf-8",
    )
    build = subprocess.run(
        [sys.executable, "-m", "tagmemorag", "build", "--docs", str(docs), "--config", str(config)],
        check=True,
        text=True,
        capture_output=True,
    )
    assert json.loads(build.stdout)["chunks"] == 3

    search = subprocess.run(
        [sys.executable, "-m", "tagmemorag", "search", "蒸汽很小", "--config", str(config), "--top-k", "3"],
        check=True,
        text=True,
        capture_output=True,
    )
    body = json.loads(search.stdout)
    assert body["results"]
    assert any("蒸汽" in result["text"] or "E05" in result["text"] for result in body["results"])


def test_cli_search_filters_manual_metadata(tmp_path):
    docs = tmp_path / "docs"
    (docs / "fridge").mkdir(parents=True)
    (docs / "coffee").mkdir()
    (docs / "fridge" / "manual.md").write_text("# 温度\n冷藏室温度可以调节。\n", encoding="utf-8")
    (docs / "fridge" / "manual.metadata.json").write_text(
        '{"manual_id":"fridge-manual","title":"Fridge Manual","source_file":"fridge/manual.md","product_category":"fridge","product_model":"NRK6192","language":"zh-CN","tags":["temperature-setting"]}',
        encoding="utf-8",
    )
    (docs / "coffee" / "manual.md").write_text("# 温度\n咖啡温度和蒸汽设置。\n", encoding="utf-8")
    (docs / "coffee" / "manual.metadata.json").write_text(
        '{"manual_id":"coffee-manual","title":"Coffee Manual","source_file":"coffee/manual.md","product_category":"coffee","product_model":"CM1","language":"zh-CN","tags":["maintenance"]}',
        encoding="utf-8",
    )
    config = tmp_path / "config.yaml"
    data_dir = tmp_path / "data"
    config.write_text(
        f"""
model:
  name: hashing
  dim: 64
storage:
  data_dir: {data_dir}
""",
        encoding="utf-8",
    )

    subprocess.run(
        [sys.executable, "-m", "tagmemorag", "build", "--docs", str(docs), "--config", str(config)],
        check=True,
        text=True,
        capture_output=True,
    )
    search = subprocess.run(
        [
            sys.executable,
            "-m",
            "tagmemorag",
            "search",
            "温度",
            "--config",
            str(config),
            "--category",
            "fridge",
            "--model",
            "NRK6192",
            "--tag",
            "Temperature Setting",
        ],
        check=True,
        text=True,
        capture_output=True,
    )

    body = json.loads(search.stdout)
    assert body["results"]
    assert {result["manual_id"] for result in body["results"]} == {"fridge-manual"}


def test_cli_serve_uses_config_host_port(tmp_path, monkeypatch):
    config = tmp_path / "config.yaml"
    config.write_text(
        """
model:
  name: hashing
server:
  host: 127.0.0.9
  port: 9000
""",
        encoding="utf-8",
    )
    called = {}

    def fake_run(app, **kwargs):
        called["app"] = app
        called["kwargs"] = kwargs

    monkeypatch.setattr(cli.uvicorn, "run", fake_run)

    assert cli.main(["serve", "--config", str(config)]) == 0
    assert called["kwargs"]["host"] == "127.0.0.9"
    assert called["kwargs"]["port"] == 9000


def test_cli_auth_generate_key_outputs_hash_and_plaintext(capsys):
    assert cli.main(["auth", "generate-key", "--id", "cs-test", "--scopes", "search,rebuild", "--kb", "default", "--rate", "10"]) == 0

    out = capsys.readouterr().out
    assert '"id": "cs-test"' in out
    assert '"hash": "sha256:' in out
    assert '"scopes": [' in out
    assert "tmr_live_" in out


def test_cli_manual_bulk_preview_and_import(tmp_path, capsys):
    config = tmp_path / "config.yaml"
    config.write_text(
        f"""
model:
  name: hashing
  dim: 64
storage:
  data_dir: {tmp_path / "data"}
manual_library:
  root_dir: {tmp_path / "manuals"}
""",
        encoding="utf-8",
    )
    metadata = tmp_path / "manuals.csv"
    metadata.write_text(
        "manual_id,title,source_file,product_category,language,tags\n"
        "cm1,CM1 Manual,coffee/cm1.md,coffee,zh-CN,maintenance\n",
        encoding="utf-8",
    )
    source = tmp_path / "cm1.md"
    source.write_text("# Use\nClean weekly.\n", encoding="utf-8")

    assert cli.main(["manual-bulk", "preview", "--config", str(config), "--metadata", str(metadata), "--file", str(source)]) == 0
    preview = json.loads(capsys.readouterr().out)
    assert preview["summary"]["valid_count"] == 1
    assert preview["rows"][0]["action"] == "create"

    assert (
        cli.main(
            [
                "manual-bulk",
                "import",
                "--config",
                str(config),
                "--metadata",
                str(metadata),
                "--file",
                str(source),
                "--selected-row",
                "2",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["imported_count"] == 1
    assert (tmp_path / "manuals" / "default" / "coffee" / "cm1.md").exists()

    assert cli.main(["manual-library", "dirty", "--config", str(config)]) == 0
    dirty = json.loads(capsys.readouterr().out)
    assert dirty["dirty_manuals"][0]["manual_id"] == "cm1"

    assert cli.main(["manual-library", "dirty", "--config", str(config), "--format", "csv"]) == 0
    assert "manual_id,source_file,operation" in capsys.readouterr().out


def test_cli_feedback_workflow(tmp_path, capsys):
    config = tmp_path / "config.yaml"
    config.write_text(
        f"""
model:
  name: hashing
  dim: 64
storage:
  data_dir: {tmp_path / "data"}
""",
        encoding="utf-8",
    )
    payload_path = tmp_path / "feedback.json"
    payload_path.write_text(
        json.dumps(
            {
                "feedback_id": "fb-cli",
                "trace_id": "trace-1",
                "search_id": "search-1",
                "build_id": "build-1",
                "query": "E05 蒸汽异常怎么处理",
                "outcome": "missing_result",
                "expected": [{"source_file": "coffee.md", "header": "E05", "metadata": {"manual_id": "cm1"}}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    assert cli.main(["feedback", "submit", "--config", str(config), "--json", str(payload_path)]) == 0
    created = json.loads(capsys.readouterr().out)
    assert created["feedback"]["feedback_id"] == "fb-cli"

    assert cli.main(["feedback", "list", "--config", str(config), "--status", "new"]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert [row["feedback_id"] for row in listed["feedback"]] == ["fb-cli"]

    assert cli.main(["feedback", "review", "--config", str(config), "--feedback-id", "fb-cli", "--status", "triaged"]) == 0
    reviewed = json.loads(capsys.readouterr().out)
    assert reviewed["feedback"]["status"] == "triaged"

    output = tmp_path / "eval_drafts" / "default" / "feedback.jsonl"
    assert cli.main(["feedback", "promote-preview", "--config", str(config), "--feedback-id", "fb-cli", "--output", str(output)]) == 0
    preview = json.loads(capsys.readouterr().out)
    assert preview["cases"][0]["id"] == "feedback-fb-cli"
