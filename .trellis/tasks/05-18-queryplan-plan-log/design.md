# T2 — QueryPlan + Budget contract + SQLite plan log — Design

This document is the technical design for T2. It implements the contracts in `.trellis/spec/backend/architecture.md` § A2 + § C9, parameterized by the eight brainstorm decisions D1–D8 captured in `prd.md`.

## 1. Goal & Boundaries

**In scope:**
- `QueryPlan` and `Budget` dataclasses (frozen, JSON round-trip).
- Rule-based `build_plan(request, kb_name, settings) -> QueryPlan`.
- 2-class intent classifier (`text_answer` / `out_of_scope`); 6-value enum.
- Per-KB SQLite plan log with two-phase write (basic sync + result async via background writer thread).
- `_BudgetGuard` shared-deadline helper used by retrieval / evidence / context_pack stages.
- `SearchRequest` / `RetrieveRequest` accept optional `budget` field.
- Responses include `plan_id`.
- `SearchFeedback` adds optional `plan_id` field; `/search/feedback` and `/retrieve/feedback` accept it.
- PII mask hook (passthrough placeholder).
- Private-KB short-circuit (no persistence, force `allow_external_reranker=False`).
- Settings `queryplan` config block.

**Out of scope:**
- LLM-based query rewrites (HyDE, multi-query) — pluggable backend slot only, no implementation.
- Reranker integration — `rerank: None` placeholder; T3 fills it.
- T5 replay tool — T2 ships persistence only.
- Real PII masking — hook is passthrough with TODO.
- Postgres backend — SQLite per D6 of architecture-v2.
- yaml writeback (Settings is process-internal mutation only — same discipline as T1 D12).

**Compatibility:**
- Existing `/search` and `/retrieve` callers (no `budget` field, no `plan_id` consumption) work unchanged.
- Existing `feedback.jsonl` rows without `plan_id` parse as empty string.

## 2. Domain Model

### 2.1 Intent enum

```python
class Intent(StrEnum):
    TEXT_ANSWER = "text_answer"            # default
    TABLE_LOOKUP = "table_lookup"          # reserved (T6+)
    TROUBLESHOOTING = "troubleshooting"    # reserved (T6+)
    MODEL_SPECIFIC = "model_specific"      # reserved (T6+)
    VISUAL_REFERENCE = "visual_reference"  # reserved (Phase 7B)
    OUT_OF_SCOPE = "out_of_scope"          # T2 emits this
```

T2's classifier emits `TEXT_ANSWER` and `OUT_OF_SCOPE` only. Others are reserved for forward-compat.

### 2.2 Budget

```python
@dataclass(frozen=True)
class Budget:
    latency_ms: int                                   # required
    rerank_tier: Literal["off", "tier1", "tier2"]     # default "off" until T3
    max_evidence: int                                 # default 8
    allow_external_reranker: bool                     # default True; private KBs force False
    deadline_at: float = 0.0                          # set by build_plan; time.monotonic()-based

    def to_dict(self) -> dict[str, Any]: ...
    @classmethod
    def from_dict(cls, data: dict) -> "Budget": ...
```

