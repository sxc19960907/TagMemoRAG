from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .state import StepRecord


@dataclass(frozen=True)
class StepReplayVerdict:
    step_idx: int
    tool_match: bool
    signal_match: bool
    args_schema_match: bool
    decision_source_match: bool
    verdict: str

    def to_dict(self) -> dict:
        return {
            "step_idx": self.step_idx,
            "tool_match": self.tool_match,
            "signal_match": self.signal_match,
            "args_schema_match": self.args_schema_match,
            "decision_source_match": self.decision_source_match,
            "verdict": self.verdict,
        }


@dataclass(frozen=True)
class AgentRunReplayVerdict:
    plan_id: str
    overall: str
    steps: tuple[StepReplayVerdict, ...]

    def to_dict(self) -> dict:
        return {
            "plan_id": self.plan_id,
            "overall": self.overall,
            "steps": [step.to_dict() for step in self.steps],
        }


def replay_steps(plan_id: str, steps: Iterable[StepRecord]) -> AgentRunReplayVerdict:
    verdicts = tuple(_replay_step(step) for step in steps)
    overall = "match" if all(step.verdict == "match" for step in verdicts) else "diverged"
    return AgentRunReplayVerdict(plan_id=plan_id, overall=overall, steps=verdicts)


def _replay_step(step: StepRecord) -> StepReplayVerdict:
    tool_match = bool(step.tool)
    signal_match = step.grade is None or step.grade.signal in {"high", "low", "inconclusive", "no_signal"}
    args_schema_match = isinstance(step.args, dict)
    decision_source_match = step.decision_source in {"rule", "llm"}
    matched = tool_match and signal_match and args_schema_match and decision_source_match
    return StepReplayVerdict(
        step_idx=step.step_idx,
        tool_match=tool_match,
        signal_match=signal_match,
        args_schema_match=args_schema_match,
        decision_source_match=decision_source_match,
        verdict="match" if matched else "diverged",
    )


__all__ = ["AgentRunReplayVerdict", "StepReplayVerdict", "replay_steps"]
