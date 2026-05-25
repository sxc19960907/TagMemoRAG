from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import diag_general_web_answer_eval as diag  # noqa: E402


def test_run_diagnostic_generates_grounded_answers_from_local_docs(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "web.md").write_text(
        "# GitHub Hello World\n"
        "A repository is a folder that contains related items.\n\n"
        "README files are written in Markdown.\n",
        encoding="utf-8",
    )
    suite = tmp_path / "suite.jsonl"
    suite.write_text(
        '{"id":"repo-readme","kb_name":"general_web",'
        '"query":"GitHub repository README Markdown folder",'
        '"relevant":[{"source_file":"web.md","text_contains":["repository is a folder"]}],'
        '"top_k_override":3}\n',
        encoding="utf-8",
    )

    report = diag.run_diagnostic(
        suite_path=suite,
        docs_path=docs,
        config_path=REPO_ROOT / "examples" / "config" / "local-hashing-npz.yaml",
        kb_name="general_web",
        top_k=3,
        source_k=3,
    )

    assert report["summary"] == {"cases": 1, "failed": 0, "passed": True}
    case = report["cases"][0]
    assert case["id"] == "repo-readme"
    assert case["passed"] is True
    assert case["retrieve"]["answerable"] is True
    assert "repository is a folder" in case["answer"]["text"]
    assert case["answer_quality"]["observed"]["grounded"] is True
    assert case["answer_quality"]["observed"]["citation_supported"] is True
