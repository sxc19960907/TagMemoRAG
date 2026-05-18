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

    def remaining_ms(self) -> int:
        deadline = self.plan.budget.deadline_at
        if deadline <= 0.0:
            # deadline_at not initialized: treat as full budget remaining
            return self.plan.budget.latency_ms
        return max(0, int((deadline - time.monotonic()) * 1000))

    def exhausted(self) -> bool:
        return self.remaining_ms() <= 0


__all__ = ["BudgetGuard"]
