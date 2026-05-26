from __future__ import annotations

from fastapi.testclient import TestClient

from tagmemorag import api
from tagmemorag.auth.config_store import ConfigAuthStore
from tagmemorag.config import ApiKeyConfig, AuthConfig, ManualLibraryConfig, Settings, StorageConfig
from tagmemorag.state import AppState


def _client(tmp_path, fake_embedder) -> TestClient:
    api.settings = Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "data")),
        manual_library=ManualLibraryConfig(root_dir=str(tmp_path / "manuals")),
        model={"dim": 64},
    )
    api.embedder = fake_embedder
    api.app_state = AppState()
    return TestClient(api.app)


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
    assert "bindSharedApiToken" in js.text
    assert "function updateLinks()" in js.text
    assert "/admin/rag-workbench" in js.text
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
    assert 'id="quality-selected-evidence"' in body
    assert 'id="quality-expected-evidence"' in body
    assert 'id="quality-promotion-summary"' in body
    assert 'id="quality-promotion-preview"' in body
    assert 'id="quality-workbench"' in body
    assert 'href="/admin/rag-workbench?kb_name=ops"' in body
    assert 'id="quality-manual-library"' in body
    assert 'href="/admin/manual-library?kb_name=ops"' in body
    assert 'id="quality-people"' in body
    assert 'href="/admin/people?kb_name=ops"' in body
    assert 'id="quality-qa"' in body
    assert 'href="/qa?kb_name=ops"' in body
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
    assert "renderRefList" in js.text
    assert "renderPromotionSummary" in js.text
    assert "skipReasonLabel" in js.text
    assert "quality-promotion-summary" in js.text
    assert "selectedRefCards" in js.text
    assert "expectedRefCards" in js.text
    assert "bindSharedApiToken" in js.text
    assert "authHeadersFromToken" in js.text
    assert "function updateLinks()" in js.text
    assert "/admin/rag-workbench" in js.text
    assert "/admin/manual-library" in js.text
    assert "/admin/people" in js.text
    assert "/qa?kb_name=" in js.text


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
    assert 'id="workbench-people"' in body
    assert 'id="workbench-qa"' in body
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
    assert 'id="people-key-rows"' in body
    assert 'id="people-detail-list"' in body
    assert 'id="people-lifecycle"' in body
    assert 'id="people-public-paths"' in body
    assert 'id="people-generate-form"' in body
    assert 'id="people-generation-result"' in body
    assert 'id="people-generate-command"' in body
    assert 'id="people-workbench"' in body
    assert 'href="/admin/rag-workbench?kb_name=ops"' in body
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
    assert "bindSharedApiToken" in js.text
    assert "authHeadersFromToken" in js.text
    assert "function updateLinks()" in js.text
    assert "/admin/rag-workbench" in js.text
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
    assert 'id="qa-suggestions"' in body
    assert 'id="qa-copy-answer"' in body
    assert 'id="qa-followups"' in body
    assert 'id="qa-feedback"' in body
    assert 'id="qa-feedback-note"' in body
    assert 'id="qa-history"' in body
    assert 'id="qa-clear-history"' in body
    assert 'id="qa-sources"' in body
    assert "Product manual support" in body
    assert "Try asking" in body
    assert "Ask about a symptom, task, or error." in body
    assert "Knowledge base" not in body
    assert "Use KB" not in body
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
    assert "renderFollowups" in js.text
    assert "buildFollowupQuestions" in js.text
    assert "handleFeedback" in js.text
    assert "/search/feedback" in js.text
    assert "feedbackPayloadForTurn" in js.text
    assert "selectedResultsForFeedback" in js.text
    assert "Feedback sent to Retrieval Quality." in js.text
    assert "addConversationTurn" in js.text
    assert "updateConversationTurn" in js.text
    assert "restoreConversationTurn" in js.text
    assert "clearHistory" in js.text
    assert "qa-history-item" in js.text
    assert "bindSourceToggles" in js.text
    assert "qa-source-summary" in js.text
    assert "qa-source-toggle" in js.text
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
