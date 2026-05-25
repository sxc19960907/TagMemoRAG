from __future__ import annotations

from dataclasses import dataclass

from tagmemorag.agentic import AgentStepCtx
from tagmemorag.agentic.state import StepRecord, ToolObservation
from tagmemorag.agentic.tools.final import FinalTool
from tagmemorag.agentic.tools.grade import GradeTool
from tagmemorag.agentic.tools.retrieve import RetrieveTool
from tagmemorag.agentic.tools.rewrite import RewriteTool
from tagmemorag.answer.base import AnswerCitation, AnswerGeneration, AnswerPrompt, AnswerRequestContext
from tagmemorag.config import Settings
from tagmemorag.queryplan import Budget, Intent, QueryPlan
from tagmemorag.queryplan.budget import BudgetGuard
from tagmemorag.reranker.base import RerankResult, RerankResultItem


def _plan() -> QueryPlan:
    return QueryPlan(
        schema_version=1,
        plan_id="p-agent",
        kb_name="kb",
        query_hash="sha256:abc",
        query_rewrites_masked=(),
        intent=Intent.TEXT_ANSWER,
        filters={},
        strategy={},
        rerank=None,
        budget=Budget(latency_ms=5000),
        created_at="2026-05-21T00:00:00Z",
    )


@dataclass
class _Settings:
    pass


def _ctx() -> AgentStepCtx:
    plan = _plan()
    return AgentStepCtx(plan=plan, guard=BudgetGuard(plan), settings=_Settings(), step_idx=0)


def test_rewrite_tool_is_identity_without_terms():
    obs = RewriteTool()({"query": "  original   query "}, _ctx())

    assert obs.payload["query"] == "original query"
    assert obs.payload["changed"] is False
    assert obs.payload["reason"] == "c3_no_terms_identity"
    assert "original_query_hash" in obs.payload


def test_rewrite_tool_appends_unique_terms():
    obs = RewriteTool()(
        {"query": "E01 pump", "append_terms": ["water tank", "pump", "water tank"], "reason": "low_signal"},
        _ctx(),
    )

    assert obs.payload["query"] == "E01 pump water tank"
    assert obs.payload["changed"] is True
    assert obs.payload["reason"] == "low_signal"


class _AnswerGenerator:
    def generate(self, context):
        return AnswerGeneration(
            "ok",
            citations=(AnswerCitation("cit_1"),),
            model_id="stub",
            prompt_version=context.prompt.prompt_version,
        )


def test_final_tool_wraps_answer_generator():
    context = AnswerRequestContext(
        question="q",
        retrieve_payload={},
        prompt=AnswerPrompt(messages=(), prompt_version="p1", allowed_citation_ids=frozenset({"cit_1"})),
        max_output_tokens=16,
    )

    obs = FinalTool(_AnswerGenerator(), context)({}, _ctx())

    assert obs.payload["answer"]["text"] == "ok"
    assert obs.payload["answer"]["citations"] == [{"citation_id": "cit_1"}]
    assert obs.tokens_consumed == 16


class _RecordingEmbedder:
    def __init__(self):
        self.queries = []

    def encode_query(self, query):
        self.queries.append(query)
        return [1.0, 0.0]


class _State:
    build_id = "build-1"
    kb_name = "kb"


def test_retrieve_tool_embeds_each_runtime_query(monkeypatch):
    calls = []

    def fake_execute_search(**kwargs):
        calls.append(kwargs)

        class _Execution:
            results = []

        return _Execution()

    monkeypatch.setattr("tagmemorag.agentic.tools.retrieve.execute_search", fake_execute_search)
    embedder = _RecordingEmbedder()
    tool = RetrieveTool(
        state=_State(),
        embedder=embedder,
        query_text="fallback query",
        top_k=3,
        source_k=3,
    )

    plan = _plan()
    ctx = AgentStepCtx(plan=plan, guard=BudgetGuard(plan), settings=Settings(), step_idx=0)
    obs = tool({"query": "rewritten steam query"}, ctx)

    assert embedder.queries == ["rewritten steam query"]
    assert calls[0]["query_text"] == "rewritten steam query"
    assert calls[0]["query_vec"] == [1.0, 0.0]
    assert obs.payload["kb_name"] == "kb"


