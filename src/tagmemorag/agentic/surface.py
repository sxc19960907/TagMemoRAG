from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

from ..queryplan import QueryPlan

AgenticMode = Literal["classic", "agentic"]


@dataclass(frozen=True)
class ModeResolution:
    mode: AgenticMode
    source: Literal["request", "forced", "settings"]
    reason: str = ""


def resolve_agentic_mode(
    *,
    settings_mode: AgenticMode,
    request_mode: AgenticMode | None = None,
    forced_mode: AgenticMode | None = None,
    forced_reason: str = "forced_mode",
) -> ModeResolution:
    if request_mode is not None:
        return ModeResolution(request_mode, "request", "request_override")
    if forced_mode is not None:
        return ModeResolution(forced_mode, "forced", forced_reason)
    return ModeResolution(settings_mode, "settings", "settings_default")


def stamp_plan_mode(plan: QueryPlan, resolution: ModeResolution) -> QueryPlan:
    strategy = dict(plan.strategy)
    strategy["mode"] = resolution.mode
    strategy["mode_source"] = resolution.source
    if resolution.source == "forced":
        strategy["forced_mode"] = resolution.mode
        strategy["forced_mode_reason"] = resolution.reason
    elif resolution.source == "request":
        strategy["request_mode"] = resolution.mode
        strategy["request_mode_reason"] = resolution.reason
    return replace(plan, strategy=strategy)


__all__ = ["AgenticMode", "ModeResolution", "resolve_agentic_mode", "stamp_plan_mode"]
