"""Tests for SF Qwen3-Reranker-0.6B adapter (T3 Slice 4)."""

from __future__ import annotations

import json

import httpx
import pytest

from tagmemorag.config import Settings
from tagmemorag.reranker.base import RerankDoc
from tagmemorag.reranker.circuit_breaker import CircuitBreaker
from tagmemorag.reranker.siliconflow import (
    RerankerCircuitOpenError,
    RerankerClientError,
    RerankerVendorError,
    SFQwen3Reranker,
)


@pytest.fixture
def settings(monkeypatch) -> Settings:
    monkeypatch.setenv("SILICONFLOW_API_KEY", "test-key-xyz")
    s = Settings()
    s.reranker.retry_max = 1
    s.reranker.retry_backoff_ms = 1  # fast in tests
    s.reranker.circuit_breaker_threshold = 2
    s.reranker.circuit_breaker_cooldown_seconds = 1
    return s


def _mock_transport(handler) -> httpx.Client:
    transport = httpx.MockTransport(handler)
    return httpx.Client(transport=transport, timeout=httpx.Timeout(10.0))


def _docs(n: int = 3) -> list[RerankDoc]:
    return [RerankDoc(chunk_id=f"c{i}", text=f"text {i}") for i in range(n)]


# ---------- happy path ----------

def test_rerank_happy_path(settings):
    seen_requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append(request)
        body = json.loads(request.content)
        # SF returns results in order of relevance_score desc; we mimic by index
        results = [{"index": 1, "relevance_score": 0.9},
                   {"index": 0, "relevance_score": 0.7},
                   {"index": 2, "relevance_score": 0.3}]
        return httpx.Response(200, json={"id": "rerank-x", "results": results})

    client = _mock_transport(handler)
    rk = SFQwen3Reranker(settings, http_client=client)
    outcome = rk.rerank("query", _docs(3), instruction=None, budget_ms=2000)

    assert outcome.vendor_id == "qwen3-reranker-0.6b@siliconflow"
    assert len(outcome.items) == 3
    assert outcome.items[0] == ("c1", 0.9)
    assert outcome.items[1] == ("c0", 0.7)
    assert outcome.items[2] == ("c2", 0.3)
    assert outcome.truncated_chunk_ids == ()
    # Verify request shape
    assert len(seen_requests) == 1
    req_body = json.loads(seen_requests[0].content)
    assert req_body["model"] == "Qwen/Qwen3-Reranker-0.6B"
    assert req_body["query"] == "query"
    assert req_body["documents"] == ["text 0", "text 1", "text 2"]
    assert req_body["return_documents"] is False
    assert seen_requests[0].headers["authorization"] == "Bearer test-key-xyz"


def test_rerank_with_instruction(settings):
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"results": []})

    client = _mock_transport(handler)
    rk = SFQwen3Reranker(settings, http_client=client)
    rk.rerank("q", _docs(1), instruction="Sort by recency", budget_ms=2000)
    assert seen[0]["instruction"] == "Sort by recency"


def test_rerank_omits_instruction_when_none(settings):
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"results": []})

    client = _mock_transport(handler)
    rk = SFQwen3Reranker(settings, http_client=client)
    rk.rerank("q", _docs(1), instruction=None, budget_ms=2000)
    assert "instruction" not in seen[0]


def test_rerank_empty_docs_short_circuits(settings):
    """Empty docs returns empty outcome without HTTP call."""
    call_count = {"n": 0}

    def handler(request):
        call_count["n"] += 1
        return httpx.Response(200, json={"results": []})

    client = _mock_transport(handler)
    rk = SFQwen3Reranker(settings, http_client=client)
    outcome = rk.rerank("q", [], instruction=None, budget_ms=2000)
    assert outcome.items == ()
    assert call_count["n"] == 0


# ---------- truncation ----------

def test_rerank_truncates_oversized_doc(settings):
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"results": []})

    # Force a small budget so truncation triggers
    settings.reranker.max_seq_length = 1024
    settings.reranker.query_token_budget = 100
    settings.reranker.instruction_token_budget = 50
    # max_chars = (1024 - 100 - 50) * 4 - 4096 = 3500 - 4096 = -596 → clamped to 1
    # Use a sane setting instead:
    settings.reranker.max_seq_length = 2048
    settings.reranker.query_token_budget = 50
    settings.reranker.instruction_token_budget = 0
    # max_chars = (2048 - 50) * 4 - 4096 = 7992 - 4096 = 3896

    client = _mock_transport(handler)
    rk = SFQwen3Reranker(settings, http_client=client)
    huge_doc = "x" * 10000
    docs = [RerankDoc(chunk_id="big", text=huge_doc), RerankDoc(chunk_id="small", text="ok")]
    outcome = rk.rerank("q", docs, instruction=None, budget_ms=2000)
    assert "big" in outcome.truncated_chunk_ids
    assert "small" not in outcome.truncated_chunk_ids
    # Verify the body actually had truncated text
    sent = seen[0]["documents"]
    assert len(sent[0]) <= 3896
    assert sent[1] == "ok"


# ---------- retry / failure paths ----------

