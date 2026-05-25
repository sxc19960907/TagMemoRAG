# RAG Answer Quality Diagnostics — Implementation Plan

## Operating Rules

- Keep diagnostics optional and offline by default.
- Preserve existing `/answer`, `/retrieve`, ranking eval, and baselines unless
  this task explicitly adds a new answer-quality fixture.
- Use a deterministic local/fake judge for tests.
- Keep report fields bounded and safe.

## Steps

### Step 1 — Inspect Existing Eval and CLI Surfaces

- Locate current eval package, CLI dispatch, JSONL loading helpers, and report
  writing conventions.
- Locate current answer prompt/citation validation tests to reuse contracts.
- Decide whether the entry point belongs under `python -m tagmemorag eval ...`
  or a project script wrapper.

Output:

- implementation notes in `implement.jsonl` or task journal if discoveries
  affect scope.

### Step 2 — Add Diagnostics Contracts

- Add dataclasses/types for answer-quality cases, per-case results, summary,
  and report.
- Add JSONL loader and report writer.
- Add local/fake judge implementation.
- Enforce bounded warnings and failure reasons.

### Step 3 — Add CLI or Script Entry Point

- Wire a command that accepts:
  - `--suite`
  - `--output`
  - optional `--format json` if existing eval style uses formats.
- Ensure output directories are created safely.
- Print a compact summary without raw snippets by default.

### Step 4 — Add Fixtures and Tests

- Add at least one grounded and one ungrounded fixture case.
- Add unit tests for:
  - fixture loading;
  - grounded case pass;
  - ungrounded case fail;
  - citation support missing/unknown citation;
  - report schema and safe bounded fields;
  - CLI output/report creation.
- Add provider/env skip test only if a provider-gated judge boundary is
  implemented in this task.

### Step 5 — Validate and Document

- Run focused tests first.
- Run answer API/prompt tests to prove default behavior unchanged.
- Run eval-related tests if command wiring touches shared eval code.
- Update docs only if a user-facing command is added.

## Validation Commands

Exact test names may change after inspection. Start with:

```bash
uv run pytest tests/unit -k "answer_quality or answer"
uv run pytest tests/unit/test_eval*.py
git diff --check
```

If a CLI command is added:

```bash
uv run python -m tagmemorag eval answer-quality \
  --suite tests/fixtures/answer_quality/basic.jsonl \
  --output .tmp/answer-quality/report.json
```

## Exit Criteria

- [x] Diagnostics report schema is bounded and safe.
- [x] Existing answer API and prompt behavior are unchanged by default.
- [x] At least one grounded and one ungrounded fixture are defined.
- [x] Provider/env requirements are explicit and skip safely when absent.
- [x] Rollback leaves existing ranking eval unchanged.
