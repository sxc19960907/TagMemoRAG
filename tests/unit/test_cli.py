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
