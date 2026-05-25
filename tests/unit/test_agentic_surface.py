from __future__ import annotations

from tagmemorag.agentic.surface import resolve_agentic_mode, stamp_plan_mode
from tagmemorag.config import Settings
from tagmemorag.queryplan import build_plan


def test_mode_resolution_precedence():
    assert resolve_agentic_mode(settings_mode="classic").mode == "classic"
    forced = resolve_agentic_mode(settings_mode="classic", forced_mode="agentic", forced_reason="eval")
    assert forced.mode == "agentic"
    assert forced.source == "forced"
    request = resolve_agentic_mode(settings_mode="classic", forced_mode="agentic", request_mode="classic")
    assert request.mode == "classic"
    assert request.source == "request"


def test_stamp_plan_mode_adds_safe_metadata():
    plan = build_plan("secret question", "default", Settings(model={"provider": "hashing"}))
    resolution = resolve_agentic_mode(settings_mode="classic", forced_mode="agentic", forced_reason="eval_cli")

    stamped = stamp_plan_mode(plan, resolution)

    assert stamped.strategy["mode"] == "agentic"
    assert stamped.strategy["mode_source"] == "forced"
    assert stamped.strategy["forced_mode"] == "agentic"
    assert stamped.strategy["forced_mode_reason"] == "eval_cli"
    assert "secret question" not in str(stamped.strategy)
