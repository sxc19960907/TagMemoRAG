# Prompt and Context Pack Quality Review — Implementation Plan

## Operating Rules

- Use diagnostics and tests, not prompt taste alone.
- Keep prompt/context changes bounded and reversible.
- Preserve `/answer` schema and citation validation.
- Keep tests offline; skip live provider checks unless explicit env gates exist.

## Steps

### Step 1 — Baseline Existing Prompt and Diagnostics

- Read answer prompt/API tests.
- Run current answer-quality diagnostics.
- Identify missing citation/conflict cases.

### Step 2 — Add Diagnostic Fixtures

- Add answer-quality cases for citation miss and conflicting evidence.
- Ensure reports remain bounded and do not include full context snippets.

### Step 3 — Tighten Prompt Instructions

- Update system prompt with explicit citation support, conflict, and refusal
  instructions.
- Keep retrieved context in user message only.

### Step 4 — Tests

- Add prompt assertions for new instructions.
- Update answer-quality expectations for new cases.
- Run answer API/generator tests.

## Validation Commands

```bash
uv run python -m tagmemorag eval answer-quality \
  --suite tests/fixtures/answer_quality/basic.jsonl \
  --output .tmp/answer-quality/report.json
uv run pytest tests/unit/test_answer_prompt.py tests/unit/test_answer_quality_eval.py tests/unit/test_answer_api.py tests/unit/test_answer_generator.py
uv run pytest tests/unit tests/e2e --ignore=tests/e2e/test_perf.py
git diff --check
```

## Exit Criteria

- [x] New fixture cases cover citation miss and conflicting evidence.
- [x] Answer prompt tests and answer API tests are named gates.
- [x] If live DeepSeek verification is used, env gating and cost controls are
      explicit.
- [x] Context pack changes are bounded and reversible.
- [x] Rollback is reverting prompt/context changes.
