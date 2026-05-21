from __future__ import annotations

from dataclasses import dataclass

from tagmemorag.agentic import AgentStepCtx
from tagmemorag.agentic.tools.final import FinalTool
from tagmemorag.agentic.tools.grade import GradeTool
from tagmemorag.agentic.tools.rewrite import RewriteTool
from tagmemorag.answer.base import AnswerCitation, AnswerGeneration, AnswerPrompt, AnswerRequestContext
from tagmemorag.queryplan import Budget, Intent, QueryPlan
from tagmemorag.queryplan.budget import BudgetGuard
from tagmemorag.reranker.base import RerankResult


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


def test_rewrite_tool_is_identity_stub():
    obs = RewriteTool()({"query": "original"}, _ctx())

    assert obs.payload == {"query": "original", "reason": "c1_stub_identity"}


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
        prompt=AnswerPrompt(messages=(), prompt_version="p1"),
        max_output_tokens=16,
    )

    obs = FinalTool(_AnswerGenerator(), context)({}, _ctx())

    assert obs.payload["answer"]["text"] == "ok"
    assert obs.payload["answer"]["citations"] == [{"citation_id": "cit_1"}]
    assert obs.tokens_consumed == 16


class _Dispatcher:
    def __init__(self):
        self.calls = []

    def rerank(self, plan, candidates, guard, *, query_text=""):
        self.calls.append((plan, candidates, guard, query_text))
        return RerankResult(
            items=(),
            truncated_chunk_ids=(),
            vendor_used="noop",
            cache_status="skipped",
            latency_ms=0,
            warnings=("noop_via_settings_disabled",),
        )


def test_grade_tool_calls_dispatcher_and_forces_no_signal():
    dispatcher = _Dispatcher()

    obs = GradeTool(dispatcher, candidates=["c1"], query_text="q")({}, _ctx())

    assert len(dispatcher.calls) == 1
    assert dispatcher.calls[0][1] == ["c1"]
    assert obs.payload["grade"]["signal"] == "no_signal"
    assert obs.payload["grade"]["reason"] == "c1_stub"
    assert obs.rerank_result is not None
    assert obs.warnings == ("noop_via_settings_disabled",)
