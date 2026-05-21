from __future__ import annotations

from tagmemorag.agentic.replay import replay_steps
from tagmemorag.agentic.state import GradeOutcome, StepRecord, ToolObservation


def _step() -> StepRecord:
    return StepRecord(
        step_idx=0,
        tool="retrieve",
        args={"query": "masked"},
        observation=ToolObservation({"result_count": 1}),
        grade=GradeOutcome(signal="no_signal", reason="c1_stub"),
        decision_source="rule",
        rationale="initial_retrieve",
        ts="2026-05-21T00:00:00Z",
    )


def test_replay_steps_match_rule_driven_stub_step():
    verdict = replay_steps("plan-1", [_step()])

    assert verdict.overall == "match"
    assert verdict.steps[0].tool_match is True
    assert verdict.steps[0].signal_match is True
    assert verdict.steps[0].args_schema_match is True
    assert verdict.steps[0].decision_source_match is True
    assert verdict.to_dict()["steps"][0]["verdict"] == "match"
