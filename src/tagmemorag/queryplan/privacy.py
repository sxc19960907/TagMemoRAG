"""PII masking hook for query rewrites (Architecture v2 § A2 / Decision D6).

T2 default: passthrough. The hook exists so a later operator/task can plug
masking via Settings.queryplan.pii_mask_rules without changing the planner
contract.

rules format:
    [{"pattern": r"<regex>", "replace": "<placeholder>"}, ...]
"""

from __future__ import annotations

import re


def mask_rewrites(
    rewrites: list[str] | tuple[str, ...],
    rules: list[dict] | None,
) -> tuple[str, ...]:
    """Apply PII masking to query rewrites before persistence.

    Returns a tuple of strings (frozen for QueryPlan).
    rules=None or empty → passthrough.
    """
    if not rules:
        return tuple(rewrites)
    out: list[str] = []
    for text in rewrites:
        masked = text
        for rule in rules:
            pattern = rule.get("pattern")
            replace = rule.get("replace", "[REDACTED]")
            if not pattern:
                continue
            try:
                masked = re.sub(pattern, replace, masked)
            except re.error:
                # Skip invalid patterns silently; ops should validate at deploy time.
                continue
        out.append(masked)
    return tuple(out)


__all__ = ["mask_rewrites"]
