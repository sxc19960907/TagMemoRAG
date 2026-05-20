"""SiliconFlow Qwen3-Reranker-0.6B adapter (Architecture v2 § A3 / Decision D5).

Vendor specifics confined here per [[arch-vendor-specifics-discipline]].
Dispatcher and build_plan never reference SF / Qwen3 by name.

Resilience:
- httpx timeout = caller-supplied budget_ms (clamped by hard_timeout_ms).
- Single retry on 5xx / 429 / network with exponential backoff.
- HTTP 4xx (except 429) → no retry (config error).
- Failures bubble to dispatcher (not caller) and are caught into fallback.
- CircuitBreaker tracked per adapter instance; record_failure on raise,
  record_success on 200 OK.

Truncation:
- Pre-truncate each doc to max_doc_chars before POST. Qwen3 does NOT support
  vendor-side max_chunks_per_doc / overlap_tokens fields.
- Truncated chunk_ids surfaced in RerankerOutcome for plan log + warnings.
"""

from __future__ import annotations

import os
import time
from typing import Any

import httpx
import structlog

from ..config import Settings
from .base import RerankDoc, RerankerOutcome
from .circuit_breaker import CircuitBreaker

_LOGGER = structlog.get_logger()


class RerankerCircuitOpenError(Exception):
    """Breaker is open; vendor not called."""


class RerankerVendorError(Exception):
    """Vendor returned non-recoverable failure (after retry exhausted)."""


class RerankerClientError(Exception):
    """4xx (except 429); not retried — config error."""


class SFQwen3Reranker:
    id: str = "qwen3-reranker-0.6b@siliconflow"
    version: str = "v1"
    max_seq_length: int = 32768
    supports_instruction: bool = True

    def __init__(
        self,
        settings: Settings,
        *,
        http_client: httpx.Client | None = None,
        breaker: CircuitBreaker | None = None,
    ):
        self.settings = settings
        self._http = http_client  # may be None; lazy-init in _post
        self._owns_http = http_client is None
        self._breaker = breaker or CircuitBreaker(
            threshold=settings.reranker.circuit_breaker_threshold,
            cooldown_s=settings.reranker.circuit_breaker_cooldown_seconds,
        )

    @property
    def breaker(self) -> CircuitBreaker:
        return self._breaker

    def _get_http(self) -> httpx.Client:
        if self._http is None:
            # Default client; per-call timeout overrides this anyway
            self._http = httpx.Client(timeout=httpx.Timeout(30.0))
        return self._http

    def _api_key(self) -> str:
        env_name = self.settings.reranker.api_key_env
        key = os.environ.get(env_name, "")
        if not key:
            raise RerankerClientError(f"API key env var not set: {env_name}")
        return key

    def _max_doc_chars(self) -> int:
        s = self.settings.reranker
        free_tokens = s.max_seq_length - s.query_token_budget - s.instruction_token_budget
        # ~4 chars/token, leave 4096 buffer
        max_chars = free_tokens * 4 - 4096
        return max(1, max_chars)

    @staticmethod
    def _truncate(text: str, max_chars: int) -> tuple[str, bool]:
        if len(text) <= max_chars:
            return text, False
        return text[:max_chars], True

    def rerank(
        self,
        query: str,
        docs: list[RerankDoc],
        instruction: str | None,
        budget_ms: int,
    ) -> RerankerOutcome:
        if self._breaker.is_open():
            raise RerankerCircuitOpenError("breaker open; skipping vendor call")
        if not docs:
            return RerankerOutcome(items=(), truncated_chunk_ids=(), vendor_id=self.id)

        max_chars = self._max_doc_chars()
        truncated: list[str] = []
        prepared_texts: list[str] = []
        for d in docs:
            text, was_truncated = self._truncate(d.text, max_chars)
            prepared_texts.append(text)
            if was_truncated:
                truncated.append(d.chunk_id)

        try:
            response_payload = self._call_with_retry(
                query=query,
                documents=prepared_texts,
                instruction=instruction,
                budget_ms=budget_ms,
            )
            self._breaker.record_success()
        except Exception:
            self._breaker.record_failure()
            raise

        items = self._build_items(response_payload, docs)
        return RerankerOutcome(
            items=items,
            truncated_chunk_ids=tuple(truncated),
            vendor_id=self.id,
        )

    def _build_items(
        self,
        payload: dict[str, Any],
        docs: list[RerankDoc],
    ) -> tuple[tuple[str, float], ...]:
        results = payload.get("results", [])
        items: list[tuple[str, float]] = []
        for entry in results:
            try:
                idx = int(entry["index"])
                score = float(entry["relevance_score"])
            except (KeyError, TypeError, ValueError):
                continue
            if 0 <= idx < len(docs):
                items.append((docs[idx].chunk_id, score))
        return tuple(items)

    def _call_with_retry(
        self,
        *,
        query: str,
        documents: list[str],
        instruction: str | None,
        budget_ms: int,
    ) -> dict[str, Any]:
        s = self.settings.reranker
        # Effective httpx timeout: at most hard_timeout_ms, at least 100ms (paranoid floor).
        effective_ms = max(100, min(budget_ms, s.hard_timeout_ms))
        timeout = httpx.Timeout(effective_ms / 1000.0)

        body: dict[str, Any] = {
            "model": s.model_id,
            "query": query,
            "documents": documents,
            "top_n": s.top_n,
            "return_documents": False,
        }
        if self.supports_instruction and instruction:
            body["instruction"] = instruction

        url = f"{s.base_url.rstrip('/')}/rerank"
        headers = {
            "Authorization": f"Bearer {self._api_key()}",
            "Content-Type": "application/json",
        }

        attempts = max(1, s.retry_max + 1)
        last_exc: Exception | None = None
        for attempt in range(attempts):
            try:
                resp = self._get_http().post(url, json=body, headers=headers, timeout=timeout)
            except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as exc:
                last_exc = exc
                _LOGGER.warning(
                    "reranker_vendor_network_error",
                    attempt=attempt,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                )
                if attempt + 1 < attempts:
                    time.sleep(s.retry_backoff_ms / 1000.0)
                    continue
                raise RerankerVendorError(f"network error after {attempts} attempts: {exc}") from exc

            status = resp.status_code
            if status == 200:
                try:
                    return resp.json()
                except Exception as exc:  # noqa: BLE001
                    raise RerankerVendorError(f"invalid JSON in response: {exc}") from exc
            if 400 <= status < 500 and status != 429:
                raise RerankerClientError(
                    f"client error {status}: {resp.text[:300]}"
                )
            # 429 / 5xx — retryable
            last_exc = RerankerVendorError(f"vendor returned {status}: {resp.text[:300]}")
            _LOGGER.warning(
                "reranker_vendor_retryable",
                attempt=attempt,
                status=status,
            )
            if attempt + 1 < attempts:
                time.sleep(s.retry_backoff_ms / 1000.0)
                continue
            raise last_exc

        # Unreachable, but appease linters
        raise RerankerVendorError("unreachable")

    def close(self) -> None:
        if self._owns_http and self._http is not None:
            self._http.close()
            self._http = None


__all__ = [
    "RerankerCircuitOpenError",
    "RerankerClientError",
    "RerankerVendorError",
    "SFQwen3Reranker",
]
