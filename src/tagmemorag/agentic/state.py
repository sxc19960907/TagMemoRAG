from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from ..answer.base import AnswerGeneration
from ..queryplan import QueryPlan
from ..reranker.base import RerankResult


AgentSignal = Literal["high", "low", "inconclusive", "no_signal"]
DecisionSource = Literal["rule", "llm"]


@dataclass(frozen=True)
class GradeOutcome:
    top1_score: float = 0.0
    margin: float = 0.0
    depth: int = 0
    signal: AgentSignal = "no_signal"
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "top1_score": float(self.top1_score),
            "margin": float(self.margin),
            "depth": int(self.depth),
            "signal": self.signal,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GradeOutcome":
        return cls(
            top1_score=float(data.get("top1_score") or 0.0),
            margin=float(data.get("margin") or 0.0),
            depth=int(data.get("depth") or 0),
            signal=str(data.get("signal") or "no_signal"),  # type: ignore[arg-type]
            reason=str(data.get("reason") or ""),
        )


@dataclass(frozen=True)
class ToolObservation:
    payload: dict[str, Any]
    tokens_consumed: int = 0
    latency_ms: int = 0
    warnings: tuple[str, ...] = ()
    rerank_result: RerankResult | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "payload": dict(self.payload),
            "tokens_consumed": int(self.tokens_consumed),
            "latency_ms": int(self.latency_ms),
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ToolObservation":
        return cls(
            payload=dict(data.get("payload") or {}),
            tokens_consumed=int(data.get("tokens_consumed") or 0),
            latency_ms=int(data.get("latency_ms") or 0),
            warnings=tuple(str(item) for item in data.get("warnings") or ()),
        )


@dataclass(frozen=True)
class StepRecord:
    step_idx: int
    tool: str
    args: dict[str, Any]
    observation: ToolObservation
    grade: GradeOutcome | None
    decision_source: DecisionSource
    rationale: str
    ts: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_idx": int(self.step_idx),
            "tool": self.tool,
            "args": dict(self.args),
            "observation": self.observation.to_dict(),
            "grade": self.grade.to_dict() if self.grade is not None else None,
            "decision_source": self.decision_source,
            "rationale": self.rationale,
            "ts": self.ts,
        }


@dataclass(frozen=True)
class AgentStepCtx:
    plan: QueryPlan
    guard: Any
    settings: Any
    step_idx: int
    history: tuple[StepRecord, ...] = ()
    state_dir: str = ""


@dataclass
class AgentState:
    plan: QueryPlan
    history: list[StepRecord] = field(default_factory=list)
    last_retrieve_obs: ToolObservation | None = None
    last_grade: GradeOutcome | None = None
    classic_fallback_answer: AnswerGeneration | None = None
    final_answer: AnswerGeneration | None = None

    def append(self, record: StepRecord) -> None:
        self.history.append(record)
        if record.tool == "retrieve":
            self.last_retrieve_obs = record.observation
        if record.grade is not None:
            self.last_grade = record.grade

    def can_iterate(self, guard: Any) -> bool:
        exhausted, _reason = guard.agent_exhausted()
        return not exhausted

    def finalize(self) -> AnswerGeneration:
        if self.final_answer is not None:
            return self.final_answer
        if self.classic_fallback_answer is not None:
            return self.classic_fallback_answer
        raise RuntimeError("agent state has no final answer")


__all__ = [
    "AgentSignal",
    "AgentState",
    "AgentStepCtx",
    "DecisionSource",
    "GradeOutcome",
    "StepRecord",
    "ToolObservation",
]