def test_rerank_retries_on_429_then_succeeds(settings):
    call_count = {"n": 0}

    def handler(request):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return httpx.Response(429, text="rate limited")
        return httpx.Response(200, json={"results": [{"index": 0, "relevance_score": 0.5}]})

    client = _mock_transport(handler)
    rk = SFQwen3Reranker(settings, http_client=client)
    outcome = rk.rerank("q", _docs(1), instruction=None, budget_ms=2000)
    assert call_count["n"] == 2
    assert outcome.items == (("c0", 0.5),)


def test_rerank_retries_on_5xx_then_succeeds(settings):
    call_count = {"n": 0}

    def handler(request):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return httpx.Response(503, text="service unavailable")
        return httpx.Response(200, json={"results": [{"index": 0, "relevance_score": 0.7}]})

    client = _mock_transport(handler)
    rk = SFQwen3Reranker(settings, http_client=client)
    outcome = rk.rerank("q", _docs(1), instruction=None, budget_ms=2000)
    assert call_count["n"] == 2
    assert outcome.items == (("c0", 0.7),)


def test_rerank_persistent_5xx_raises_vendor_error(settings):
    def handler(request):
        return httpx.Response(503, text="down")

    client = _mock_transport(handler)
    rk = SFQwen3Reranker(settings, http_client=client)
    with pytest.raises(RerankerVendorError):
        rk.rerank("q", _docs(1), instruction=None, budget_ms=2000)


def test_rerank_4xx_no_retry_client_error(settings):
    call_count = {"n": 0}

    def handler(request):
        call_count["n"] += 1
        return httpx.Response(401, text="unauthorized")

    client = _mock_transport(handler)
    rk = SFQwen3Reranker(settings, http_client=client)
    with pytest.raises(RerankerClientError):
        rk.rerank("q", _docs(1), instruction=None, budget_ms=2000)
    assert call_count["n"] == 1  # no retry


def test_rerank_records_success_after_200(settings):
    breaker = CircuitBreaker(threshold=2, cooldown_s=10)
    breaker.record_failure()  # 1 failure recorded

    def handler(request):
        return httpx.Response(200, json={"results": []})

    client = _mock_transport(handler)
    rk = SFQwen3Reranker(settings, http_client=client, breaker=breaker)
    rk.rerank("q", _docs(1), instruction=None, budget_ms=2000)
    state = breaker.state()
    assert state["failures"] == 0  # success cleared


def test_rerank_records_failure_on_vendor_error(settings):
    breaker = CircuitBreaker(threshold=3, cooldown_s=10)

    def handler(request):
        return httpx.Response(503, text="down")

    client = _mock_transport(handler)
    rk = SFQwen3Reranker(settings, http_client=client, breaker=breaker)
    with pytest.raises(RerankerVendorError):
        rk.rerank("q", _docs(1), instruction=None, budget_ms=2000)
    assert breaker.state()["failures"] == 1


def test_rerank_skipped_when_breaker_open(settings):
    breaker = CircuitBreaker(threshold=1, cooldown_s=10)
    breaker.record_failure()  # opens

    call_count = {"n": 0}

    def handler(request):
        call_count["n"] += 1
        return httpx.Response(200, json={"results": []})

    client = _mock_transport(handler)
    rk = SFQwen3Reranker(settings, http_client=client, breaker=breaker)
    with pytest.raises(RerankerCircuitOpenError):
        rk.rerank("q", _docs(1), instruction=None, budget_ms=2000)
    assert call_count["n"] == 0  # breaker prevented HTTP call


def test_rerank_missing_api_key_raises_client_error(settings, monkeypatch):
    monkeypatch.delenv("SILICONFLOW_API_KEY", raising=False)

    def handler(request):
        return httpx.Response(200, json={"results": []})

    client = _mock_transport(handler)
    rk = SFQwen3Reranker(settings, http_client=client)
    with pytest.raises(RerankerClientError, match="API key"):
        rk.rerank("q", _docs(1), instruction=None, budget_ms=2000)


def test_rerank_handles_invalid_json_response(settings):
    def handler(request):
        return httpx.Response(200, content=b"not json")

    client = _mock_transport(handler)
    rk = SFQwen3Reranker(settings, http_client=client)
    with pytest.raises(RerankerVendorError, match="invalid JSON"):
        rk.rerank("q", _docs(1), instruction=None, budget_ms=2000)


def test_rerank_skips_malformed_result_entries(settings):
    """Malformed entries in `results` are silently dropped (not raised)."""
    def handler(request):
        return httpx.Response(200, json={"results": [
            {"index": 0, "relevance_score": 0.5},
            {"missing_score": True},  # malformed
            {"index": "not_int", "relevance_score": 0.3},  # bad index
            {"index": 2, "relevance_score": 0.1},
        ]})

    client = _mock_transport(handler)
    rk = SFQwen3Reranker(settings, http_client=client)
    outcome = rk.rerank("q", _docs(3), instruction=None, budget_ms=2000)
    assert len(outcome.items) == 2
    assert outcome.items[0] == ("c0", 0.5)
    assert outcome.items[1] == ("c2", 0.1)
