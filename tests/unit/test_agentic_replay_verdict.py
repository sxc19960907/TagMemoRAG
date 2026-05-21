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


def test_replay_steps_match_rule_driven_route_step():
    step = StepRecord(
        step_idx=0,
        tool="route",
        args={},
        observation=ToolObservation({"route": {"route": "single_shot"}}),
        grade=GradeOutcome(signal="no_signal", reason="route_preflight"),
        decision_source="rule",
        rationale="single_shot_default",
        ts="2026-05-21T00:00:00Z",
    )

    verdict = replay_steps("plan-1", [step])

    assert verdict.overall == "match"
    assert verdict.steps[0].tool_match is True
    assert verdict.steps[0].verdict == "match"


def test_replay_steps_match_rewrite_sequence():
    steps = [
        StepRecord(
            step_idx=0,
            tool="retrieve",
            args={"query": "q"},
            observation=ToolObservation({"result_count": 1}),
            grade=None,
            decision_source="rule",
            rationale="initial_retrieve",
            ts="2026-05-21T00:00:00Z",
        ),
        StepRecord(
            step_idx=1,
            tool="rewrite",
            args={"query": "q", "append_terms": ["pump"]},
            observation=ToolObservation({"query": "q pump", "changed": True}),
            grade=GradeOutcome(signal="low", reason="pump"),
            decision_source="rule",
            rationale="rewrite_via_low_signal",
            ts="2026-05-21T00:00:01Z",
        ),
        StepRecord(
            step_idx=2,
            tool="retrieve",
            args={"query": "q pump"},
            observation=ToolObservation({"result_count": 2}),
            grade=None,
            decision_source="rule",
            rationale="iterative_retrieve",
            ts="2026-05-21T00:00:02Z",
        ),
    ]

    verdict = replay_steps("plan-1", steps)

    assert verdict.overall == "match"
    assert [step.verdict for step in verdict.steps] == ["match", "match", "match"]
