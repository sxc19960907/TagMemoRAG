# T3 — Reranker first-class component — Design

This document is the technical design for T3. It implements the contracts in `.trellis/spec/backend/architecture.md` § A3, parameterized by D1–D7 in `prd.md`.

## 1. Goal & Boundaries

**In scope:** vendor-neutral `Reranker` Protocol + SF Qwen3-Reranker-0.6B adapter + dispatcher + LRU cache + 4 calibrators + circuit breaker + integration into `/retrieve` pipeline + plan log rerank_json fill + Settings.reranker block + feature flag default off.

**Out of scope:** LLM-as-judge Tier-2; offline teacher (8B); visual reranker (Phase 7B); BGE/BCE adapter; persistent cache; intent-adaptive top_n; rerank in `/search` (legacy).

**Compatibility:** existing `/retrieve` callers unchanged when `Settings.reranker.enabled=False` (default). Existing `/search` never enters reranker.

## 2. Domain Model

### 2.1 RerankDoc / RerankResult / RerankSpec

```python
@dataclass(frozen=True)
class RerankDoc:
    chunk_id: str
    text: str

@dataclass(frozen=True)
class RerankResultItem:
    chunk_id: str
    raw_score: float
    calibrated_score: float

@dataclass(frozen=True)
class RerankResult:
    items: tuple[RerankResultItem, ...]  # sorted desc by calibrated_score
    truncated_chunk_ids: tuple[str, ...]  # chunks that hit max_doc_chars
    vendor_used: str  # "qwen3-reranker-0.6b@siliconflow" / "noop" / etc
    cache_status: Literal["hit", "miss", "skipped"]
    latency_ms: int  # observed wall-clock
    warnings: tuple[str, ...]  # fallback reasons, etc

@dataclass(frozen=True)
class RerankSpec:
    """Stored on QueryPlan.rerank when tier1+ is active."""
    reranker_id: str         # "qwen3-reranker-0.6b@siliconflow"
    reranker_version: str    # vendor model version
    instruction: str | None  # only honored by Qwen3 family
    top_n: int               # output count
```

### 2.2 Reranker Protocol

```python
class Reranker(Protocol):
    id: str
    version: str
    max_seq_length: int
    supports_instruction: bool

    def rerank(
        self,
        query: str,
        docs: list[RerankDoc],
        instruction: str | None,
        budget_ms: int,
    ) -> RerankResult: ...
```

Vendor adapters implement this. `NoopReranker` and `SFQwen3Reranker` are concrete implementations in T3.

### 2.3 Calibrator Protocol + 4 implementations

```python
class Calibrator(Protocol):
    name: str  # "minmax" | "zscore" | "sigmoid" | "identity"
    def calibrate(self, raw_scores: list[float]) -> list[float]: ...
```

`MinMaxCalibrator` (default), `ZScoreCalibrator`, `SigmoidCalibrator`, `IdentityCalibrator`.

Edge cases:
- Empty list → empty list.
- Single element → `[0.5]`.
- All elements equal → list of `0.5`s (no information; mid-point).

### 2.4 CircuitBreaker

```python
class CircuitBreaker:
    """Process-internal, thread-safe via single Lock."""
    def __init__(self, threshold: int = 3, cooldown_s: int = 30): ...
    def is_open(self) -> bool: ...        # checks cooldown elapsed
    def record_failure(self) -> None: ...
    def record_success(self) -> None: ...  # resets failures to 0
```

State: `failures: int`, `opened_at: float | None`. `is_open()` performs cooldown check; once cooldown elapsed, resets and returns False (next call retries vendor).

## 3. SF Qwen3-Reranker-0.6B Adapter

`src/tagmemorag/reranker/siliconflow.py`:

