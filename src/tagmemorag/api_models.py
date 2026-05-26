from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .retrieval import DEFAULT_TOKEN_BUDGET
from .tag_suggestions import DEFAULT_LIMIT


class GhostTagSpec(BaseModel):
    """Caller-supplied tag with explicit vector, bypassing the KB tag store.

    `vector` length must equal the model embedding dim at request time;
    mismatched ghosts are silently skipped and counted in `info.ghost_skipped_dim_mismatch`.
    """

    name: str = Field(..., min_length=1, max_length=128)
    vector: list[float] = Field(..., min_length=1)
    is_core: bool = False


class AccessKeyGenerateRequest(BaseModel):
    id: str = Field(..., min_length=1, max_length=128)
    label: str = Field(default="", max_length=256)
    scopes: list[str] = Field(default_factory=lambda: ["search"])
    kb_allowlist: list[str] = Field(default_factory=lambda: ["*"])
    rate_limit_per_minute: int | None = Field(default=60, ge=1)
    prefix: str = Field(default="tmr_live_", min_length=1, max_length=64)


class SearchRequest(BaseModel):
    question: str
    top_k: int | None = None
    source_k: int | None = None
    steps: int | None = None
    decay: float | None = None
    amplitude_cutoff: float | None = None
    aggregate: str | None = None
    kb_name: str = "default"
    filters: "SearchFilters | None" = None
    debug: bool | None = None
    core_tags: list[str] = Field(default_factory=list)
    ghost_tags: list[GhostTagSpec] = Field(default_factory=list)
    budget: "BudgetSpec | None" = None
    mode: Literal["classic", "agentic"] | None = None
    agentic: "AgenticRequestOverrides | None" = None


class AgenticRequestOverrides(BaseModel):
    decision_enabled: bool | None = None
    max_iterations: int | None = Field(default=None, ge=0)
    max_agent_tokens: int | None = Field(default=None, ge=1)
    max_tool_calls: int | None = Field(default=None, ge=0)


class BudgetSpec(BaseModel):
    """T2: optional per-request resource budget override.

    Missing fields fall through to Settings.queryplan.default_*. The
    deadline_at lifecycle field on the runtime Budget is computed by
    build_plan and never appears in the API surface.
    """

    latency_ms: int | None = Field(default=None, ge=1)
    rerank_tier: Literal["off", "tier1", "tier2"] | None = None
    max_evidence: int | None = Field(default=None, ge=1)
    allow_external_reranker: bool | None = None

    def to_planner_dict(self) -> dict:
        """Convert to the dict shape expected by build_plan(budget_spec=...)."""
        out: dict = {}
        if self.latency_ms is not None:
            out["latency_ms"] = self.latency_ms
        if self.rerank_tier is not None:
            out["rerank_tier"] = self.rerank_tier
        if self.max_evidence is not None:
            out["max_evidence"] = self.max_evidence
        if self.allow_external_reranker is not None:
            out["allow_external_reranker"] = self.allow_external_reranker
        return out


class RetrieveRequest(SearchRequest):
    token_budget: int = Field(default=DEFAULT_TOKEN_BUDGET, ge=0, le=128000)


class AnswerRequest(RetrieveRequest):
    answer_token_budget: int | None = Field(default=None, ge=1, le=128000)
    include_retrieve: bool = True


class QaConversationTurn(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)
    answer: str | None = Field(default=None, max_length=1200)


class QaAnswerRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)
    include_retrieve: bool = True
    conversation_context: list[QaConversationTurn] = Field(default_factory=list, max_length=3)


class SearchFilters(BaseModel):
    manual_id: str | None = None
    brand: str | None = None
    product_category: str | None = None
    product_model: str | None = None
    language: str | None = None
    tags: list[str] = Field(default_factory=list)

    def to_filter_dict(self) -> dict[str, object]:
        return {
            "manual_id": self.manual_id,
            "brand": self.brand,
            "product_category": self.product_category,
            "product_model": self.product_model,
            "language": self.language,
            "tags": self.tags,
        }


class RebuildRequest(BaseModel):
    docs_dir: str
    kb_name: str = "default"


class ManualMetadataValidationRequest(BaseModel):
    kb_name: str = "default"
    metadata: dict[str, object]
    mode: str = "create"
    current_manual_id: str | None = None


class ManualMetadataUpdateRequest(BaseModel):
    kb_name: str = "default"
    metadata: dict[str, object]


class ManualTagSuggestRequest(BaseModel):
    kb_name: str = "default"
    metadata: dict[str, object]
    text_sample: str = Field(default="", max_length=4000)
    limit: int = Field(default=DEFAULT_LIMIT, ge=1, le=24)


class ManualLibraryRebuildRequest(BaseModel):
    kb_name: str = "default"
    mode: str = "full"
    allow_fallback: bool = True


class TagPolicyUpdateRequest(BaseModel):
    kb_name: str = "default"
    policy: dict[str, object]


class TagRewriteRequest(BaseModel):
    kb_name: str = "default"
    source_tags: list[str]
    target_tag: str
    mode: str = "merge"
    update_policy: bool = False
    policy_alias_mode: str | None = None


class AnchorRequest(BaseModel):
    node_id: int
    label: str
    boost: float = Field(default=2.0, gt=0)
    propagation_boost: float = Field(default=1.0, gt=0)
    kb_name: str = "default"


class CacheClearRequest(BaseModel):
    kb_name: str | None = None


class EvalRunStartRequest(BaseModel):
    suite_id: str = Field(..., min_length=1, max_length=80)


class IndexGenBuildShadowRequest(BaseModel):
    kb_name: str = "default"
    docs_dir: str | None = None
    embedding_model_id: str | None = None
    embedding_model_version: str | None = None
    parser_version: str | None = None
    chunker_version: str | None = None
    index_schema_version: int | None = None


class IndexGenCancelShadowRequest(BaseModel):
    kb_name: str = "default"


class IndexGenSwapRequest(BaseModel):
    kb_name: str = "default"


class IndexGenRetireRequest(BaseModel):
    kb_name: str = "default"
    generation: int
    force: bool = False


class FeedbackSubmitRequest(BaseModel):
    kb_name: str = "default"
    trace_id: str = ""
    search_id: str = ""
    retrieve_id: str = ""
    build_id: str = ""
    query: str = Field(..., max_length=1000)
    outcome: str
    selected_results: list[dict[str, object]] = Field(default_factory=list, max_length=20)
    selected_evidence_ids: list[str] = Field(default_factory=list, max_length=20)
    selected_context_item_ids: list[str] = Field(default_factory=list, max_length=20)
    answerable: bool | None = None
    failure_reason: str = Field(default="", max_length=120)
    expected: list[dict[str, object]] = Field(default_factory=list, max_length=20)
    note: str = Field(default="", max_length=2000)
    plan_id: str | None = Field(default=None, max_length=120)


class FeedbackReviewRequest(BaseModel):
    kb_name: str = "default"
    status: str | None = None
    operator_note: str | None = Field(default=None, max_length=2000)
    expected: list[dict[str, object]] | None = Field(default=None, max_length=20)


class FeedbackPromoteRequest(BaseModel):
    kb_name: str = "default"
    feedback_ids: list[str]
    output_path: str | None = None
    append: bool = False
    overwrite: bool = False
