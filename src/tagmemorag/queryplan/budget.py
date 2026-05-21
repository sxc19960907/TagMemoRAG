"""BudgetGuard — shared deadline early-exit helper (Architecture v2 § A2 / D4).

Each long-running stage in the retrieval pipeline (retrieve / rerank /
evidence build / context pack) constructs a BudgetGuard once, then checks
exhausted() at its entry. On exhaustion the stage SHOULD return a partial
result and append a warning; it MUST NOT raise.

The deadline_at on QueryPlan.budget is monotonic-clock-relative, so this
guard is robust against system clock changes during a request.
"""

from __future__ import annotations

import time

from .plan import QueryPlan


class BudgetGuard:
    def __init__(self, plan: QueryPlan):
        self.plan = plan
        self._iterations_used = 0
        self._agent_tokens_used = 0
        self._tool_calls_used = 0

    def remaining_ms(self) -> int:
        deadline = self.plan.budget.deadline_at
        if deadline <= 0.0:
            # deadline_at not initialized: treat as full budget remaining
            return self.plan.budget.latency_ms
        return max(0, int((deadline - time.monotonic()) * 1000))

    def exhausted(self) -> bool:
        return self.remaining_ms() <= 0

    def iterations_left(self) -> int:
        return max(0, int(self.plan.budget.max_iterations) - self._iterations_used)

    def tokens_left(self) -> int:
        return max(0, int(self.plan.budget.max_agent_tokens) - self._agent_tokens_used)

    def tool_calls_left(self) -> int:
        return max(0, int(self.plan.budget.max_tool_calls) - self._tool_calls_used)

    def consume_iteration(self, count: int = 1) -> None:
        self._iterations_used += max(0, int(count))

    def consume_tokens(self, count: int) -> None:
        self._agent_tokens_used += max(0, int(count))

    def consume_tool_call(self, count: int = 1) -> None:
        self._tool_calls_used += max(0, int(count))

    def agent_exhausted(self) -> tuple[bool, str | None]:
        if self.iterations_left() <= 0:
            return True, "max_iterations"
        if self.tokens_left() <= 0:
            return True, "max_agent_tokens"
        if self.tool_calls_left() <= 0:
            return True, "max_tool_calls"
        return False, None


__all__ = ["BudgetGuard"]
