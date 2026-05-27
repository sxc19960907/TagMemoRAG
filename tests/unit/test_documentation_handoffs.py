from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_trial_report_ci_handoff_documents_retention_and_ci_boundary():
    handoff = (ROOT / "docs" / "trial-report-ci-handoff.md").read_text(encoding="utf-8")
    quality = (ROOT / "docs" / "rag-quality-gates.md").read_text(encoding="utf-8")
    trial = (ROOT / "docs" / "trial-operator-handoff-2026-05-27.md").read_text(encoding="utf-8")
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
    assert "docs/trial-report-ci-handoff.md" in readme
