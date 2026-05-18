"""Reranker dispatcher (Architecture v2 § A3).

Routes rerank requests per Budget.rerank_tier + ACL flag; manages cache,
calibration, and fallback chain. Never raises to the caller.

Routing tree (in order):
  1. Settings.reranker.enabled=False → noop pass-through.
  2. plan.budget.rerank_tier="off" → noop pass-through.
  3. plan.budget.allow_external_reranker=False (private KB / ACL) → noop pass-through.
  4. BudgetGuard.remaining_ms() < min_budget_ms → noop, warning="reranker_skipped_due_to_budget".
  5. Cache lookup → return cached items + cache_status="hit".
  6. Vendor call → on success, calibrate + cache + return; on failure, noop fallback with warning.
"""

from __future__ import annotations

import hashlib
import time
from typing import TYPE_CHECKING, Iterable

import structlog

from .base import (
    RerankDoc,
    RerankResult,
    RerankResultItem,
    RerankerOutcome,
)
from .cache import RerankCache
from .calibration import build_calibrator
from .local_fallback import NoopReranker
from .siliconflow import (
    RerankerCircuitOpenError,
    RerankerClientError,
    RerankerVendorError,
    SFQwen3Reranker,
)

if TYPE_CHECKING:  # pragma: no cover
    from ..config import Settings
    from ..queryplan import QueryPlan
    from ..queryplan.budget import BudgetGuard

_LOGGER = structlog.get_logger()


class _CandidateLike:
    """Duck-type for SearchResult — only chunk_id and text needed.

    The real SearchResult class lives in retrieval; we don't import it here
    to keep dispatcher independent of search internals. Caller passes any
    object with `chunk_id` and `text` attributes.
    """

    chunk_id: str
    text: str


class RerankerDispatcher:
    def __init__(
        self,
        settings: "Settings",
        *,
        primary=None,
        noop=None,
        cache=None,
    ):
        self.settings = settings
        self.primary = primary or self._build_primary()
        self.noop = noop or NoopReranker()
        if cache is not None:
            self.cache = cache
        elif settings.reranker.cache_enabled:
            self.cache = RerankCache(max_entries=settings.reranker.cache_max_entries)
        else:
            self.cache = None
        self.calibrator = build_calibrator(settings.reranker.calibrator)

    def _build_primary(self):
        s = self.settings.reranker
        if s.provider == "siliconflow":
            return SFQwen3Reranker(self.settings)
        if s.provider == "noop":
            return NoopReranker()
        raise ValueError(f"Unknown reranker provider: {s.provider}")

    @staticmethod
    def _instruction_hash(instruction: str | None) -> str:
        body = (instruction or "").encode("utf-8")
        return hashlib.sha256(body).hexdigest()[:16]

    @staticmethod
    def _chunk_id_set_hash(candidates: Iterable) -> str:
        ids = sorted(c.chunk_id for c in candidates)
        return hashlib.sha256(",".join(ids).encode("utf-8")).hexdigest()[:16]

    def _cache_key(self, plan: "QueryPlan", candidates: Iterable) -> tuple:
        instruction = plan.rerank.instruction if plan.rerank else None
        return (
            self.primary.id,
            self.primary.version,
            self._instruction_hash(instruction),
            plan.query_hash,
            self._chunk_id_set_hash(candidates),
        )

    def _calibrate(self, raw_pairs: list[tuple[str, float]]) -> list[RerankResultItem]:
        if not raw_pairs:
            return []
        scores = [p[1] for p in raw_pairs]
        calibrated = self.calibrator.calibrate(scores)
        items = [
            RerankResultItem(chunk_id=cid, raw_score=raw, calibrated_score=cal)
            for (cid, raw), cal in zip(raw_pairs, calibrated)
        ]
        items.sort(key=lambda it: it.calibrated_score, reverse=True)
        return items

    def _noop_result(
        self,
        candidates: list,
        reason: str,
        cache_status: str = "skipped",
    ) -> RerankResult:
        outcome = self.noop.rerank(
            query="",
            docs=[RerankDoc(chunk_id=c.chunk_id, text="") for c in candidates],
            instruction=None,
            budget_ms=0,
        )
        items = self._calibrate(list(outcome.items))
        return RerankResult(
            items=tuple(items),
            truncated_chunk_ids=(),
            vendor_used=self.noop.id,
            cache_status=cache_status,  # type: ignore[arg-type]
            latency_ms=0,
            warnings=(reason,) if reason else (),
        )

    def rerank(
        self,
        plan: "QueryPlan",
        candidates: list,
        guard: "BudgetGuard",
    ) -> RerankResult:
        s = self.settings.reranker

        # 1. Global enabled check
        if not s.enabled:
            return self._noop_result(candidates, "noop_via_settings_disabled")

        # 2. Plan tier check
        tier = plan.budget.rerank_tier
        if tier == "off":
            return self._noop_result(candidates, "noop_via_tier_off")

        # 3. ACL gate
        if not plan.budget.allow_external_reranker:
            return self._noop_result(candidates, "noop_via_acl")

        # 4. Budget guard pre-check
        remaining = guard.remaining_ms()
        if remaining < s.min_budget_ms:
            return self._noop_result(
                candidates, "reranker_skipped_due_to_budget"
            )

        # 5. Cache lookup
        cache_key = self._cache_key(plan, candidates) if self.cache is not None else None
        if cache_key is not None and self.cache is not None:
            cached = self.cache.get(cache_key)
            if cached is not None:
                items = self._calibrate(cached)
                return RerankResult(
                    items=tuple(items),
                    truncated_chunk_ids=(),
                    vendor_used=self.primary.id,
                    cache_status="hit",
                    latency_ms=0,
                    warnings=(),
                )

        # 6. Vendor call
        budget_ms = max(
            1,
            min(remaining - s.downstream_reserve_ms, s.hard_timeout_ms),
        )
        instruction = plan.rerank.instruction if plan.rerank else None
        docs = [RerankDoc(chunk_id=c.chunk_id, text=c.text) for c in candidates]
        t0 = time.perf_counter()
        try:
            outcome: RerankerOutcome = self.primary.rerank(
                query=getattr(plan, "query_text", "") or "",
                docs=docs,
                instruction=instruction,
                budget_ms=budget_ms,
            )
        except (RerankerCircuitOpenError, RerankerVendorError, RerankerClientError) as exc:
            _LOGGER.warning(
                "reranker_dispatcher_fallback",
                kb_name=plan.kb_name,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
            return self._noop_result(
                candidates,
                f"reranker_fallback:{type(exc).__name__}",
            )
        except Exception as exc:  # noqa: BLE001  defensive
            _LOGGER.error(
                "reranker_dispatcher_unexpected",
                kb_name=plan.kb_name,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
            return self._noop_result(
                candidates,
                f"reranker_fallback:unexpected_{type(exc).__name__}",
            )

        latency_ms = int((time.perf_counter() - t0) * 1000)
        if cache_key is not None and self.cache is not None:
            self.cache.put(cache_key, list(outcome.items))
        items = self._calibrate(list(outcome.items))
        return RerankResult(
            items=tuple(items),
            truncated_chunk_ids=tuple(outcome.truncated_chunk_ids),
            vendor_used=self.primary.id,
            cache_status="miss",
            latency_ms=latency_ms,
            warnings=(),
        )


__all__ = ["RerankerDispatcher"]
