from __future__ import annotations

import json
import os
import time
from pathlib import Path

from fastapi.testclient import TestClient
import networkx as nx
import numpy as np

from tagmemorag import api, api_eval_report, api_eval_runs
from tagmemorag.auth.config_store import ConfigAuthStore
from tagmemorag.config import ApiKeyConfig, AuthConfig, ManualLibraryConfig, Settings, StorageConfig
from tagmemorag.state import AppState
from tagmemorag.types import GraphState


def _client(tmp_path, fake_embedder) -> TestClient:
    api_eval_runs.eval_run_registry.reset_for_tests()
    api.settings = Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "data")),
        manual_library=ManualLibraryConfig(root_dir=str(tmp_path / "manuals")),
        model={"provider": "hashing", "dim": 64},
    )
    api.embedder = fake_embedder
    api.app_state = AppState()
    return TestClient(api.app)


def _wait_for_eval_job(client: TestClient, job_id: str, timeout: float = 10.0) -> dict:
    deadline = time.time() + timeout
    body = {}
    while time.time() < deadline:
        response = client.get(f"/eval/runs/{job_id}")
        assert response.status_code == 200
        body = response.json()
        if body["status"] not in {"queued", "running"}:
            return body
        time.sleep(0.05)
    raise AssertionError(f"eval job did not finish: {body}")


def test_manual_library_admin_route_serves_shell(tmp_path, fake_embedder):
    client = _client(tmp_path, fake_embedder)

    response = client.get("/admin/manual-library?kb_name=ops")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    body = response.text
    assert "Manual Library" in body
    assert 'id="manual-rows"' in body
    assert 'id="suggest-upload-tags"' in body
    assert 'id="suggest-detail-tags"' in body
    assert 'id="bulk-preview-rows"' in body
    assert 'id="rebuild-mode"' in body
    assert 'id="dirty-summary"' in body
    assert 'id="diagnostics-cards"' in body
    assert 'id="verify-blobs"' in body
    assert 'id="queue-job-rows"' in body
    assert 'id="audit-rows"' in body
    assert 'id="manual-library-workbench"' in body
    assert 'href="/admin/rag-workbench?kb_name=ops"' in body
    assert 'id="manual-library-retrieval-quality"' in body
    assert 'href="/admin/retrieval-quality?kb_name=ops"' in body
    assert 'id="manual-library-people"' in body
    assert 'href="/admin/people?kb_name=ops"' in body
    assert 'id="manual-library-qa-link"' in body
    assert 'href="/qa?kb_name=ops"' in body
    assert 'id="open-tag-governance"' in body
    assert 'id="tag-stat-rows"' in body
    assert 'id="rewrite-preview-rows"' in body
    assert '"defaultKbName": "ops"' in body
    assert "/static/manual-library/manual_library.js" in body
    assert 'from "./i18n.js"' in client.get("/static/manual-library/manual_library.js").text


def test_manual_library_static_assets_are_served(tmp_path, fake_embedder):
    client = _client(tmp_path, fake_embedder)

    css = client.get("/static/manual-library/manual_library.css")
    js = client.get("/static/manual-library/manual_library.js")

    assert css.status_code == 200
    assert "workspace" in css.text
    assert "suggestion-chip" in css.text
    assert js.status_code == 200
    assert "manuals/validate" in js.text
    assert "manuals/tags/suggest" in js.text
    assert "manual-library/bulk/preview" in js.text
    assert "manual-library/bulk/import" in js.text
    assert "manual-library/tags/rewrite/preview" in js.text
    assert "manual-library/tags/policy" in js.text
    assert "manual-library/diagnostics" in js.text
    assert "manual-library/registry/audit" in js.text
    assert "manual-library/rebuild-jobs" in js.text
    assert "dirtyManualCount" in js.text
    assert "acceptAllSuggestions" in js.text
    assert "pollRebuildJob" in js.text
    assert "rebuildFailed" in js.text
    assert 'renderNextStep("rebuildFailed")' in js.text
    assert "The previous searchable KB remains active" in js.text
    assert "Retry rebuild" in js.text
    assert "bindSharedApiToken" in js.text
    assert "function updateLinks()" in js.text
    assert "/admin/rag-workbench" in js.text
    assert "/admin/rag-readiness" in js.text
    assert "/admin/retrieval-quality" in js.text
    assert "/admin/people" in js.text
    assert "/qa?kb_name=" in js.text


def test_admin_token_static_asset_is_served(tmp_path, fake_embedder):
    client = _client(tmp_path, fake_embedder)

    js = client.get("/static/manual-library/admin_token.js")

    assert js.status_code == 200
    assert "tagmemoragApiToken" in js.text
    assert "sessionStorage" in js.text
    assert "bindSharedApiToken" in js.text
    assert "authHeadersFromToken" in js.text
    assert "localStorage" not in js.text


def test_i18n_static_asset_is_served(tmp_path, fake_embedder):
    client = _client(tmp_path, fake_embedder)

    js = client.get("/static/manual-library/i18n.js")

    assert js.status_code == 200
    assert "tagmemoragUiLanguage" in js.text
    assert "initI18n" in js.text
    assert "currentLanguage" in js.text
    assert "English" in js.text
    assert "中文" in js.text


def test_retrieval_quality_admin_route_serves_shell(tmp_path, fake_embedder):
    client = _client(tmp_path, fake_embedder)

    response = client.get("/admin/retrieval-quality?kb_name=ops")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    body = response.text
    assert "Retrieval Quality" in body
    assert 'id="quality-summary-needs-review"' in body
    assert 'id="quality-summary-helpful"' in body
    assert 'id="quality-summary-not-helpful"' in body
    assert 'id="quality-summary-promotable"' in body
    assert 'id="quality-feedback-rows"' in body
    assert 'id="quality-review-guidance"' in body
    assert 'id="quality-triage-panel"' in body
    assert 'id="quality-mark-triaged"' in body
    assert 'id="quality-triage-preview"' in body
    assert 'id="quality-selected-evidence"' in body
    assert 'id="quality-expected-evidence"' in body
    assert 'id="quality-use-selected-expected"' in body
    assert 'id="quality-expected-source"' in body
    assert 'id="quality-expected-header"' in body
    assert 'id="quality-expected-text"' in body
    assert 'id="quality-expected-manual"' in body
    assert 'id="quality-promotion-summary"' in body
    assert 'id="quality-promotion-preview"' in body
    assert 'id="quality-workbench"' in body
    assert 'href="/admin/rag-workbench?kb_name=ops"' in body
    assert 'id="quality-readiness"' in body
    assert 'href="/admin/rag-readiness?kb_name=ops"' in body
    assert 'id="quality-manual-library"' in body
    assert 'href="/admin/manual-library?kb_name=ops"' in body
    assert 'id="quality-people"' in body
    assert 'href="/admin/people?kb_name=ops"' in body
    assert 'id="quality-qa"' in body
    assert 'href="/qa?kb_name=ops"' in body
    assert "/admin/eval-report" not in body
    assert 'id="quality-refresh"' in body
    assert '"defaultKbName": "ops"' in body
    assert "/static/manual-library/retrieval_quality.js" in body
    assert 'type="module" src="http://testserver/static/manual-library/retrieval_quality.js"' in body