`deadline_at` is the hot field used at runtime. JSON serialization OMITS `deadline_at` (it's monotonic-clock-relative; not persistable).

### 2.3 QueryPlan

```python
@dataclass(frozen=True)
class QueryPlan:
    schema_version: int                # currently 1
    plan_id: str                       # UUID, request-scoped
    kb_name: str
    query_hash: str                    # sha256 of normalized query; raw query NEVER stored
    query_rewrites_masked: tuple[str, ...]  # PII-masked rewrites; first element is the (masked) original
    intent: Intent
    filters: dict[str, Any]            # snapshot of SearchFilters.to_filter_dict()
    strategy: dict[str, Any]           # which indexes participate; populated by build_plan
    rerank: dict[str, Any] | None      # None until T3; placeholder
    budget: Budget
    served_by_generation: int | None   # filled async from GraphState
    served_by_build_id: str            # filled async
    created_at: str                    # ISO-8601 UTC
    persist: bool = True               # set False for private KBs (D8); not serialized

    def to_basic_dict(self) -> dict: ...    # for sync INSERT — see §4
    def to_result_dict(self) -> dict: ...   # for async UPDATE — see §4
```

`persist=False` short-circuits all SQLite writes for this plan.

## 3. Rule-Based Planner

### 3.1 Entry point

```python
# src/tagmemorag/queryplan/planner.py
def build_plan(
    request: "SearchRequest | RetrieveRequest",
    kb_name: str,
    settings: Settings,
) -> QueryPlan:
    """Construct a QueryPlan from an API request.

    Side effects: NONE. Pure function. The plan is not persisted here;
    persistence is handled by `plan_log.insert_basic` after this returns.
    """
```

### 3.2 Steps inside `build_plan`

1. Generate `plan_id = str(uuid.uuid4())`.
2. Compute `query_hash = "sha256:" + hashlib.sha256(question.strip().encode("utf-8")).hexdigest()`.
3. Build budget:
   - If `request.budget is not None`: use it (with explicit defaults filled).
   - Else: use `settings.queryplan.default_*` fields.
   - Set `budget.deadline_at = time.monotonic() + budget.latency_ms / 1000.0`.
4. Classify intent:
   - `intent = classify_intent(request.question, kb_name, settings)`
   - For T2: return `OUT_OF_SCOPE` if any rule keyword in `settings.queryplan.out_of_scope_keywords` matches; else `TEXT_ANSWER`.
5. Mask rewrites:
   - Initial rewrites = `[request.question]` (passthrough; future LLM planner returns more).
   - `query_rewrites_masked = mask(rewrites, settings.queryplan.pii_mask_rules)` — passthrough in T2.
6. Snapshot filters: `request.filters.to_filter_dict() if request.filters else {}`.
7. Compute strategy:
   - For T2 = `{"indexes": ["vector", "lexical", "metadata", "graph"]}` (matches existing hybrid retrieval).
   - Future planners may scope this down.
8. Private KB short-circuit:
   - `if kb_name in settings.queryplan.private_kbs:`
     - `budget = budget._replace(allow_external_reranker=False)` (use dataclasses.replace)
     - `persist = False`
9. Return frozen QueryPlan with `created_at = now_iso()`.

### 3.3 Intent classifier

```python
# src/tagmemorag/queryplan/intent.py
DEFAULT_OUT_OF_SCOPE_KEYWORDS = (
    "今天天气", "几点了", "翻译成英文", "股票",
    "today's weather", "what time", "translate this",
)

def classify_intent(question: str, kb_name: str, settings: Settings) -> Intent:
    keywords = settings.queryplan.out_of_scope_keywords or DEFAULT_OUT_OF_SCOPE_KEYWORDS
    lowered = question.lower()
    for kw in keywords:
        if kw.lower() in lowered:
            return Intent.OUT_OF_SCOPE
    return Intent.TEXT_ANSWER
```

The keyword list lives in code (DEFAULT_*) plus optional override in `Settings.queryplan.out_of_scope_keywords`. Settings = pydantic `list[str] | None` (None = use defaults).

## 4. Plan Log Storage

### 4.1 File location

```
{kb_root}/query_plans.db
```
Same per-KB convention as `index.json`. SQLite WAL mode for concurrent reads.

### 4.2 Schema (user_version=1)

```sql
CREATE TABLE plans (
    plan_id TEXT PRIMARY KEY,
    schema_version INTEGER NOT NULL DEFAULT 1,
    kb_name TEXT NOT NULL,
    query_hash TEXT NOT NULL,
    query_rewrites_masked_json TEXT NOT NULL,
    intent TEXT NOT NULL,
    filters_json TEXT NOT NULL,
    strategy_json TEXT NOT NULL,
    budget_json TEXT NOT NULL,
    rerank_json TEXT,                    -- T3 fills (NULL in T2)
    served_by_generation INTEGER,        -- async UPDATE
    served_by_build_id TEXT,             -- async UPDATE
    cache_status TEXT,                   -- "hit" | "miss" | "disabled"; async UPDATE
    evidence_ids_json TEXT,              -- async UPDATE
    latency_ms_observed INTEGER,         -- async UPDATE
    warnings_json TEXT,                  -- async UPDATE
    created_at TEXT NOT NULL
);
CREATE INDEX idx_plans_kb_created ON plans(kb_name, created_at);
CREATE INDEX idx_plans_kb_generation ON plans(kb_name, served_by_generation);
CREATE INDEX idx_plans_kb_intent ON plans(kb_name, intent);
PRAGMA user_version = 1;
PRAGMA journal_mode = WAL;
```

### 4.3 Connection management + APIs

- `PlanLog` per KB; lazy connection; WAL mode; `check_same_thread=False`; `timeout=2.0s`.
- `_ensure_schema` runs migration on first connect.
- `insert_basic(plan)` — sync write of basic fields BEFORE response returns; failures swallowed + metric.
- `update_result_async(plan_id, result_dict)` — enqueue to BackgroundWriter; non-blocking.

### 4.4 BackgroundWriter

- Module-level singleton, single worker thread.
- Bounded `queue.Queue(maxsize=settings.queryplan.background_writer_max_queue)`; default 1024.
- Overflow → drop oldest + `record_plan_log_event("queue_overflow")`. Drop preferred over blocking the API thread.
- UPDATE failures logged + metric; worker thread never crashes.

### 4.5 Retention

`prune_expired(kb, settings)` — admin-callable function that DELETEs rows older than `settings.queryplan.retention_days`. T2 does NOT auto-trigger; T5 may schedule.

### 4.6 Schema migration

`PRAGMA user_version`. fresh→v1; v1→v1 no-op; unknown→`STORAGE_SCHEMA_MISMATCH`.

## 5. PII Mask Hook

```python
# src/tagmemorag/queryplan/privacy.py
def mask_rewrites(rewrites: list[str], rules: list[dict] | None) -> tuple[str, ...]:
    """T2 default: passthrough.
    rules format: [{"pattern": r"...", "replace": "[REDACTED]"}, ...]
    """
    if not rules:
        return tuple(rewrites)
    out = []
    for text in rewrites:
        masked = text
        for rule in rules:
            masked = re.sub(rule["pattern"], rule["replace"], masked)
        out.append(masked)
    return tuple(out)
```

T2 ships rules=None (passthrough). Hook exists so a later task can plug in masking via `Settings.queryplan.pii_mask_rules` without changing the planner contract.

## 6. Early-Exit Protocol

### 6.1 BudgetGuard

```python
# src/tagmemorag/queryplan/budget.py
class BudgetGuard:
    def __init__(self, plan: QueryPlan):
        self.plan = plan

    def remaining_ms(self) -> int:
        deadline = self.plan.budget.deadline_at
        if deadline <= 0.0:
            return self.plan.budget.latency_ms
        return max(0, int((deadline - time.monotonic()) * 1000))

    def exhausted(self) -> bool:
        return self.remaining_ms() <= 0
```

### 6.2 Stage integration

Each stage in `_search_impl` / `_retrieve_impl` checks `guard.exhausted()` at entry. On exhaustion: append warning, skip stage, continue. **Never raise.** Response always structurally valid.

Stages:
1. Out-of-scope short-circuit (intent check)
2. Cache lookup
3. Retrieval
4. Evidence build
5. Context pack (only `/retrieve`)

## 7. API Surface Changes

### 7.1 Request models

```python
class BudgetSpec(BaseModel):
    latency_ms: int | None = None
    rerank_tier: Literal["off", "tier1", "tier2"] | None = None
    max_evidence: int | None = None
    allow_external_reranker: bool | None = None

class SearchRequest(BaseModel):
    # ... existing fields ...
    budget: BudgetSpec | None = None
```

### 7.2 Response shape

`/search` and `/retrieve` add `plan_id: str` and optional `warnings: list[str]`. All existing fields preserved.

### 7.3 Feedback request

`FeedbackSubmitRequest.plan_id: str | None = None`; `SearchFeedback.plan_id: str = ""`. JSONL backward compat: missing field → "".

### 7.4 No new admin endpoints in T2

T5 builds query/replay tooling.

## 8. Settings Block

```python
class QueryPlanConfig(BaseModel):
    persist_enabled: bool = True
    retention_days: int = 30
    private_kbs: list[str] = Field(default_factory=list)
    default_latency_ms: int = 5000
    default_max_evidence: int = 8
    default_rerank_tier: Literal["off", "tier1", "tier2"] = "off"
    default_allow_external_reranker: bool = True
    out_of_scope_keywords: list[str] | None = None
    pii_mask_rules: list[dict] | None = None
    background_writer_max_queue: int = 1024
```

`Settings.queryplan: QueryPlanConfig` field added.

## 9. Wire-up in `_search_impl` / `_retrieve_impl`

Pseudo-code:

```python
def _search_impl(request, http_request, state, t0):
    plan = build_plan(request, request.kb_name, settings)
    plan_log = get_plan_log(request.kb_name, settings)
    plan_log.insert_basic(plan)
    guard = BudgetGuard(plan)
    warnings = []

    # 1. out-of-scope short-circuit
    if plan.intent == Intent.OUT_OF_SCOPE:
        warnings.append("out_of_scope_intent")
        plan_log.update_result_async(plan.plan_id, {
            "served_by_generation": active_gen,
            "served_by_build_id": state.build_id,
            "cache_status": "disabled",
            "evidence_ids": [],
            "latency_ms_observed": elapsed_ms(t0),
            "warnings": warnings,
        })
        return SearchResponse(plan_id=plan.plan_id, results=[], warnings=warnings, ...)

    # 2. cache check
    cache_status = "disabled"
    if app_state.query_cache:
        cached = app_state.query_cache.get(...)
        if cached:
            cache_status = "hit"
            plan_log.update_result_async(plan.plan_id, {"cache_status": "hit", ...})
            return cached.with_plan_id(plan.plan_id)
        cache_status = "miss"

    # 3-5. retrieval / evidence / context_pack with guard checks
    candidates = []
    if guard.exhausted():
        warnings.append("retrieval_skipped_due_to_budget")
    else:
        candidates = retrieve(...)
    # ... same pattern for evidence, context_pack ...

    plan_log.update_result_async(plan.plan_id, {...})
    return SearchResponse(plan_id=plan.plan_id, warnings=warnings, ...)
```

## 10. Test Matrix

Unit:
- `test_queryplan_budget.py` — Budget round-trip, deadline_at not serialized, BudgetGuard exhaustion math.
- `test_queryplan_intent.py` — out-of-scope keyword matching, custom Settings override.
- `test_queryplan_planner.py` — build_plan output, private KB short-circuit, plan_id uniqueness, deadline set.
- `test_queryplan_privacy.py` — mask passthrough, mask with rule, multiple rules.
- `test_queryplan_plan_log.py` — schema migration, insert_basic, update_result, retention pruning, schema mismatch error.
- `test_queryplan_background_writer.py` — overflow drops + metric, FIFO ordering, worker exception isolation.
- `test_search_feedback_plan_id.py` — SearchFeedback adds plan_id, jsonl backward compat.

API integration:
- `/search` returns plan_id; pre-existing fields unchanged.
- `/retrieve` returns plan_id.
- `/search/feedback` accepts plan_id.
- private KB does NOT persist plan; response still has plan_id.
- forced low-budget request returns warnings + empty results, not error.
- cache hit produces fresh plan_id; cache_status="hit" eventually in plan log.

## 11. Risk & Mitigation

| Risk | Mitigation |
|---|---|
| SQLite contention under burst | WAL mode + single shared BackgroundWriter; bounded queue with overflow drop. |
| `plan_id` returned but not yet in DB at instant lookup | Documented in API: response is authoritative; row arrives within ms. |
| BackgroundWriter dies → silently lose updates | Worker exception logged + metric; thread restarts on next enqueue. |
| Schema migration on existing DB with newer version | Hard error per `_ensure_schema`; ops must downgrade or run migration tool (T5+). |
| Query rewrites contain PII before mask hook plugged in | Default rules=None → only `[question]` stored; same exposure as feedback.jsonl. |
| Private KB list misconfigured (KB still leaks) | Tests cover; admin endpoint to inspect `Settings.queryplan` (planned T5). |

## 12. Out-of-task questions resolved during implementation

To be added during slice work, mirroring T1 pattern (D9–D12 added during implementation when reality surfaced design gaps).
