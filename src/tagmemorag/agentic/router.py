from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from ..queryplan import Intent, QueryPlan


RouteKind = Literal["no_retrieval", "single_shot", "multi_hop"]
FeatureValue = bool | int | float | str


@dataclass(frozen=True)
class RouteDecision:
    route: RouteKind
    confidence: float
    reason: str
    features: dict[str, FeatureValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "route": self.route,
            "confidence": float(self.confidence),
            "reason": self.reason,
            "features": dict(self.features),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RouteDecision":
        return cls(
            route=str(data.get("route") or "single_shot"),  # type: ignore[arg-type]
            confidence=float(data.get("confidence") or 0.0),
            reason=str(data.get("reason") or ""),
            features=_safe_features(dict(data.get("features") or {})),
        )


class AdaptiveRouter(Protocol):
    def route(self, *, plan: QueryPlan, query_text: str) -> RouteDecision:
        ...


class RuleBasedAdaptiveRouter:
    _GREETINGS = frozenset(
        {
            "hi",
            "hello",
            "hey",
            "ok",
            "thanks",
            "thank you",
            "你好",
            "您好",
            "谢谢",
            "好的",
        }
    )
    _COMPARE_MARKERS = (
        "compare",
        "difference",
        "different",
        "versus",
        " vs ",
        "better",
        "which is",
        "哪个更",
        "哪一个更",
        "区别",
        "对比",
        "比较",
    )
    _STEP_MARKERS = (
        "first",
        "then",
        "after",
        "before",
        "based on",
        "depends on",
        "follow up",
        "再",
        "然后",
        "之后",
        "先",
        "根据",
    )
    _MODEL_PATTERN = re.compile(r"\b[a-z]{1,8}[-_ ]?\d{1,5}[a-z]?\b", re.IGNORECASE)

    def route(self, *, plan: QueryPlan, query_text: str) -> RouteDecision:
        normalized = _normalize(query_text)
        features = self._features(plan, normalized)
        if features["planner_out_of_scope"] or features["empty_query"] or features["greeting_only"]:
            return RouteDecision("no_retrieval", 0.95, "no_retrieval_rule", features)
        if features["has_compare_marker"] or features["has_step_marker"] or features["multi_entity"]:
            return RouteDecision("multi_hop", 0.75, "multi_hop_rule", features)
        return RouteDecision("single_shot", 0.6, "single_shot_default", features)

    def _features(self, plan: QueryPlan, normalized: str) -> dict[str, FeatureValue]:
        model_mentions = len(set(self._MODEL_PATTERN.findall(normalized)))
        return {
            "planner_out_of_scope": plan.intent == Intent.OUT_OF_SCOPE,
            "empty_query": normalized == "",
            "greeting_only": normalized in self._GREETINGS,
            "has_compare_marker": any(marker in normalized for marker in self._COMPARE_MARKERS),
            "has_step_marker": any(marker in normalized for marker in self._STEP_MARKERS),
            "model_mention_count": model_mentions,
            "filter_count": len(plan.filters),
            "query_token_count": len(normalized.split()),
            "multi_entity": model_mentions >= 2 or _multi_filter(plan.filters),
        }


def _normalize(text: str) -> str:
    return " ".join(text.strip().casefold().split())


def _safe_features(features: dict[str, Any]) -> dict[str, FeatureValue]:
    safe: dict[str, FeatureValue] = {}
    for key, value in features.items():
        if isinstance(value, bool | int | float | str):
            safe[str(key)] = value
    return safe


def _multi_filter(filters: dict[str, Any]) -> bool:
    for value in filters.values():
        if isinstance(value, list | tuple | set) and len(value) >= 2:
            return True
    return False


__all__ = [
    "AdaptiveRouter",
    "RouteDecision",
    "RouteKind",
    "RuleBasedAdaptiveRouter",
]
