from __future__ import annotations

from pathlib import Path

import pytest

from tagmemorag.agentic import AgentStepCtx, ToolObservation, run_agent
from tagmemorag.agentic.decision import RuleOnlyDecisionGenerator
from tagmemorag.agentic.router import RouteDecision
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


class _GradeTool(_Tool):
    def __init__(self, signals):
        super().__init__("grade", {})
        self.signals = list(signals)

    def __call__(self, args: dict, ctx: AgentStepCtx) -> ToolObservation:
        signal, reason = self.signals.pop(0)
        self.calls.append((args, ctx.step_idx))
        return ToolObservation({"grade": {"signal": signal, "reason": reason}})


class _Decision(RuleOnlyDecisionGenerator):
    def __init__(self):
        self.called = False

    def choose_tool(self, state, registry):
        self.called = True
        return super().choose_tool(state, registry)


class _Router:
    def __init__(self, route: str):
        self.route_kind = route
        self.calls = []

    def route(self, *, plan, query_text: str) -> RouteDecision:
        self.calls.append((plan.plan_id, query_text))
        return RouteDecision(self.route_kind, 0.9, f"{self.route_kind}_rule")


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


def _iterative_registry(signals=(("low", "water tank"), ("no_signal", "c3_done"))):
    registry = AgentToolRegistry()
    retrieve = _Tool("retrieve", {"results": []})
    grade = _GradeTool(signals)
    rewrite = _Tool("rewrite", {"query": "q water tank", "changed": True})
    final = _Tool(
        "final",
        {
            "answer": {
                "kind": "answer",
                "text": "ok",
                "citations": [],
                "model_id": "stub",
                "model_version": "",
                "prompt_version": "p1",
                "warnings": [],
            }
        },
    )
    for tool in (retrieve, grade, rewrite, final):
        registry.register(tool)
    return registry, retrieve, grade, rewrite, final


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


def test_router_single_shot_returns_classic_fallback_without_tool_calls():
    registry, retrieve, grade, final = _registry()
    router = _Router("single_shot")
    plan = _plan()
    fallback = AnswerGeneration("fallback")

    result = run_agent(
        plan=plan,
        registry=registry,
        guard=BudgetGuard(plan),
        decision_gen=RuleOnlyDecisionGenerator(),
        settings=object(),
        initial_query="q",
        classic_fallback=fallback,
        router=router,
    )

    assert result.answer is fallback
    assert result.fallback_reason == "route_single_shot"
    assert [record.tool for record in result.state.history] == ["route"]
    assert result.state.history[0].observation.payload["route"]["route"] == "single_shot"
    assert router.calls == [(plan.plan_id, "q")]
    assert not retrieve.calls
    assert not grade.calls
    assert not final.calls


def test_router_single_shot_writes_only_route_step(tmp_path: Path):
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
        classic_fallback=AnswerGeneration("fallback"),
        router=_Router("single_shot"),
    )
    log._writer.flush()

    steps = log.load_steps(plan.plan_id)
    assert [step.tool for step in steps] == ["route"]
    assert steps[0].decision_source == "rule"
    assert steps[0].grade is not None
    assert steps[0].grade.signal == "no_signal"
    assert steps[0].rationale == "single_shot_rule"


def test_router_multi_hop_continues_c1_loop_after_route_step():
    registry, retrieve, grade, final = _registry()
    plan = _plan()

    result = run_agent(
        plan=plan,
        registry=registry,
        guard=BudgetGuard(plan),
        decision_gen=RuleOnlyDecisionGenerator(),
        settings=object(),
        initial_query="q",
        router=_Router("multi_hop"),
    )

    assert result.answer.text == "ok"
    assert [record.tool for record in result.state.history] == ["route", "retrieve", "grade", "final"]
    assert retrieve.calls[0][1] == 1


def test_low_signal_runs_rewrite_then_second_retrieve():
    registry, retrieve, grade, rewrite, final = _iterative_registry()
    plan = _plan(budget=Budget(latency_ms=5000, max_iterations=8, max_tool_calls=8))

    result = run_agent(
        plan=plan,
        registry=registry,
        guard=BudgetGuard(plan),
        decision_gen=RuleOnlyDecisionGenerator(),
        settings=object(),
        initial_query="q",
    )

    assert result.answer.text == "ok"
    assert [record.tool for record in result.state.history] == [
        "retrieve",
        "grade",
        "rewrite",
        "retrieve",
        "grade",
        "final",
    ]
    assert retrieve.calls[0][0] == {"query": "q"}
    assert rewrite.calls[0][0] == {"query": "q", "reason": "water tank", "append_terms": ["water tank"]}
    assert retrieve.calls[1][0] == {"query": "q water tank"}
    assert grade.calls[0][1] == 1
    assert grade.calls[1][1] == 4
    assert final.calls


def test_router_multi_hop_composes_with_iterative_loop():
    registry, retrieve, _grade, _rewrite, _final = _iterative_registry()
    plan = _plan(budget=Budget(latency_ms=5000, max_iterations=8, max_tool_calls=8))

    result = run_agent(
        plan=plan,
        registry=registry,
        guard=BudgetGuard(plan),
        decision_gen=RuleOnlyDecisionGenerator(),
        settings=object(),
        initial_query="q",
        router=_Router("multi_hop"),
    )

    assert [record.tool for record in result.state.history] == [
        "route",
        "retrieve",
        "grade",
        "rewrite",
        "retrieve",
        "grade",
        "final",
    ]
    assert retrieve.calls[0][1] == 1
    assert retrieve.calls[1][1] == 4


def test_low_signal_budget_exhaustion_returns_classic_fallback():
    registry, retrieve, grade, rewrite, final = _iterative_registry()
    plan = _plan(budget=Budget(latency_ms=5000, max_iterations=3, max_tool_calls=3))
    fallback = AnswerGeneration("fallback")

    result = run_agent(
        plan=plan,
        registry=registry,
        guard=BudgetGuard(plan),
        decision_gen=RuleOnlyDecisionGenerator(),
        settings=object(),
        initial_query="q",
        classic_fallback=fallback,
    )

    assert result.answer is fallback
    assert result.fallback_reason == "max_iterations"
    assert [record.tool for record in result.state.history] == ["retrieve", "grade", "rewrite"]
    assert retrieve.calls
    assert grade.calls
    assert rewrite.calls
    assert not final.calls


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


def test_router_short_circuit_without_fallback_is_error():
    registry, *_tools = _registry()
    plan = _plan()

    with pytest.raises(RuntimeError, match="fallback unavailable: route_single_shot"):
        run_agent(
            plan=plan,
            registry=registry,
            guard=BudgetGuard(plan),
            decision_gen=RuleOnlyDecisionGenerator(),
            settings=object(),
            router=_Router("single_shot"),
        )
