from __future__ import annotations

from pathlib import Path

import pytest

from tagmemorag.agentic import AgentStepCtx, ToolObservation, run_agent
from tagmemorag.agentic.decision import RuleOnlyDecisionGenerator
from tagmemorag.agentic.tools import AgentToolRegistry
from tagmemorag.answer.base import AnswerCitation, AnswerGeneration
from tagmemorag.config import Settings, StorageConfig
from tagmemorag.queryplan import Budget, Intent, PlanLog, QueryPlan
from tagmemorag.queryplan.budget import BudgetGuard
from tagmemorag.queryplan.plan_log import _reset_shared_writer_for_tests


def _plan(**kwargs) -> QueryPlan:
    budget = kwargs.pop("budget", Budget(latency_ms=5000, max_iterations=5, max_tool_calls=5))
    return QueryPlan(
        schema_version=1,
        plan_id=kwargs.pop("plan_id", "agent-plan"),
        kb_name="kb",
        query_hash="sha256:abc",
        query_rewrites_masked=(),
        intent=Intent.TEXT_ANSWER,
        filters={},
        strategy={},
        rerank=None,
        budget=budget,
        created_at="2026-05-21T00:00:00Z",
        **kwargs,
    )


class _Tool:
    def __init__(self, name, payload):
        self.name = name
        self.description = name
        self.input_schema = {"type": "object", "properties": {}}
        self.calls = []
        self.payload = payload

    def __call__(self, args: dict, ctx: AgentStepCtx) -> ToolObservation:
        self.calls.append((args, ctx.step_idx))
        return ToolObservation(self.payload)


class _Decision(RuleOnlyDecisionGenerator):
    def __init__(self):
        self.called = False

    def choose_tool(self, state, registry):
        self.called = True
        return super().choose_tool(state, registry)


def _registry():
    registry = AgentToolRegistry()
    retrieve = _Tool("retrieve", {"results": []})
    grade = _Tool("grade", {"grade": {"signal": "no_signal", "reason": "c1_stub"}})
    final = _Tool(
        "final",
        {
            "answer": {
                "kind": "answer",
                "text": "ok",
                "citations": [{"citation_id": "cit_1"}],
                "model_id": "stub",
                "model_version": "",
                "prompt_version": "p1",
                "warnings": [],
            }
        },
    )
    registry.register(retrieve)
    registry.register(grade)
    registry.register(final)
    return registry, retrieve, grade, final


def test_runs_retrieve_grade_then_final_on_no_signal_stub():
    registry, retrieve, grade, final = _registry()
    decision = _Decision()
    plan = _plan()

    result = run_agent(
        plan=plan,
        registry=registry,
        guard=BudgetGuard(plan),
        decision_gen=decision,
        settings=object(),
        initial_query="q",
    )

    assert result.answer.text == "ok"
    assert result.answer.citations == (AnswerCitation("cit_1"),)
    assert [record.tool for record in result.state.history] == ["retrieve", "grade", "final"]
    assert retrieve.calls[0][0] == {"query": "q"}
    assert grade.calls
    assert final.calls
    assert decision.called is False


def test_writes_one_step_record_per_tool(tmp_path: Path):
    _reset_shared_writer_for_tests()
    registry, *_tools = _registry()
    settings = Settings(storage=StorageConfig(data_dir=str(tmp_path / "data")))
    log = PlanLog("kb", settings)
    plan = _plan()
    log.insert_basic(plan)

    run_agent(
        plan=plan,
        registry=registry,
        guard=BudgetGuard(plan),
        decision_gen=RuleOnlyDecisionGenerator(),
        settings=settings,
        plan_log=log,
        initial_query="q",
    )
    log._writer.flush()

    steps = log.load_steps(plan.plan_id)
    assert [step.tool for step in steps] == ["retrieve", "grade", "final"]
    assert all(step.decision_source == "rule" for step in steps)


def test_budget_iteration_exhaustion_triggers_classic_fallback():
    registry, *_tools = _registry()
    plan = _plan(budget=Budget(latency_ms=5000, max_iterations=0, max_tool_calls=5))
    fallback = AnswerGeneration("fallback")

    result = run_agent(
        plan=plan,
        registry=registry,
        guard=BudgetGuard(plan),
        decision_gen=RuleOnlyDecisionGenerator(),
        settings=object(),
        classic_fallback=fallback,
    )

    assert result.answer is fallback
    assert result.fallback_reason == "max_iterations"


def test_budget_tool_call_exhaustion_stops_before_next_tool():
    registry, retrieve, grade, final = _registry()
    plan = _plan(budget=Budget(latency_ms=5000, max_iterations=5, max_tool_calls=2))

    with pytest.raises(RuntimeError, match="before final: max_tool_calls"):
        run_agent(
            plan=plan,
            registry=registry,
            guard=BudgetGuard(plan),
            decision_gen=RuleOnlyDecisionGenerator(),
            settings=object(),
            initial_query="q",
        )

    assert retrieve.calls
    assert grade.calls
    assert not final.calls


def test_budget_exhaustion_without_fallback_is_error():
    registry, *_tools = _registry()
    plan = _plan(budget=Budget(latency_ms=5000, max_iterations=0, max_tool_calls=5))

    with pytest.raises(RuntimeError):
        run_agent(
            plan=plan,
            registry=registry,
            guard=BudgetGuard(plan),
            decision_gen=RuleOnlyDecisionGenerator(),
            settings=object(),
        )
