from __future__ import annotations

import json
import subprocess
import sys


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
