from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import diag_mixed_domain_eval as diag  # noqa: E402
from tagmemorag.eval.dataset import EvalSuiteError  # noqa: E402


def test_run_diagnostic_passes_mixed_local_docs_with_negatives(tmp_path: Path):
    docs = tmp_path / "docs"
    (docs / "washer").mkdir(parents=True)
    (docs / "public_web").mkdir()
    (docs / "washer" / "manual.md").write_text(
        "# W6564 Drain Pump\n"
        "The W6564 washer drain motor sits behind the drain pump cover.\n",
        encoding="utf-8",
    )
    (docs / "washer" / "manual.metadata.json").write_text(
        json.dumps(
            {
                "manual_id": "w6564-local",
                "title": "W6564 Manual",
                "source_file": "washer/manual.md",
                "product_category": "washer",
                "product_name": "W6564",
                "product_model": "W6564",
                "language": "en",
                "tags": ["washer"],
            }
        ),
        encoding="utf-8",
    )
    (docs / "public_web" / "github.md").write_text(
        "# GitHub Hello World\n"
        "A repository is a folder that contains related items.\n"
        "README files are written in Markdown.\n",
        encoding="utf-8",
    )
    (docs / "public_web" / "github.metadata.json").write_text(
        json.dumps(
            {
                "manual_id": "github-local",
                "title": "GitHub Hello World",
                "source_file": "public_web/github.md",
                "domain": "software_docs",
                "doc_type": "documentation",
                "product_category": "software_docs",
                "product_name": "",
                "product_model": "",
                "language": "en",
                "tags": ["software-docs"],
            }
        ),
        encoding="utf-8",
    )
    suite = tmp_path / "mixed.jsonl"
    suite.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "id": "manual",
                        "kb_name": "mixed_knowledge",
                        "query": "W6564 washer drain motor pump cover",
                        "relevant": [
                            {
                                "source_file": "washer/manual.md",
                                "text_contains": ["drain motor"],
                                "metadata": {"product_category": "washer"},
                            }
                        ],
                        "negatives": [{"metadata": {"product_category": "software_docs"}}],
                        "top_k_override": 1,
                    }
                ),
                json.dumps(
                    {
                        "id": "docs",
                        "kb_name": "mixed_knowledge",
                        "query": "GitHub repository README Markdown folder",
                        "relevant": [
                            {
                                "source_file": "public_web/github.md",
                                "text_contains": ["repository is a folder"],
                                "metadata": {"domain": "software_docs"},
                            }
                        ],
                        "negatives": [{"metadata": {"product_category": "washer"}}],
                        "top_k_override": 1,
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    report = diag.run_diagnostic(
        suite_path=suite,
        docs_path=docs,
        config_path=REPO_ROOT / "examples" / "config" / "local-hashing-npz.yaml",
        kb_name="mixed_knowledge",
        top_k=2,
        eval_data_dir=tmp_path / "data",
    )

    assert report["schema_version"] == "mixed_domain_eval.v1"
    assert report["summary"]["passed"] is True
    assert report["failed_cases"] == []
    assert {case["id"] for case in report["cases"]} == {"manual", "docs"}
    assert all(not case.get("negative_hits") for case in report["cases"])


def test_stage_default_docs_copies_manuals_and_public_web_docs(tmp_path: Path):
    manuals = tmp_path / "manuals"
    public = tmp_path / "public"
    (manuals / "washer").mkdir(parents=True)
    (public / "public_web").mkdir(parents=True)
    (manuals / "washer" / "m.pdf").write_bytes(b"%PDF-1.4\n")
    (manuals / "washer" / "m.metadata.json").write_text("{}", encoding="utf-8")
    (public / "public_web" / "doc.md").write_text("# Doc\n", encoding="utf-8")
    (public / "public_web" / "doc.metadata.json").write_text("{}", encoding="utf-8")

    staged = diag.stage_default_docs(destination=tmp_path / "staged", manual_docs=manuals, public_web_docs=public)

    assert (staged / "washer" / "m.pdf").exists()
    assert (staged / "washer" / "m.metadata.json").exists()
    assert (staged / "public_web" / "doc.md").exists()
    assert (staged / "public_web" / "doc.metadata.json").exists()


def test_run_diagnostic_rejects_missing_docs(tmp_path: Path):
    with pytest.raises(EvalSuiteError, match="docs path does not exist"):
        diag.run_diagnostic(
            suite_path=REPO_ROOT / "tests" / "fixtures" / "eval" / "mixed_knowledge.jsonl",
            docs_path=tmp_path / "missing",
            config_path=REPO_ROOT / "examples" / "config" / "local-hashing-npz.yaml",
        )