def test_retrieval_quality_static_asset_is_served(tmp_path, fake_embedder):
    client = _client(tmp_path, fake_embedder)

    js = client.get("/static/manual-library/retrieval_quality.js")

    assert js.status_code == 200
    assert "/search/feedback" in js.text
    assert "/search/feedback/promote/preview" in js.text
    assert "quality-feedback-rows" in js.text
    assert "renderSummary" in js.text
    assert "quality-summary-needs-review" in js.text
    assert "sourceLabel" in js.text
    assert "reviewGuidance" in js.text
    assert "renderTriageDecision" in js.text
    assert "triageDecision" in js.text
    assert "quality-mark-triaged" in js.text
    assert "renderRefList" in js.text
    assert "renderPromotionSummary" in js.text
    assert "promotionQualityClass" in js.text
    assert "Weak matcher" in js.text
    assert "skipReasonLabel" in js.text
    assert "summary.output_path" in js.text
    assert "summary.suite_path" in js.text
    assert "summary.report_path" in js.text
    assert "summary.next_command" in js.text
    assert "summary.command_note" in js.text
    assert "reportViewerHref" in js.text
    assert "evalLauncherHref" in js.text
    assert "/admin/eval-report" in js.text
    assert "Open report" in js.text
    assert "Run in browser" in js.text
    assert "quality-promotion-summary" in js.text
    assert "setExpectedEditor" in js.text
    assert "expectedFromEditor" in js.text
    assert "useSelectedAsExpected" in js.text
    assert "selectedRefCards" in js.text
    assert "expectedRefCards" in js.text
    assert "bindSharedApiToken" in js.text
    assert "authHeadersFromToken" in js.text
    assert "initialFeedbackId" in js.text
    assert "requestedFeedbackId" in js.text
    assert "selectFeedbackFromUrl" in js.text
    assert "function updateLinks()" in js.text
    assert "/admin/rag-workbench" in js.text
    assert "/admin/rag-readiness" in js.text
    assert "/admin/manual-library" in js.text
    assert "/admin/people" in js.text
    assert "/qa?kb_name=" in js.text


def test_eval_report_admin_route_serves_shell(tmp_path, fake_embedder):
    client = _client(tmp_path, fake_embedder)

    response = client.get("/admin/eval-report?kb_name=ops&report_path=.tmp/report.json&suite_path=.tmp/suite.jsonl")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    body = response.text
    assert "Eval Report" in body
    assert 'id="eval-report-path"' in body
    assert 'value=".tmp/report.json"' in body
    assert 'id="eval-report-api-token"' in body
    assert 'id="eval-report-quality"' in body
    assert 'href="/admin/retrieval-quality?kb_name=ops"' in body
    assert 'id="eval-report-readiness"' in body
    assert 'href="/admin/rag-readiness?kb_name=ops"' in body
    assert 'id="eval-run-suite"' in body
    assert 'id="eval-run-start"' in body
    assert 'id="eval-run-status"' in body
    assert 'id="eval-suite-history"' in body
    assert 'id="eval-suite-history-count"' in body
    assert 'id="eval-report-recents"' in body
    assert 'id="eval-report-refresh"' in body
    assert 'id="eval-report-cases"' in body
    assert 'id="eval-report-config-snapshot"' in body
    assert '"defaultKbName": "ops"' in body
    assert '"defaultReportPath": ".tmp/report.json"' in body
    assert '"defaultSuitePath": ".tmp/suite.jsonl"' in body
    assert "/static/manual-library/eval_report.js" in body


def test_eval_report_static_asset_is_served(tmp_path, fake_embedder):
    client = _client(tmp_path, fake_embedder)

    js = client.get("/static/manual-library/eval_report.js")

    assert js.status_code == 200
    assert "/eval/report?path=" in js.text
    assert "/eval/reports?limit=20" in js.text
    assert "/eval/suites" in js.text
    assert "/eval/runs" in js.text
    assert "startEvalRun" in js.text
    assert "pollEvalRun" in js.text
    assert "eval-run-suite" in js.text
    assert "eval-run-status" in js.text
    assert "eval-suite-history" in js.text
    assert "renderSuiteHistory" in js.text
    assert "latest_report" in js.text
    assert "Open latest" in js.text
    assert "Load latest" in js.text
    assert "suiteMetaText" in js.text
    assert "defaultSuitePath" in js.text
    assert "Feedback draft" in js.text
    assert "Uses current KB" in js.text
    assert "eval-report-cases" in js.text
    assert "eval-report-recents" in js.text
    assert "loadRecentReports" in js.text
    assert "renderCaseCard" in js.text
    assert "renderGuidanceItem" in js.text
    assert "caseQaHref" in js.text
    assert "caseWorkbenchHref" in js.text
    assert "Ask in Q&A" in js.text
    assert "Open in Workbench" in js.text
    assert "Recommended Fix" in js.text
    assert "Expected Evidence" in js.text
    assert "Actual Top Results" in js.text
    assert "bindSharedApiToken" in js.text
    assert "authHeadersFromToken" in js.text
    assert "/admin/retrieval-quality" in js.text
    assert "/admin/rag-readiness" in js.text
    assert "/qa?kb_name=" in js.text


def test_rag_readiness_admin_route_serves_shell(tmp_path, fake_embedder):
    client = _client(tmp_path, fake_embedder)

    response = client.get("/admin/rag-readiness?kb_name=ops")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    body = response.text
    assert "RAG Readiness" in body
    assert 'id="readiness-kb-name"' in body
    assert 'value="ops"' in body
    assert 'id="readiness-status"' in body
    assert 'id="readiness-cards"' in body
    assert 'id="readiness-recommendations"' in body
    assert 'id="readiness-workbench"' in body
    assert 'href="/admin/rag-workbench?kb_name=ops"' in body
    assert 'id="readiness-qa"' in body
    assert 'href="/qa?kb_name=ops"' in body
    assert '"defaultKbName": "ops"' in body
    assert "/static/manual-library/rag_readiness.js" in body


def test_rag_readiness_static_asset_is_served(tmp_path, fake_embedder):
    client = _client(tmp_path, fake_embedder)

    js = client.get("/static/manual-library/rag_readiness.js")
    i18n = client.get("/static/manual-library/i18n.js")

    assert js.status_code == 200
    assert "/admin/rag-readiness/summary?kb_name=" in js.text
    assert "readiness-cards" in js.text
    assert "renderRecommendations" in js.text
    assert "primary_action" in js.text
    assert "action_label" in js.text
    assert "button-link compact" in js.text
    assert "/admin/rag-workbench" in js.text
    assert "/admin/manual-library" in js.text
    assert "/admin/eval-report" in js.text
    assert "/qa?kb_name=" in js.text
    assert i18n.status_code == 200
    assert "Start Q&A" in i18n.text
    assert "Review manuals" in i18n.text
    assert "Open latest report" in i18n.text