```python
class SFQwen3Reranker:
    id = "qwen3-reranker-0.6b@siliconflow"
    version = "v1"
    max_seq_length = 32768
    supports_instruction = True

    def __init__(self, settings, *, http_client=None, breaker=None):
        self.settings = settings
        self.client = http_client or httpx.Client(timeout=httpx.Timeout(30.0))
        self.breaker = breaker or CircuitBreaker(
            threshold=settings.reranker.circuit_breaker_threshold,
            cooldown_s=settings.reranker.circuit_breaker_cooldown_seconds,
        )

    def rerank(self, query, docs, instruction, budget_ms):
        if self.breaker.is_open():
            raise RerankerCircuitOpen(...)
        # Pre-truncate
        max_doc_chars = self._compute_max_doc_chars(query, instruction)
        truncated = []
        prepared_docs = []
        for d in docs:
            text, was_truncated = self._truncate(d.text, max_doc_chars)
            prepared_docs.append(text)
            if was_truncated:
                truncated.append(d.chunk_id)
        # POST with retry
        try:
            payload = self._call_with_retry(query, prepared_docs, instruction, budget_ms)
            self.breaker.record_success()
        except Exception:
            self.breaker.record_failure()
            raise
        # Map to RerankResultItem (raw_score from API; calibrated set later by dispatcher)
        items = self._build_items(payload, docs)
        return _PartialResult(items=items, truncated=truncated)  # dispatcher fills calibrated + cache_status
```

### 3.1 HTTP request shape (private to adapter; vendor specifics never leak elsewhere)

```python
POST https://api.siliconflow.cn/v1/rerank
Authorization: Bearer ${env[settings.model.api_key_env]}
Content-Type: application/json

{
    "model": "Qwen/Qwen3-Reranker-0.6B",
    "query": "...",
    "documents": ["...", "..."],
    "instruction": "...",  # if supports_instruction and not None
    "top_n": <int>,
    "return_documents": false  # we already have chunk_id mapping
}
```

### 3.2 Retry behavior

- HTTP 200: success.
- HTTP 4xx (except 429): `RerankerClientError` (no retry — config issue).
- HTTP 429 / 5xx / `httpx.ReadTimeout` / `ConnectError` / `RemoteProtocolError`:
  - First failure: sleep `retry_backoff_ms` (200ms default), retry once.
  - Second failure: raise `RerankerVendorError`; breaker records.
- httpx timeout = `min(budget_ms, hard_timeout_ms)` (D7).

### 3.3 Truncation math

```python
def _compute_max_doc_chars(self, query: str, instruction: str | None) -> int:
    s = self.settings.reranker
    used_token_budget = s.query_token_budget + s.instruction_token_budget
    free_tokens = s.max_seq_length - used_token_budget
    # ~4 chars/token, leave 4096 buffer
    return free_tokens * 4 - 4096
```

For Qwen3 0.6B: 32768 - 256 - 64 = 32448 tokens; *4 = 129792 chars; -4096 buffer = ~125696 chars per doc.

## 4. Dispatcher

`src/tagmemorag/reranker/dispatcher.py`:

