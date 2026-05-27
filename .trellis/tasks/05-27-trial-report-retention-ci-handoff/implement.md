# Trial Report Retention CI Handoff Implementation Plan

## Steps

1. Start the child task after reading specs.
2. Add a concise report/CI handoff doc.
3. Link it from README, trial operator handoff, and RAG quality gates.
4. Add a focused docs test for required command/path/CI strings.
5. Validate and archive.

## Validation

- `python3 -m py_compile tests/unit/test_documentation_handoffs.py`
- `uv run pytest tests/unit/test_documentation_handoffs.py -q`
- `git diff --check`
