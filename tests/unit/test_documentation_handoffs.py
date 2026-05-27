from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_trial_report_ci_handoff_documents_retention_and_ci_boundary():
    handoff = (ROOT / "docs" / "trial-report-ci-handoff.md").read_text(encoding="utf-8")
    final_review = (ROOT / "docs" / "trial-readiness-final-review-2026-05-27.md").read_text(encoding="utf-8")
    quality = (ROOT / "docs" / "rag-quality-gates.md").read_text(encoding="utf-8")
    trial = (ROOT / "docs" / "trial-operator-handoff-2026-05-27.md").read_text(encoding="utf-8")
    quick_start = (ROOT / "docs" / "browser-rag-quick-start.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "--include-browser-qa" in handoff
    assert "--browser-qa-full" in handoff
    assert ".tmp/trial-ops-pilot/report.json" in handoff
    assert "uv run pytest tests/unit tests/e2e --ignore=tests/e2e/test_perf.py" in handoff
    assert "uv run python scripts/run_eval_ci.py" in handoff
    assert "Default CI does not run `readiness browser-qa`" in handoff
    assert "GitHub CI is checked after push" in handoff

    assert "trial-report-ci-handoff.md" in quality
    assert "trial-report-ci-handoff.md" in trial
    assert "trial-readiness-final-review-2026-05-27.md" in trial
    assert "first-run upload guidance" in trial
    assert "Start by adding a manual" in trial
    assert "Open Manual Library" in trial
    assert "7630ba7" not in trial
    assert "Start From Ask Q&A" in quick_start
    assert "Manual is indexed. Ask a question about it below." in quick_start
    assert "Check readiness" in quick_start
    assert "docs/trial-report-ci-handoff.md" in readme
    assert "browser QA readiness: `passed`" in final_review
    assert "QA first-run upload guidance" in final_review
    assert "GitHub Actions as authoritative" in final_review


def test_real_pdf_document_intake_report_records_current_boundary():
    report = (ROOT / "docs" / "real-pdf-document-intake-test-2026-05-27.md").read_text(encoding="utf-8")

    assert "Real product-manual PDF intake is locally usable" in report
    assert "recall@k" in report
    assert "0.966667" in report
    assert "limited `.docx` OpenXML text extractor" in report
    assert "Manual Library and Q&A uploads accept `.docx`" in report
    assert "OpenXML-to-Markdown extractor" in report
    assert "parser warning summarization" in report


def test_docx_direct_intake_is_documented_for_browser_users():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    quick_start = (ROOT / "docs" / "browser-rag-quick-start.md").read_text(encoding="utf-8")
    trial = (ROOT / "docs" / "trial-operator-handoff-2026-05-27.md").read_text(encoding="utf-8")

    assert "uploads also accept `.docx`" in readme
    assert "readable `.docx` manual" in quick_start
    assert "readable `.docx` files" in trial
