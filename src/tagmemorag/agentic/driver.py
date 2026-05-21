from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..answer.base import AnswerCitation, AnswerGeneration
from ..queryplan import PlanLog, now_iso_utc
from ..queryplan.budget import BudgetGuard
from .decision import DecisionGenerator
from .router import AdaptiveRouter, RouteDecision
from .state import AgentState, AgentStepCtx, GradeOutcome, StepRecord, ToolObservation
from .tools.registry import AgentToolRegistry


@dataclass(frozen=True)
class AgentRunResult:
    answer: AnswerGeneration
    state: AgentState
    fallback_reason: str = ""


def run_agent(
    *,
    plan,
    registry: AgentToolRegistry,
    guard: BudgetGuard,
    decision_gen: DecisionGenerator,
    settings: Any,
    plan_log: PlanLog | None = None,
    initial_query: str = "",
    state_dir: str = "",
    classic_fallback: AnswerGeneration | None = None,
    router: AdaptiveRouter | None = None,
) -> AgentRunResult:
    state = AgentState(plan=plan, classic_fallback_answer=classic_fallback)

    if not getattr(plan, "persist", True):
        return _terminate_with_fallback(
            state,
            "private_kb_classic",
            plan_log=None,
            record_step=False,
        )

    if router is not None:
        route = router.route(plan=plan, query_text=initial_query)
        _append_route_step(state, route, plan_log)
        if route.route in {"single_shot", "no_retrieval"}:
            return _terminate_with_fallback(
                state,
                f"route_{route.route}",
                plan_log=plan_log,
                record_step=False,
            )

    exhausted, reason = guard.agent_exhausted()
    if exhausted:
        return _terminate_with_fallback(state, reason or "agent_budget_exhausted", plan_log=plan_log)

    current_query = initial_query
    latest_grade: GradeOutcome | None = None
    while True:
        fallback = _fallback_if_exhausted(state, guard, plan_log)
        if fallback is not None:
            return fallback
        retrieve_obs = _call_tool(
            "retrieve",
            {"query": current_query},
            registry=registry,
            state=state,
            guard=guard,
            settings=settings,
            plan_log=plan_log,
            state_dir=state_dir,
            grade=None,
            rationale="initial_retrieve" if latest_grade is None else "iterative_retrieve",
        )
        state.last_retrieve_obs = retrieve_obs

        fallback = _fallback_if_exhausted(state, guard, plan_log)
        if fallback is not None:
            return fallback
        grade_obs = _call_tool(
            "grade",
            {},
            registry=registry,
            state=state,
            guard=guard,
            settings=settings,
            plan_log=plan_log,
            state_dir=state_dir,
            grade=_extract_grade(retrieve_obs),
            rationale="c1_stub_grade" if latest_grade is None else "iterative_grade",
        )
        latest_grade = _extract_grade(grade_obs)
        state.last_grade = latest_grade

        decision = _decide_next(state, latest_grade, decision_gen)
        if decision == "final":
            break
        if decision != "rewrite":
            raise NotImplementedError("agentic non-rewrite decisions are owned by later child tasks")

        fallback = _fallback_if_exhausted(state, guard, plan_log)
        if fallback is not None:
            return fallback
        rewrite_obs = _call_tool(
            "rewrite",
            _rewrite_args(current_query, latest_grade),
            registry=registry,
            state=state,
            guard=guard,
            settings=settings,
            plan_log=plan_log,
            state_dir=state_dir,
            grade=latest_grade,
            rationale="rewrite_via_low_signal",
        )
        current_query = str(rewrite_obs.payload.get("query") or current_query)

    fallback = _fallback_if_exhausted(state, guard, plan_log)
    if fallback is not None:
        return fallback
    final_obs = _call_tool(
        "final",
        {},
        registry=registry,
        state=state,
        guard=guard,
        settings=settings,
        plan_log=plan_log,
        state_dir=state_dir,
        grade=latest_grade,
        rationale=f"final_via_{latest_grade.signal if latest_grade is not None else 'no_signal'}",
    )
    answer_payload = dict(final_obs.payload.get("answer") or {})
    answer = AnswerGeneration(
        text=str(answer_payload.get("text") or ""),
        citations=tuple(
            AnswerCitation(str(item.get("citation_id") or ""))
            for item in answer_payload.get("citations") or ()
            if isinstance(item, dict) and item.get("citation_id")
        ),
        model_id=str(answer_payload.get("model_id") or ""),
        model_version=str(answer_payload.get("model_version") or ""),
        prompt_version=str(answer_payload.get("prompt_version") or ""),
        warnings=tuple(str(item) for item in answer_payload.get("warnings") or ()),
    )
    state.final_answer = answer
    return AgentRunResult(answer=state.finalize(), state=state)