```python
class RerankerDispatcher:
    """Routes rerank requests per Budget.rerank_tier + ACL; runs fallback chain on failure."""

    def __init__(self, settings, *, primary=None, noop=None, cache=None):
        self.settings = settings
        self.primary = primary or _build_primary(settings)
        self.noop = noop or NoopReranker()
        self.cache = cache or RerankCache(max_entries=settings.reranker.cache_max_entries)
        self.calibrator = _build_calibrator(settings)

    def rerank(
        self,
        plan: QueryPlan,
        candidates: list[SearchResult],
        guard: BudgetGuard,
    ) -> RerankResult:
        # 0. ACL / disabled / tier=off → noop pass-through
        if (
            not self.settings.reranker.enabled
            or plan.budget.rerank_tier == "off"
            or not plan.budget.allow_external_reranker
        ):
            return self._noop_result(candidates, "noop_via_policy")

        # 1. BudgetGuard pre-check (D7)
        if guard.remaining_ms() < self.settings.reranker.min_budget_ms:
            return self._noop_result(candidates, "skipped_due_to_budget")

        # 2. Cache lookup
        cache_key = self._cache_key(plan, candidates)
        if (cached := self.cache.get(cache_key)) is not None:
            return self._calibrate_and_assemble(cached, candidates, "hit", 0)

        # 3. Vendor call
        budget_ms = min(
            guard.remaining_ms() - self.settings.reranker.downstream_reserve_ms,
            self.settings.reranker.hard_timeout_ms,
        )
        docs = [RerankDoc(chunk_id=c.chunk_id, text=c.text) for c in candidates]
        try:
            t0 = time.perf_counter()
            partial = self.primary.rerank(plan.query, docs, plan.rerank.instruction, budget_ms)
            latency_ms = int((time.perf_counter() - t0) * 1000)
            self.cache.put(cache_key, partial.items)
            return self._calibrate_and_assemble(partial.items, candidates, "miss", latency_ms,
                                                 truncated=partial.truncated)
        except Exception as exc:
            return self._noop_result(candidates, f"fallback:{type(exc).__name__}")
```

Cache key:

```python
key = (
    self.primary.id,
    self.primary.version,
    hashlib.sha256((plan.rerank.instruction or "").encode("utf-8")).hexdigest()[:16],
    plan.query_hash,
    hashlib.sha256(",".join(sorted(c.chunk_id for c in candidates)).encode("utf-8")).hexdigest()[:16],
)
```

## 5. Cache

`src/tagmemorag/reranker/cache.py`:

```python
class RerankCache:
    """Simple LRU using OrderedDict; thread-safe via Lock."""

    def __init__(self, max_entries: int = 5000):
        self._cap = max_entries
        self._data: collections.OrderedDict[tuple, list] = collections.OrderedDict()
        self._lock = threading.Lock()

    def get(self, key) -> list | None: ...  # move to end on hit
    def put(self, key, value) -> None: ...  # evict oldest when over cap
```

## 6. Pipeline Integration

In `api.py:_retrieve_impl`, between `execute_search` and `build_retrieve_response`:

```python
# After execute_search returns candidates:
# Note: when reranker enabled, top_k passed to execute_search expanded to rerank_candidates_n.
candidates = execution.results  # up to rerank_candidates_n if enabled

if plan.budget.rerank_tier != "off":
    rerank_outcome = dispatcher.rerank(plan, candidates, guard)
    # Reorder candidates by rerank result; preserve only items in result
    candidates = _reorder(candidates, rerank_outcome)
    if rerank_outcome.warnings:
        warnings.extend(rerank_outcome.warnings)
    plan_log_rerank_payload = {
        "vendor_used": rerank_outcome.vendor_used,
        "calibrated": True,
        "calibrator": settings.reranker.calibrator,
        "latency_ms": rerank_outcome.latency_ms,
        "top_n": len(rerank_outcome.items),
        "truncated_count": len(rerank_outcome.truncated_chunk_ids),
        "cache_status": rerank_outcome.cache_status,
        "warnings": list(rerank_outcome.warnings),
    }
else:
    plan_log_rerank_payload = None

# Then proceed to build_retrieve_response(candidates, ...) — which truncates to user's request.top_k via existing token-budget logic.
```

`execute_search` is called with `top_k = plan.budget.rerank_candidates_n if plan.budget.rerank_tier != "off" else request.top_k`.

`request.top_k` flows through to `build_retrieve_response` for final truncation; existing logic preserved.

## 7. Plan Log rerank_json

When dispatcher returns, the existing `update_result_async` call in `_retrieve_impl` adds `rerank` field:

```python
plan_log.update_result_async(plan.plan_id, {
    # existing fields ...
    "rerank": plan_log_rerank_payload,  # None if rerank_tier=off
})
```

`plan_log.py` already JSON-stringifies the `rerank` key into `rerank_json` column (T2 normalization in update_result_async).

