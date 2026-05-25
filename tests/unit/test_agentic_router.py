from __future__ import annotations

from tagmemorag.agentic.router import RouteDecision, RuleBasedAdaptiveRouter
from tagmemorag.eval.dataset import load_eval_suite
from tagmemorag.queryplan import Budget, Intent, QueryPlan


def _plan(**kwargs) -> QueryPlan:
    return QueryPlan(
        schema_version=1,
        plan_id=kwargs.pop("plan_id", "route-plan"),
        kb_name="default",
        query_hash="sha256:abc",
        query_rewrites_masked=(),
        intent=kwargs.pop("intent", Intent.TEXT_ANSWER),
        filters=kwargs.pop("filters", {}),
        strategy=kwargs.pop("strategy", {}),
        rerank=None,
        budget=Budget(latency_ms=5000),
        created_at="2026-05-21T00:00:00Z",
        **kwargs,
    )


def test_route_decision_round_trips_safe_payload():
    decision = RouteDecision(
        route="multi_hop",
        confidence=0.75,
        reason="multi_hop_rule",
        features={"has_compare_marker": True, "query_token_count": 4},
    )

    payload = decision.to_dict()
    assert payload == {
        "route": "multi_hop",
        "confidence": 0.75,
        "reason": "multi_hop_rule",
        "features": {"has_compare_marker": True, "query_token_count": 4},
    }
    assert RouteDecision.from_dict(payload) == decision


def test_rule_router_single_shot_for_agentic_simple_passthrough():
    router = RuleBasedAdaptiveRouter()
    plan = _plan()

    for case in load_eval_suite("tests/fixtures/eval/agentic_simple_passthrough.jsonl"):
        decision = router.route(plan=plan, query_text=case.query)
        assert decision.route == "single_shot", case.id


def test_rule_router_multi_hop_markers():
    router = RuleBasedAdaptiveRouter()
    plan = _plan()

    assert router.route(plan=plan, query_text="Compare WM8 and DW2 drain faults").route == "multi_hop"
    assert router.route(plan=plan, query_text="先根据 E01 检查水箱，再看泵的问题").route == "multi_hop"
    assert router.route(plan=_plan(filters={"manual_id": ["washer-a", "washer-b"]}), query_text="drain pump").route == "multi_hop"


def test_rule_router_no_retrieval_empty_greeting_out_of_scope():
    router = RuleBasedAdaptiveRouter()

    assert router.route(plan=_plan(), query_text="   ").route == "no_retrieval"
    assert router.route(plan=_plan(), query_text="你好").route == "no_retrieval"
    assert router.route(plan=_plan(intent=Intent.OUT_OF_SCOPE), query_text="weather tomorrow").route == "no_retrieval"