def _fallback_if_exhausted(
    state: AgentState,
    guard: BudgetGuard,
    plan_log: PlanLog | None,
) -> AgentRunResult | None:
    exhausted, reason = guard.agent_exhausted()
    if not exhausted:
        return None
    return _terminate_with_fallback(state, reason or "agent_budget_exhausted", plan_log=plan_log)


def _append_route_step(
    state: AgentState,
    route: RouteDecision,
    plan_log: PlanLog | None,
) -> None:
    record = _build_step_record(
        step_idx=len(state.history),
        tool="route",
        args={},
        observation=ToolObservation(payload={"route": route.to_dict()}),
        grade=GradeOutcome(signal="no_signal", reason="route_preflight"),
        rationale=route.reason,
    )
    state.append(record)
    if plan_log is not None:
        plan_log.append_step_async(state.plan.plan_id, record)


def _call_tool(
    name: str,
    args: dict[str, Any],
    *,
    registry: AgentToolRegistry,
    state: AgentState,
    guard: BudgetGuard,
    settings: Any,
    plan_log: PlanLog | None,
    state_dir: str,
    grade: GradeOutcome | None,
    rationale: str,
) -> ToolObservation:
    exhausted, reason = guard.agent_exhausted()
    if exhausted:
        raise RuntimeError(f"agentic budget exhausted before {name}: {reason}")
    guard.consume_iteration()
    guard.consume_tool_call()
    ctx = AgentStepCtx(
        plan=state.plan,
        guard=guard,
        settings=settings,
        step_idx=len(state.history),
        history=tuple(state.history),
        state_dir=state_dir,
    )
    obs = registry.get(name)(args, ctx)
    guard.consume_tokens(obs.tokens_consumed)
    record_grade = _extract_grade(obs) if name == "grade" else grade
    record = _build_step_record(
        step_idx=len(state.history),
        tool=name,
        args=args,
        observation=obs,
        grade=record_grade,
        rationale=rationale,
    )
    state.append(record)
    if plan_log is not None:
        plan_log.append_step_async(state.plan.plan_id, record)
    return obs


def _build_step_record(
    *,
    step_idx: int,
    tool: str,
    args: dict[str, Any],
    observation: ToolObservation,
    grade: GradeOutcome | None,
    rationale: str,
) -> StepRecord:
    return StepRecord(
        step_idx=step_idx,
        tool=tool,
        args=args,
        observation=observation,
        grade=grade,
        decision_source="rule",
        rationale=rationale,
        ts=now_iso_utc(),
    )


def _extract_grade(obs: ToolObservation) -> GradeOutcome:
    grade = dict(obs.payload.get("grade") or {})
    if not grade:
        return GradeOutcome(signal="no_signal", reason="c1_stub")
    return GradeOutcome.from_dict(grade)


def _decide_next(state: AgentState, grade: GradeOutcome, decision_gen: DecisionGenerator) -> str:
    if grade.signal in {"no_signal", "high", "inconclusive"}:
        return "final"
    if grade.signal == "low":
        return "rewrite"
    decision = decision_gen.choose_tool(state, AgentToolRegistry())
    if decision is not None:
        return decision.tool
    raise NotImplementedError("agentic non-no_signal decisions are owned by later child tasks")


def _rewrite_args(query: str, grade: GradeOutcome) -> dict[str, Any]:
    args: dict[str, Any] = {"query": query, "reason": grade.reason or "low_signal"}
    if grade.reason:
        args["append_terms"] = [grade.reason]
    return args


def _terminate_with_fallback(
    state: AgentState,
    reason: str,
    *,
    plan_log: PlanLog | None = None,
    record_step: bool = True,
) -> AgentRunResult:
    if state.classic_fallback_answer is None:
        raise RuntimeError(f"agentic fallback unavailable: {reason}")
    if record_step and getattr(state.plan, "persist", True):
        record = _build_step_record(
            step_idx=len(state.history),
            tool="fallback",
            args={},
            observation=ToolObservation(payload={"reason": reason, "history_len": len(state.history)}),
            grade=GradeOutcome(signal="no_signal", reason=reason),
            rationale=f"fallback:{reason}",
        )
        state.append(record)
        if plan_log is not None:
            plan_log.append_step_async(state.plan.plan_id, record)
    return AgentRunResult(
        answer=state.classic_fallback_answer,
        state=state,
        fallback_reason=reason,
    )


__all__ = ["AgentRunResult", "run_agent"]
