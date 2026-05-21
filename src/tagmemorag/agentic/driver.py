from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..answer.base import AnswerCitation, AnswerGeneration
from ..queryplan import PlanLog, now_iso_utc
from ..queryplan.budget import BudgetGuard
from .decision import DecisionGenerator
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
) -> AgentRunResult:
    state = AgentState(plan=plan, classic_fallback_answer=classic_fallback)

    exhausted, reason = guard.agent_exhausted()
    if exhausted:
        return _terminate_with_classic_fallback(state, reason or "agent_budget_exhausted")

    retrieve_obs = _call_tool(
        "retrieve",
        {"query": initial_query},
        registry=registry,
        state=state,
        guard=guard,
        settings=settings,
        plan_log=plan_log,
        state_dir=state_dir,
        grade=None,
        rationale="initial_retrieve",
    )
    state.last_retrieve_obs = retrieve_obs

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
        rationale="c1_stub_grade",
    )
    grade = _extract_grade(grade_obs)
    state.last_grade = grade

    decision = _decide_next(state, grade, decision_gen)
    if decision != "final":
        raise NotImplementedError("agentic non-final decisions are owned by later child tasks")

    final_obs = _call_tool(
        "final",
        {},
        registry=registry,
        state=state,
        guard=guard,
        settings=settings,
        plan_log=plan_log,
        state_dir=state_dir,
        grade=grade,
        rationale="final_via_no_signal",
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
    record = _build_step_record(
        step_idx=len(state.history),
        tool=name,
        args=args,
        observation=obs,
        grade=grade,
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
    if grade.signal == "no_signal":
        return "final"
    decision = decision_gen.choose_tool(state, AgentToolRegistry())
    if decision is not None:
        return decision.tool
    raise NotImplementedError("agentic non-no_signal decisions are owned by later child tasks")


def _terminate_with_classic_fallback(state: AgentState, reason: str) -> AgentRunResult:
    if state.classic_fallback_answer is None:
        raise RuntimeError(f"agentic budget exhausted without fallback: {reason}")
    return AgentRunResult(
        answer=state.classic_fallback_answer,
        state=state,
        fallback_reason=reason,
    )


__all__ = ["AgentRunResult", "run_agent"]
