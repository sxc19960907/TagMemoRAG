# Agentic Production Tool Wiring

## Goal

Plan production retrieve/final tool wiring for default-off agentic mode with eval and replay gates. Planning only until approved.

## Requirements

- Wire default-off agentic retrieve/final tools to production retrieval and
  answer contracts.
- Preserve C5 private-KB guard and budget fallback.
- Use agentic eval slices before any enablement.

## Acceptance Criteria

- [x] `agentic_simple_passthrough.jsonl` remains classic-equivalent where
      expected.
- [x] `agentic_multihop.jsonl`, `agentic_low_recall_recovery.jsonl`, and
      `agentic_budget_breach.jsonl` are named gates.
- [x] Replay verdict remains `match` or documented tolerated drift.
- [x] Agentic mode remains default-off.
- [x] Rollback is disabling agentic mode or reverting tool wiring.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