def test_rag_readiness_summary_reports_not_ready_without_loaded_kb(tmp_path, fake_embedder):
    client = _client(tmp_path, fake_embedder)
    api.app_state.mark_embedder_ready()

    response = client.get("/admin/rag-readiness/summary?kb_name=missing")

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "rag_readiness.v1"
    assert body["kb_name"] == "missing"
    assert body["status"] == "not_ready"
    assert body["primary_action"] == {
        "label": "Manual Library",
        "href": "/admin/manual-library?kb_name=missing",
        "kind": "warning",
    }
    cards = {item["id"]: item for item in body["cards"]}
    assert cards["kb"]["status"] == "not_ready"
    assert cards["qa"]["status"] == "not_ready"
    recommendations = {item["code"]: item for item in body["recommendations"]}
    assert recommendations["load_kb"]["href"] == "/admin/manual-library?kb_name=missing"
    assert recommendations["load_kb"]["action_label"] == "Manual Library"
    assert recommendations["try_qa_after_ready"]["href"] == "/qa?kb_name=missing"


def test_rag_readiness_summary_reports_review_when_eval_missing(tmp_path, fake_embedder, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = _client(tmp_path, fake_embedder)
    graph = nx.Graph()
    graph.add_node(1, text="ready")
    api.app_state.mark_embedder_ready()
    api.app_state.swap_kb("default", GraphState(graph=graph, vectors=np.zeros((1, 64), dtype=np.float32), build_id="build-ready", kb_name="default"))

    response = client.get("/admin/rag-readiness/summary?kb_name=default")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "needs_review"
    cards = {item["id"]: item for item in body["cards"]}
    assert cards["kb"]["status"] == "ready"
    assert cards["manuals"]["status"] == "ready"
    assert cards["eval"]["status"] == "needs_review"
    assert cards["qa"]["status"] == "ready"
    assert body["primary_action"] == {
        "label": "Open Eval Report",
        "href": "/admin/eval-report?kb_name=default",
        "kind": "warning",
    }
    recommendations = {item["code"]: item for item in body["recommendations"]}
    assert recommendations["run_eval"]["action_label"] == "Open Eval Report"
    assert recommendations["run_eval"]["href"] == "/admin/eval-report?kb_name=default"


def test_rag_readiness_summary_links_failed_latest_eval_report(tmp_path, fake_embedder, monkeypatch):
    monkeypatch.chdir(tmp_path)
    fixture = tmp_path / "tests" / "fixtures" / "eval" / "coffee.jsonl"
    fixture.parent.mkdir(parents=True)
    fixture.write_text("{}\n", encoding="utf-8")
    report_path = tmp_path / ".tmp" / "eval" / "browser-runs" / "coffee-report.json"
    report_path.parent.mkdir(parents=True)
    report_path.write_text(json.dumps(_eval_report_payload(str(fixture.resolve()), passed=False), ensure_ascii=False), encoding="utf-8")
    os.utime(report_path, (1_700_000_000, 1_700_000_000))
    client = _client(tmp_path, fake_embedder)
    graph = nx.Graph()
    graph.add_node(1, text="ready")
    api.app_state.mark_embedder_ready()
    api.app_state.swap_kb("default", GraphState(graph=graph, vectors=np.zeros((1, 64), dtype=np.float32), build_id="build-ready", kb_name="default"))

    response = client.get("/admin/rag-readiness/summary?kb_name=default")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "needs_review"
    recommendations = {item["code"]: item for item in body["recommendations"]}
    assert recommendations["review_eval"]["action_label"] == "Open latest report"
    assert recommendations["review_eval"]["href"].startswith("/admin/eval-report?kb_name=default&report_path=")
    assert ".tmp%2Feval%2Fbrowser-runs%2Fcoffee-report.json" in recommendations["review_eval"]["href"]
    assert body["primary_action"] == {
        "label": "Open latest report",
        "href": recommendations["review_eval"]["href"],
        "kind": "warning",
    }


def test_rag_readiness_summary_primary_action_starts_qa_when_ready(tmp_path, fake_embedder, monkeypatch):
    monkeypatch.chdir(tmp_path)
    fixture = tmp_path / "tests" / "fixtures" / "eval" / "coffee.jsonl"
    fixture.parent.mkdir(parents=True)
    fixture.write_text("{}\n", encoding="utf-8")
    report_path = tmp_path / ".tmp" / "eval" / "browser-runs" / "coffee-report.json"
    report_path.parent.mkdir(parents=True)
    report_path.write_text(json.dumps(_eval_report_payload(str(fixture.resolve()), passed=True), ensure_ascii=False), encoding="utf-8")
    client = _client(tmp_path, fake_embedder)
    graph = nx.Graph()
    graph.add_node(1, text="ready")
    api.app_state.mark_embedder_ready()
    api.app_state.swap_kb("default", GraphState(graph=graph, vectors=np.zeros((1, 64), dtype=np.float32), build_id="build-ready", kb_name="default"))

    response = client.get("/admin/rag-readiness/summary?kb_name=default")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["primary_action"] == {"label": "Start Q&A", "href": "/qa?kb_name=default", "kind": "primary"}
    assert body["recommendations"] == []


def test_eval_suites_api_lists_browser_safe_suites(tmp_path, fake_embedder, monkeypatch):
    monkeypatch.chdir(tmp_path)
    fixture = tmp_path / "tests" / "fixtures" / "eval" / "coffee.jsonl"
    fixture.parent.mkdir(parents=True)
    fixture.write_text("{}\n", encoding="utf-8")
    docs = tmp_path / "tests" / "fixtures"
    docs.mkdir(parents=True, exist_ok=True)
    client = _client(tmp_path, fake_embedder)

    response = client.get("/eval/suites")

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "eval_suites.v1"
    suites = {item["suite_id"]: item for item in body["suites"]}
    assert "coffee_smoke" in suites
    assert suites["coffee_smoke"]["suite_path"] == "tests/fixtures/eval/coffee.jsonl"
    assert suites["coffee_smoke"]["docs_path"] == "tests/fixtures"
    assert suites["coffee_smoke"]["kind"] == "fixture"
    assert suites["coffee_smoke"]["reuse_built_kb"] is False
    assert suites["coffee_smoke"]["thresholds"]["min_recall_at_k"] == 0.0
    assert suites["coffee_smoke"]["latest_report"] is None


def test_eval_suites_api_includes_latest_matching_report(tmp_path, fake_embedder, monkeypatch):
    monkeypatch.chdir(tmp_path)
    fixture = tmp_path / "tests" / "fixtures" / "eval" / "coffee.jsonl"
    fixture.parent.mkdir(parents=True)
    fixture.write_text("{}\n", encoding="utf-8")
    client = _client(tmp_path, fake_embedder)
    report_dir = tmp_path / ".tmp" / "eval" / "browser-runs"
    report_dir.mkdir(parents=True)
    older = report_dir / "older-report.json"
    older.write_text(json.dumps(_eval_report_payload("tests/fixtures/eval/coffee.jsonl", passed=False), ensure_ascii=False), encoding="utf-8")
    newer = report_dir / "newer-report.json"
    newer.write_text(json.dumps(_eval_report_payload(str((tmp_path / "tests/fixtures/eval/coffee.jsonl").resolve()), passed=True), ensure_ascii=False), encoding="utf-8")
    older_time = 1_700_000_000
    newer_time = 1_700_000_100
    os.utime(older, (older_time, older_time))
    os.utime(newer, (newer_time, newer_time))

    response = client.get("/eval/suites")

    assert response.status_code == 200
    suites = {item["suite_id"]: item for item in response.json()["suites"]}
    latest = suites["coffee_smoke"]["latest_report"]
    assert latest["relative_path"] == ".tmp/eval/browser-runs/newer-report.json"
    assert latest["passed"] is True
    assert latest["cases"] == 2
    assert latest["failed"] == 0


def test_eval_suites_api_matches_latest_report_beyond_recent_report_limit(tmp_path, fake_embedder, monkeypatch):
    monkeypatch.chdir(tmp_path)
    fixture = tmp_path / "tests" / "fixtures" / "eval" / "coffee.jsonl"
    fixture.parent.mkdir(parents=True)
    fixture.write_text("{}\n", encoding="utf-8")
    client = _client(tmp_path, fake_embedder)
    report_dir = tmp_path / ".tmp" / "eval"
    report_dir.mkdir(parents=True)
    matched = report_dir / "browser-runs" / "coffee-report.json"
    matched.parent.mkdir()
    matched.write_text(json.dumps(_eval_report_payload(str(fixture.resolve()), passed=True), ensure_ascii=False), encoding="utf-8")
    os.utime(matched, (1_700_000_000, 1_700_000_000))
    for index in range(api_eval_report.MAX_REPORT_LIST_LIMIT + 1):
        noise = report_dir / f"noise-{index}-report.json"
        noise.write_text(json.dumps(_eval_report_payload("tests/fixtures/eval/general_web.jsonl", passed=True), ensure_ascii=False), encoding="utf-8")
        newer = 1_800_000_000 + index
        os.utime(noise, (newer, newer))

    response = client.get("/eval/suites")

    assert response.status_code == 200
    suites = {item["suite_id"]: item for item in response.json()["suites"]}
    assert suites["coffee_smoke"]["latest_report"]["relative_path"] == ".tmp/eval/browser-runs/coffee-report.json"


def test_eval_suites_api_prefers_browser_run_report_over_newer_matching_report(tmp_path, fake_embedder, monkeypatch):
    monkeypatch.chdir(tmp_path)
    fixture = tmp_path / "tests" / "fixtures" / "eval" / "coffee.jsonl"
    fixture.parent.mkdir(parents=True)
    fixture.write_text("{}\n", encoding="utf-8")
    client = _client(tmp_path, fake_embedder)
    browser_report = tmp_path / ".tmp" / "eval" / "browser-runs" / "coffee-report.json"
    browser_report.parent.mkdir(parents=True)
    browser_report.write_text(json.dumps(_eval_report_payload(str(fixture.resolve()), passed=True), ensure_ascii=False), encoding="utf-8")
    other_report = tmp_path / ".tmp" / "production-provider-verification" / "eval-coffee.json"
    other_report.parent.mkdir(parents=True)
    other_report.write_text(json.dumps(_eval_report_payload(str(fixture.resolve()), passed=False), ensure_ascii=False), encoding="utf-8")
    os.utime(browser_report, (1_700_000_000, 1_700_000_000))
    os.utime(other_report, (1_800_000_000, 1_800_000_000))

    response = client.get("/eval/suites")

    assert response.status_code == 200
    suites = {item["suite_id"]: item for item in response.json()["suites"]}
    latest = suites["coffee_smoke"]["latest_report"]
    assert latest["relative_path"] == ".tmp/eval/browser-runs/coffee-report.json"
    assert latest["passed"] is True


def test_eval_suites_api_discovers_feedback_drafts(tmp_path, fake_embedder):
    client = _client(tmp_path, fake_embedder)
    draft = tmp_path / "eval_drafts" / "default" / "feedback-20260526.jsonl"
    draft.parent.mkdir(parents=True)
    draft.write_text(
        json.dumps(
            {
                "id": "feedback-fb-1",
                "query": "washer filter blocked",
                "kb_name": "default",
                "relevant": [{"source_file": "washer.md", "text_contains": ["filter"]}],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    malformed = draft.with_name("bad.jsonl")
    malformed.write_text("{bad\n", encoding="utf-8")

    response = client.get("/eval/suites")

    assert response.status_code == 200
    body = response.json()
    drafts = [item for item in body["suites"] if item["kind"] == "feedback_draft"]
    assert len(drafts) == 1
    suite = drafts[0]
    assert suite["suite_id"].startswith("feedback_draft:default_feedback_20260526:")
    assert suite["name"] == "Feedback draft: default/feedback-20260526"
    assert suite["suite_path"] == str(draft)
    assert suite["docs_path"] is None
    assert suite["reuse_built_kb"] is True
    assert suite["case_count"] == 1
    assert suite["thresholds"]["min_recall_at_k"] == 0.0


def test_eval_run_api_rejects_unknown_suite(tmp_path, fake_embedder):
    client = _client(tmp_path, fake_embedder)

    response = client.post("/eval/runs", json={"suite_id": "unknown"})

    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "INVALID_REQUEST"
    assert body["detail"]["suite_id"] == "unknown"


def test_eval_run_api_starts_job_and_writes_report(tmp_path, fake_embedder):
    client = _client(tmp_path, fake_embedder)

    started = client.post("/eval/runs", json={"suite_id": "coffee_smoke"})

    assert started.status_code == 202
    job_id = started.json()["job_id"]
    body = _wait_for_eval_job(client, job_id)
    assert body["status"] == "passed"
    assert body["summary"]["passed"] is True
    assert body["summary"]["cases"] == 7
    assert body["suite"]["suite_id"] == "coffee_smoke"
    report_path = Path(body["report_path"])
    assert report_path.exists()
    assert ".tmp/eval/browser-runs" in str(report_path)
    assert body["report_url"].startswith("/admin/eval-report?report_path=")


def test_eval_run_api_runs_discovered_feedback_draft_against_built_kb(tmp_path, fake_embedder):
    client = _client(tmp_path, fake_embedder)
    docs = tmp_path / "draft-docs"
    docs.mkdir()
    (docs / "washer.md").write_text("# Filter\nwasher filter blocked recovery steps\n", encoding="utf-8")
    build = client.post("/rebuild", json={"docs_dir": str(docs), "kb_name": "default"})
    assert build.status_code == 202
    task_id = build.json()["task_id"]
    deadline = time.time() + 10.0
    while time.time() < deadline:
        task = client.get(f"/rebuild/{task_id}").json()
        if task["status"] != "running":
            break
        time.sleep(0.05)
    assert task["status"] in {"done", "succeeded"}

    draft = tmp_path / "eval_drafts" / "default" / "feedback-20260526.jsonl"
    draft.parent.mkdir(parents=True)
    draft.write_text(
        json.dumps(
            {
                "id": "feedback-fb-1",
                "query": "washer filter blocked",
                "kb_name": "default",
                "relevant": [{"source_file": "washer.md", "text_contains": ["filter blocked"]}],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    suites = client.get("/eval/suites").json()["suites"]
    suite_id = next(item["suite_id"] for item in suites if item["kind"] == "feedback_draft")

    started = client.post("/eval/runs", json={"suite_id": suite_id})

    assert started.status_code == 202
    body = _wait_for_eval_job(client, started.json()["job_id"])
    assert body["status"] == "passed"
    assert body["suite"]["suite_id"] == suite_id
    assert body["suite"]["reuse_built_kb"] is True
    assert body["summary"]["cases"] == 1
    report = json.loads(Path(body["report_path"]).read_text(encoding="utf-8"))
    assert report["config_snapshot"]["reuse_built_kb"] is True
    assert report["cases"][0]["id"] == "feedback-fb-1"


def test_eval_report_list_api_discovers_recent_project_reports(tmp_path, fake_embedder, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = _client(tmp_path, fake_embedder)
    report_dir = tmp_path / ".tmp" / "eval"
    report_dir.mkdir(parents=True)
    report_path = report_dir / "browser-report.json"
    report_path.write_text(json.dumps(_eval_report_payload(), ensure_ascii=False), encoding="utf-8")
    malformed_path = report_dir / "broken-report.json"
    malformed_path.write_text("{bad", encoding="utf-8")
    ignored_path = tmp_path / "outside-report.json"
    ignored_path.write_text(json.dumps(_eval_report_payload(), ensure_ascii=False), encoding="utf-8")

    response = client.get("/eval/reports?limit=10")

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "eval_report_list.v1"
    paths = {item["relative_path"]: item for item in body["reports"]}
    assert ".tmp/eval/browser-report.json" in paths
    assert ".tmp/eval/broken-report.json" in paths
    assert "outside-report.json" not in paths
    assert paths[".tmp/eval/browser-report.json"]["valid"] is True
    assert paths[".tmp/eval/browser-report.json"]["suite"] == ".tmp/feedback.jsonl"
    assert paths[".tmp/eval/browser-report.json"]["cases"] == 2
    assert paths[".tmp/eval/browser-report.json"]["failed"] == 1
    assert paths[".tmp/eval/broken-report.json"]["valid"] is False
    assert paths[".tmp/eval/broken-report.json"]["error"] == "JSONDecodeError"


def test_eval_report_discovery_is_bounded_to_project_root(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    inside = tmp_path / ".tmp" / "eval" / "inside-report.json"
    inside.parent.mkdir(parents=True)
    inside.write_text(json.dumps(_eval_report_payload(), ensure_ascii=False), encoding="utf-8")
    outside = tmp_path.parent / f"{tmp_path.name}-outside-report.json"
    outside.write_text(json.dumps(_eval_report_payload(), ensure_ascii=False), encoding="utf-8")
    try:
        body = api_eval_report.list_eval_report_candidates(project_root=tmp_path, limit=10)
    finally:
        outside.unlink(missing_ok=True)

    paths = {item["path"] for item in body["reports"]}
    assert str(inside.resolve()) in paths
    assert str(outside.resolve()) not in paths


def test_eval_report_api_summarizes_valid_report(tmp_path, fake_embedder):
    client = _client(tmp_path, fake_embedder)
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(_eval_report_payload(), ensure_ascii=False), encoding="utf-8")

    response = client.get(f"/eval/report?path={report_path}")

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "eval_report_view.v1"
    assert body["report_path"] == str(report_path)
    assert body["summary"]["passed"] is False
    assert body["counts"]["total"] == 2
    assert body["counts"]["failed"] == 1
    assert body["counts"]["urgent"] == 1
    assert body["guidance_counts"]["threshold_failure"] == 1
    assert body["cases"][0]["id"] == "failed-case"
    assert body["cases"][0]["status"] == "urgent"
    assert body["cases"][0]["primary_issue"] == "threshold_failure"
    assert body["cases"][0]["guidance"][0]["title"] == "Threshold failure"
    assert body["cases"][0]["matched_expected_indexes"] == [0]
    assert body["cases"][0]["actual_top_k"][0]["source_file"] == "coffee.md"


def test_eval_report_api_guidance_classifies_common_failure_modes(tmp_path, fake_embedder):
    client = _client(tmp_path, fake_embedder)
    report_path = tmp_path / "guidance-report.json"
    report_path.write_text(json.dumps(_eval_report_guidance_payload(), ensure_ascii=False), encoding="utf-8")

    response = client.get(f"/eval/report?path={report_path}")

    assert response.status_code == 200
    body = response.json()
    cases = {case["id"]: case for case in body["cases"]}
    assert cases["no-match"]["primary_issue"] == "no_expected_match"
    assert [item["code"] for item in cases["partial"]["guidance"]] == ["partial_recall"]
    assert [item["code"] for item in cases["low-rank"]["guidance"]] == ["low_rank"]
    assert cases["negative"]["primary_issue"] == "negative_hit"
    assert cases["weak"]["primary_issue"] == "weak_matcher"
    assert body["guidance_counts"] == {
        "low_rank": 1,
        "negative_hit": 1,
        "no_expected_match": 1,
        "partial_recall": 1,
        "weak_matcher": 1,
    }


def test_eval_report_api_returns_structured_error_for_missing_file(tmp_path, fake_embedder):
    client = _client(tmp_path, fake_embedder)

    response = client.get(f"/eval/report?path={tmp_path / 'missing.json'}")

    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "INVALID_REQUEST"
    assert "not found" in body["message"]


def test_eval_report_api_returns_structured_error_for_malformed_report(tmp_path, fake_embedder):
    client = _client(tmp_path, fake_embedder)
    report_path = tmp_path / "bad.json"
    report_path.write_text('{"summary": {}}', encoding="utf-8")

    response = client.get(f"/eval/report?path={report_path}")

    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "INVALID_REQUEST"
    assert "cases list" in body["message"]


def test_rag_workbench_admin_route_serves_shell(tmp_path, fake_embedder):
    client = _client(tmp_path, fake_embedder)

    response = client.get("/admin/rag-workbench?kb_name=ops")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    body = response.text
    assert "RAG Workbench" in body
    assert 'id="workbench-question"' in body
    assert 'id="workbench-answer"' in body
    assert 'id="workbench-evidence"' in body
    assert 'id="workbench-results"' in body
    assert 'id="workbench-manual-library"' in body
    assert 'id="workbench-retrieval-quality"' in body
    assert 'id="workbench-eval-report"' in body
    assert 'id="workbench-readiness"' in body
    assert 'id="workbench-people"' in body
    assert 'id="workbench-qa"' in body
    assert 'href="/admin/eval-report?kb_name=ops"' in body
    assert 'href="/admin/rag-readiness?kb_name=ops"' in body
    assert 'href="/admin/people?kb_name=ops"' in body
    assert 'href="/qa?kb_name=ops"' in body
    assert '"defaultKbName": "ops"' in body
    assert "/static/manual-library/rag_workbench.js" in body
    assert 'aria-label="Workbench answer workspace"' in body
    assert 'aria-label="Workbench question"' in body


def test_root_route_redirects_to_rag_workbench(tmp_path, fake_embedder):
    client = _client(tmp_path, fake_embedder)

    response = client.get("/", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/rag-workbench?kb_name=default"


def test_rag_workbench_static_asset_is_served(tmp_path, fake_embedder):
    client = _client(tmp_path, fake_embedder)

    js = client.get("/static/manual-library/rag_workbench.js")

    assert js.status_code == 200
    assert "/answer" in js.text
    assert "include_retrieve" in js.text
    assert "workbench-answer" in js.text
    assert "workbench-evidence" in js.text
    assert "workbench-eval-report" in js.text
    assert "/admin/eval-report?kb_name=" in js.text
    assert "/admin/rag-readiness" in js.text
    assert "applyQuestionPrefill" in js.text
    assert "Question prefilled. Review it, then ask when ready." in js.text
    assert "/admin/people" in js.text
    assert "/qa?kb_name=" in js.text
    assert "bindSharedApiToken" in js.text
    assert "authHeadersFromToken" in js.text


def test_people_admin_route_serves_shell(tmp_path, fake_embedder):
    client = _client(tmp_path, fake_embedder)

    response = client.get("/admin/people?kb_name=ops")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    body = response.text
    assert "People & Access" in body
    assert 'class="people-boundary-guide"' in body
    assert "Use the smallest scope that fits the person." in body
    assert "Q&A users usually need search." in body
    assert 'id="people-key-rows"' in body
    assert 'id="people-detail-list"' in body
    assert 'id="people-lifecycle"' in body
    assert 'id="people-public-paths"' in body
    assert 'id="people-generate-form"' in body
    assert 'id="people-generation-result"' in body
    assert 'id="people-generate-command"' in body
    assert 'id="people-workbench"' in body
    assert 'href="/admin/rag-workbench?kb_name=ops"' in body
    assert 'id="people-readiness"' in body
    assert 'href="/admin/rag-readiness?kb_name=ops"' in body
    assert 'id="people-manual-library"' in body
    assert 'href="/admin/manual-library?kb_name=ops"' in body
    assert 'id="people-retrieval-quality"' in body
    assert 'href="/admin/retrieval-quality?kb_name=ops"' in body
    assert 'id="people-qa"' in body
    assert 'href="/qa?kb_name=ops"' in body
    assert '"defaultKbName": "ops"' in body
    assert "/static/manual-library/people_admin.js" in body


def test_people_admin_static_asset_is_served(tmp_path, fake_embedder):
    client = _client(tmp_path, fake_embedder)

    js = client.get("/static/manual-library/people_admin.js")

    assert js.status_code == 200
    assert "/admin/people/access-summary" in js.text
    assert "/admin/people/access-keys/generate" in js.text
    assert "people-key-rows" in js.text
    assert "generate-key" in js.text
    assert "Copy plaintext key" in js.text or "copyPlaintext" in js.text
    assert "Use as template" in js.text
    assert "Copy revoke config" in js.text
    assert "revoked" in js.text
    assert "safeLifecycleEntry" in js.text
    assert "peopleAccessError" in js.text
    assert "Paste an admin Bearer token" in js.text
    assert "lacks the {scope} scope" in js.text
    assert "bindSharedApiToken" in js.text
    assert "authHeadersFromToken" in js.text
    assert "function updateLinks()" in js.text
    assert "/admin/rag-workbench" in js.text
    assert "/admin/rag-readiness" in js.text
    assert "/admin/manual-library" in js.text
    assert "/admin/retrieval-quality" in js.text
    assert "/qa?kb_name=" in js.text


def test_people_access_summary_returns_safe_payload(tmp_path, fake_embedder):
    cfg = Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "data")),
        manual_library=ManualLibraryConfig(root_dir=str(tmp_path / "manuals")),
        auth=AuthConfig(
            enabled=False,
            keys=[
                ApiKeyConfig(
                    id="ops-admin",
                    label="Ops Admin",
                    hash="sha256:hidden-admin",
                    scopes=["admin"],
                    kb_allowlist=["*"],
                    rate_limit_per_minute=300,
                    created_at="2026-05-25T00:00:00+00:00",
                ),
                ApiKeyConfig(
                    id="support",
                    label="Support",
                    hash="sha256:hidden-support",
                    scopes=["search"],
                    kb_allowlist=["default"],
                    revoked=True,
                ),
            ],
        ),
        model={"dim": 64},
    )
    api.settings = cfg
    api.embedder = fake_embedder
    api.app_state = AppState()
    api.app_state.auth_store = ConfigAuthStore.from_config(cfg.auth)
    client = TestClient(api.app)

    response = client.get("/admin/people/access-summary")

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "people_access.v1"
    assert body["summary"] == {"total_keys": 2, "active_keys": 1, "revoked_keys": 1, "admin_keys": 1}
    assert body["keys"][0]["id"] == "ops-admin"
    assert body["keys"][0]["is_admin"] is True
    assert body["keys"][1]["status"] == "revoked"
    assert "hash" not in body["keys"][0]
    assert "hidden-admin" not in response.text


def test_people_access_summary_requires_admin_scope_when_auth_enabled(tmp_path, fake_embedder):
    admin_secret = "tmr_live_admin"
    search_secret = "tmr_live_search"
    cfg = Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "data")),
        manual_library=ManualLibraryConfig(root_dir=str(tmp_path / "manuals")),
        auth=AuthConfig(
            enabled=True,
            keys=[
                ApiKeyConfig(
                    id="admin",
                    hash=ConfigAuthStore.hash_plaintext(admin_secret),
                    scopes=["admin"],
                ),
                ApiKeyConfig(
                    id="search",
                    hash=ConfigAuthStore.hash_plaintext(search_secret),
                    scopes=["search"],
                ),
            ],
        ),
        model={"dim": 64},
    )
    api.settings = cfg
    api.embedder = fake_embedder
    api.app_state = AppState()
    api.app_state.auth_store = ConfigAuthStore.from_config(cfg.auth)
    client = TestClient(api.app)

    assert client.get("/admin/people/access-summary").status_code == 401
    denied = client.get("/admin/people/access-summary", headers={"Authorization": f"Bearer {search_secret}"})
    allowed = client.get("/admin/people/access-summary", headers={"Authorization": f"Bearer {admin_secret}"})

    assert denied.status_code == 403
    assert allowed.status_code == 200


def test_people_access_key_generation_returns_one_time_material(tmp_path, fake_embedder):
    client = _client(tmp_path, fake_embedder)

    response = client.post(
        "/admin/people/access-keys/generate",
        json={
            "id": "support-a",
            "label": "Support A",
            "scopes": ["search"],
            "kb_allowlist": ["ops"],
            "rate_limit_per_minute": 90,
            "prefix": "tmr_test_",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "people_access_key_generation.v1"
    assert body["plaintext_key"].startswith("tmr_test_")
    assert body["config_entry"]["id"] == "support-a"
    assert body["config_entry"]["label"] == "Support A"
    assert body["config_entry"]["scopes"] == ["search"]
    assert body["config_entry"]["kb_allowlist"] == ["ops"]
    assert body["config_entry"]["rate_limit_per_minute"] == 90
    assert body["config_entry"]["hash"].startswith("sha256:")
    assert body["plaintext_key"] not in body["config_json"]
    store = ConfigAuthStore.from_config(AuthConfig(keys=[ApiKeyConfig(**body["config_entry"])]))
    assert store.verify(body["plaintext_key"]).id == "support-a"


def test_people_access_key_generation_requires_admin_scope_when_auth_enabled(tmp_path, fake_embedder):
    admin_secret = "tmr_live_admin"
    search_secret = "tmr_live_search"
    cfg = Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "data")),
        manual_library=ManualLibraryConfig(root_dir=str(tmp_path / "manuals")),
        auth=AuthConfig(
            enabled=True,
            keys=[
                ApiKeyConfig(id="admin", hash=ConfigAuthStore.hash_plaintext(admin_secret), scopes=["admin"]),
                ApiKeyConfig(id="search", hash=ConfigAuthStore.hash_plaintext(search_secret), scopes=["search"]),
            ],
        ),
        model={"dim": 64},
    )
    api.settings = cfg
    api.embedder = fake_embedder
    api.app_state = AppState()
    api.app_state.auth_store = ConfigAuthStore.from_config(cfg.auth)
    client = TestClient(api.app)
    payload = {"id": "support-a", "scopes": ["search"], "kb_allowlist": ["ops"]}

    assert client.post("/admin/people/access-keys/generate", json=payload).status_code == 401
    denied = client.post(
        "/admin/people/access-keys/generate",
        json=payload,
        headers={"Authorization": f"Bearer {search_secret}"},
    )
    allowed = client.post(
        "/admin/people/access-keys/generate",
        json=payload,
        headers={"Authorization": f"Bearer {admin_secret}"},
    )

    assert denied.status_code == 403
    assert allowed.status_code == 200


def test_qa_page_route_serves_user_facing_shell(tmp_path, fake_embedder):
    client = _client(tmp_path, fake_embedder)

    response = client.get("/qa?kb_name=ops")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    body = response.text
    assert "Manual Q&A" in body
    assert 'class="qa-three-pane"' in body
    assert 'class="qa-left-rail"' in body
    assert 'class="qa-center-pane"' in body
    assert 'class="qa-right-rail"' in body
    assert 'id="qa-question"' in body
    assert 'id="qa-submit-new"' in body
    assert 'aria-label="Ask without conversation context"' in body
    assert 'aria-label="Ask question"' in body
    assert 'aria-label="Q&A question"' in body
    assert 'id="qa-answer"' in body
    assert 'class="qa-flow-guide"' in body
    assert 'id="qa-suggestions"' in body
    assert 'id="qa-copy-answer"' in body
    assert 'id="qa-followups"' in body
    assert 'id="qa-feedback"' in body
    assert 'id="qa-feedback-note"' in body
    assert 'id="qa-history"' in body
    assert 'id="qa-clear-history"' in body
    assert 'id="qa-sources"' in body
    assert 'id="qa-readiness-link"' in body
    assert 'class="qa-readiness-link"' in body
    assert 'href="/admin/rag-readiness?kb_name=ops"' in body
    assert 'id="qa-active-kb"' in body
    assert 'id="qa-kb-select"' in body
    assert 'aria-label="Knowledge base"' in body
    assert "Knowledge base" in body
    assert "Use KB" in body
    assert "Switching knowledge bases starts a separate Q&A session." in body
    assert "Check KB state before troubleshooting." in body
    assert "Product manual support" in body
    assert "Try asking" in body
    assert "Ask about a symptom, task, model, or error." in body
    assert "Answers will cite the manual passages used on the right." in body
    assert 'id="qa-kb-name"' not in body
    assert "workbench-evidence" not in body
    assert "workbench-results" not in body
    assert '"defaultKbName": "ops"' in body
    assert "/static/manual-library/qa_page.js" in body


def test_qa_page_static_asset_is_served(tmp_path, fake_embedder):
    client = _client(tmp_path, fake_embedder)

    js = client.get("/static/manual-library/qa_page.js")

    assert js.status_code == 200
    assert "/qa/answer" in js.text
    assert "include_retrieve" in js.text
    assert "conversation_context" in js.text
    assert "applyQuestionPrefill" in js.text
    assert "Question prefilled. Review it, then ask when ready." in js.text
    assert "conversationContextForRequest" in js.text
    assert "answerPreviewForContext" in js.text
    assert "shouldUseConversationContext" in js.text
    assert "requestNewQuestion" in js.text
    assert "renderContextNotice" in js.text
    assert "updateSubmitNewState" in js.text
    assert "qa-context-pill" in js.text
    assert "qa-context-notice" in js.text
    assert "sessionStorage" in js.text
    assert "bindSharedApiToken" in js.text
    assert "loadKnowledgeBases" in js.text
    assert 'fetch("/kb"' in js.text
    assert "handleKbSelection" in js.text
    assert "qaUrlForKb" in js.text
    assert "Switching knowledge bases starts a separate Q&A session." in js.text
    assert "authHeadersFromToken" in js.text
    assert "loadSessionMemory" in js.text
    assert "saveSessionMemory" in js.text
    assert "sanitizeAnswerBody" in js.text
    assert "clearSessionMemory" in js.text
    assert "renderAnswerText" in js.text
    assert "renderAnswerStep" in js.text
    assert "qa-answer-steps" in js.text
    assert "suggestedQuestions" in js.text
    assert "renderSuggestions" in js.text
    assert "copyAnswer" in js.text
    assert "navigator.clipboard.writeText" in js.text
    assert "loadingStages" in js.text
    assert "startLoadingStages" in js.text
    assert "renderLoadingState" in js.text
    assert "qa-progress-card" in js.text
    assert "Checking manuals" in js.text
    assert "Finding cited passages" in js.text
    assert "Retrieving manual evidence..." in js.text
    assert "renderRecoveryState" in js.text
    assert "qa-recovery-card" in js.text
    assert "Could not complete this answer" in js.text
    assert "Check readiness" in js.text
    assert "renderFollowups" in js.text
    assert "buildFollowupQuestions" in js.text
    assert "Suggested follow-ups" in js.text
    assert "These will continue from the current answer when useful." in js.text
    assert "handleFeedback" in js.text
    assert "/search/feedback" in js.text
    assert "/admin/rag-readiness" in js.text
    assert "feedbackPayloadForTurn" in js.text
    assert "selectedResultsForFeedback" in js.text
    assert "Feedback sent to Retrieval Quality." in js.text
    assert "renderFeedbackNote" in js.text
    assert "feedbackReviewHref" in js.text
    assert "Review this case" in js.text
    assert "/admin/retrieval-quality" in js.text
    assert "addConversationTurn" in js.text
    assert "updateConversationTurn" in js.text
    assert "restoreConversationTurn" in js.text
    assert "clearHistory" in js.text
    assert "qa-history-item" in js.text
    assert "bindSourceToggles" in js.text
    assert "qa-source-summary" in js.text
    assert "qa-source-toggle" in js.text
    assert "qa-source-placeholder" in js.text
    assert "Click a citation in the answer to focus a source" in js.text
    assert "qa-citation-chip" in js.text
    assert 'normalized === "no results"' in js.text
    assert "data-citation-target" in js.text
    assert "data-citation-id" in js.text
    assert "scrollIntoView" in js.text
    assert "top_k:" not in js.text
    assert "source_k:" not in js.text
    assert "qa-answer" in js.text
    assert "qa-kb-name" not in js.text
    assert "plan_id" in js.text
    assert "build_id" in js.text


def _eval_report_payload(suite: str = ".tmp/feedback.jsonl", *, passed: bool = False) -> dict:
    return {
        "suite": suite,
        "docs": None,
        "kb_names": ["default"],
        "top_k": 5,
        "thresholds": {"min_recall_at_k": 0.8, "min_mrr": 0.75, "min_hit_at_k": 0.8},
        "summary": {
            "cases": 2,
            "passed": passed,
            "precision_at_k": 0.4,
            "recall_at_k": 0.5,
            "mrr": 0.5,
            "hit_at_k": 0.5,
        },
        "cases": [
            {
                "id": "passed-case",
                "query": "how to descale",
                "kb_name": "default",
                "top_k": 5,
                "passed": True,
                "metrics": {"precision_at_k": 0.2, "recall_at_k": 1.0, "mrr": 1.0, "hit_at_k": 1.0},
                "thresholds": {},
                "expected": [{"source_file": "coffee.md", "text_contains": ["descale"]}],
                "actual_top_k": [{"rank": 1, "source_file": "coffee.md", "matched_expected_indexes": [0]}],
                "failures": [],
            },
            {
                "id": "failed-case",
                "query": "steam is weak",
                "kb_name": "default",
                "top_k": 5,
                "passed": passed,
                "metrics": {"precision_at_k": 0.0, "recall_at_k": 0.0, "mrr": 0.0, "hit_at_k": 0.0},
                "thresholds": {},
                "expected": [{"source_file": "coffee.md", "text_contains": ["steam"]}],
                "actual_top_k": [{"rank": 1, "source_file": "coffee.md", "matched_expected_indexes": [0]}],
                "failures": [] if passed else ["case recall_at_k 0.000000 < 0.800000"],
            },
        ],
        "config_snapshot": {"reuse_built_kb": True},
    }


def _eval_report_guidance_payload() -> dict:
    return {
        "suite": ".tmp/guidance.jsonl",
        "docs": None,
        "kb_names": ["default"],
        "top_k": 5,
        "thresholds": {},
        "summary": {"cases": 5, "passed": False, "precision_at_k": 0.0, "recall_at_k": 0.0, "mrr": 0.0, "hit_at_k": 0.0},
        "cases": [
            {
                "id": "no-match",
                "query": "missing evidence",
                "kb_name": "default",
                "top_k": 5,
                "passed": False,
                "metrics": {"precision_at_k": 0.0, "recall_at_k": 0.0, "mrr": 0.0, "hit_at_k": 0.0},
                "thresholds": {},
                "expected": [{"source_file": "missing.md", "text_contains": ["needle"]}],
                "actual_top_k": [{"rank": 1, "source_file": "other.md", "matched_expected_indexes": []}],
                "failures": [],
            },
            {
                "id": "partial",
                "query": "multi evidence",
                "kb_name": "default",
                "top_k": 5,
                "passed": True,
                "metrics": {"precision_at_k": 0.2, "recall_at_k": 0.5, "mrr": 1.0, "hit_at_k": 1.0},
                "thresholds": {},
                "expected": [{"source_file": "a.md"}, {"source_file": "b.md"}],
                "actual_top_k": [{"rank": 1, "source_file": "a.md", "matched_expected_indexes": [0]}],
                "failures": [],
            },
            {
                "id": "low-rank",
                "query": "ranked low",
                "kb_name": "default",
                "top_k": 5,
                "passed": True,
                "metrics": {"precision_at_k": 0.2, "recall_at_k": 1.0, "mrr": 0.333333, "hit_at_k": 1.0},
                "thresholds": {},
                "expected": [{"source_file": "ranked.md"}],
                "actual_top_k": [
                    {"rank": 1, "source_file": "other.md", "matched_expected_indexes": []},
                    {"rank": 3, "source_file": "ranked.md", "matched_expected_indexes": [0]},
                ],
                "failures": [],
            },
            {
                "id": "negative",
                "query": "wrong domain",
                "kb_name": "default",
                "top_k": 5,
                "passed": False,
                "metrics": {"precision_at_k": 0.0, "recall_at_k": 1.0, "mrr": 1.0, "hit_at_k": 1.0},
                "thresholds": {},
                "expected": [{"source_file": "right.md"}],
                "actual_top_k": [{"rank": 1, "source_file": "right.md", "matched_expected_indexes": [0]}],
                "failures": [],
                "negative_hits": [{"rank": 2, "source_file": "wrong.md"}],
            },
            {
                "id": "weak",
                "query": "weak matcher",
                "kb_name": "default",
                "top_k": 5,
                "passed": False,
                "metrics": {"precision_at_k": 0.0, "recall_at_k": 0.0, "mrr": 0.0, "hit_at_k": 0.0},
                "thresholds": {},
                "expected": [{}],
                "actual_top_k": [],
                "failures": [],
            },
        ],
        "config_snapshot": {"reuse_built_kb": True},
    }