class _ContextInspectingGenerator:
    def __init__(self):
        self.contexts = []

    def generate(self, context):
        self.contexts.append(context)
        return AnswerGeneration(
            "Use the nozzle. [cit_001] [cit_fake]",
            citations=(AnswerCitation("cit_001"), AnswerCitation("cit_fake")),
            model_id="stub",
            prompt_version=context.prompt.prompt_version,
        )


def test_final_tool_builds_context_from_latest_retrieve_and_validates_citations():
    generator = _ContextInspectingGenerator()
    retrieve_payload = {
        "citations": [{"citation_id": "cit_001"}],
        "context_pack": {
            "items": [
                {
                    "context_item_id": "ctx_001",
                    "citation_id": "cit_001",
                    "content": "Clean the steam nozzle.",
                    "source": {"source_file": "manual.md"},
                }
            ]
        },
    }
    plan = _plan()
    ctx = AgentStepCtx(
        plan=plan,
        guard=BudgetGuard(plan),
        settings=Settings(),
        step_idx=1,
        history=(
            StepRecord(
                step_idx=0,
                tool="retrieve",
                args={"query": "steam nozzle"},
                observation=ToolObservation(retrieve_payload),
                grade=None,
                decision_source="rule",
                rationale="test",
                ts="2026-05-22T00:00:00Z",
            ),
        ),
    )

    obs = FinalTool(generator, question="How do I fix weak steam?")({}, ctx)

    assert generator.contexts[0].retrieve_payload is retrieve_payload
    assert "Clean the steam nozzle." in generator.contexts[0].prompt.messages[1]["content"]
    assert obs.payload["answer"]["citations"] == [{"citation_id": "cit_001"}]
    assert "answer_dropped_invalid_citations" in obs.payload["answer"]["warnings"]


class _Dispatcher:
    def __init__(self, result: RerankResult | None = None):
        self.calls = []
        self.result = result

    def rerank(self, plan, candidates, guard, *, query_text=""):
        self.calls.append((plan, candidates, guard, query_text))
        if self.result is not None:
            return self.result
        return _rerank_result((), vendor_used="noop", cache_status="skipped", warnings=("noop_via_settings_disabled",))


def _rerank_result(items, *, vendor_used="qwen", cache_status="miss", warnings=()):
    return RerankResult(
        items=tuple(RerankResultItem(chunk_id=f"c{idx}", raw_score=score, calibrated_score=score) for idx, score in enumerate(items)),
        truncated_chunk_ids=(),
        vendor_used=vendor_used,
        cache_status=cache_status,
        latency_ms=0,
        warnings=tuple(warnings),
    )


def test_grade_tool_calls_dispatcher_and_preserves_no_signal_when_rerank_skipped():
    dispatcher = _Dispatcher()

    obs = GradeTool(dispatcher, candidates=["c1"], query_text="q")({}, _ctx())

    assert len(dispatcher.calls) == 1
    assert dispatcher.calls[0][1] == ["c1"]
    assert obs.payload["grade"]["signal"] == "no_signal"
    assert obs.payload["grade"]["reason"] == "reranker_no_signal"
    assert obs.rerank_result is not None
    assert obs.warnings == ("noop_via_settings_disabled",)


def test_grade_tool_returns_computed_low_signal():
    dispatcher = _Dispatcher(_rerank_result((0.1, 0.05)))

    obs = GradeTool(dispatcher, candidates=["c1"], query_text="q")({}, _ctx())

    assert obs.payload["grade"]["signal"] == "low"
    assert obs.payload["grade"]["reason"] == "low_score"
    assert obs.payload["grade"]["top1_score"] == 0.1