## 8. Settings Block

```python
class RerankerConfig(BaseModel):
    enabled: bool = False                  # D6 feature flag
    default_tier: Literal["off", "tier1", "tier2"] = "tier1"  # used when enabled=True

    provider: Literal["siliconflow", "noop"] = "siliconflow"
    model_id: str = "Qwen/Qwen3-Reranker-0.6B"
    model_version: str = "v1"
    instruction: str | None = None         # default no instruction
    top_n: int = Field(default=20, ge=1)
    rerank_candidates_n: int = Field(default=100, ge=1)  # D1 (also lives on Budget)

    calibrator: Literal["minmax", "zscore", "sigmoid", "identity"] = "minmax"

    max_seq_length: int = 32768
    query_token_budget: int = 256
    instruction_token_budget: int = 64

    retry_max: int = 1
    retry_backoff_ms: int = 200
    circuit_breaker_threshold: int = 3
    circuit_breaker_cooldown_seconds: int = 30

    min_budget_ms: int = 500
    hard_timeout_ms: int = 3000
    downstream_reserve_ms: int = 200

    cache_enabled: bool = True
    cache_max_entries: int = 5000

    api_key_env: str = "SILICONFLOW_API_KEY"
    base_url: str = "https://api.siliconflow.cn/v1"
```

`Settings.reranker: RerankerConfig` field.

`Budget.rerank_candidates_n: int = 100` added to T2 Budget dataclass — but only when reranker active. Resolution rule: `build_plan` reads `settings.reranker.rerank_candidates_n` and writes onto Budget.

## 9. build_plan integration

`build_plan` (T2) gains:

1. Resolve `rerank_tier` per D6 rules (enabled flag + client override).
2. Resolve `rerank_candidates_n` from Settings.reranker.
3. Construct `RerankSpec(reranker_id=..., reranker_version=..., instruction=..., top_n=...)` and attach to `plan.rerank` when tier!="off"; else `None`.

Code change is small — Budget construction + RerankSpec attach.

## 10. Test Matrix

Unit:
- `test_reranker_calibration.py` — 4 calibrators × edge cases (empty, single, all-equal, normal).
- `test_reranker_circuit_breaker.py` — open after N failures, cooldown elapses, half-open behavior, success resets.
- `test_reranker_cache.py` — LRU eviction, key isolation, thread safety smoke.
- `test_reranker_siliconflow.py` — mocked httpx: happy path; 429 retry then success; persistent 5xx → vendor error; truncation; instruction passed through; HTTP 4xx no retry.
- `test_reranker_dispatcher.py` — disabled flag short-circuit; rerank_tier=off; allow_external_reranker=False; budget too tight skips; vendor failure → noop; cache hit; cache miss path.
- `test_reranker_plan_integration.py` — build_plan attaches RerankSpec when enabled; clears when disabled.

API integration:
- `test_queryplan_api_wireup.py` extension (or new file) — `/retrieve` with reranker enabled returns plan_id; rerank field in plan log eventually populated; vendor mock returns reordered results; private KB never calls vendor.

## 11. Risks & Mitigation

| Risk | Mitigation |
|---|---|
| SF outage drops query quality | Fallback chain → noop → preserves baseline |
| Vendor charges spike | Feature flag default off; cache; bounded retry |
| Timeout cascades | BudgetGuard pre-check; httpx timeout from remaining budget |
| Cache memory growth | Bounded LRU 5000 entries; ~10MB upper bound |
| Truncation hides candidates | truncated_chunk_ids surfaced in result + plan log |
| Settings/code drift | Settings.reranker is single source of vendor specifics; never hardcode in dispatcher |
| Thread safety in singleton state (cache, breaker) | All shared mutable state behind Lock |

## 12. Implementation lessons (to fill during slices, T1/T2 pattern)

To be added if implementation surfaces design gaps (D8+).
