# RAG Trial Operations And Feedback Hardening Implementation Plan

## Ordered Work

- [x] Create and complete child task 1: trial handoff and operator dashboard review.
- [x] Create and complete child task 2: feedback triage workflow hardening.
- [x] Create and complete child task 3: upload/rebuild failure recovery black-box review.
- [x] Create and complete child task 4: eval promotion quality review from real feedback.
- [x] Create and complete child task 5: auth and role boundary trial review.
- [x] Create and complete child task 6: trial report retention and CI handoff.
- [ ] Create and complete child task 7: final trial readiness review and GitHub/CI follow-up.

## Validation Pattern

Each child task should define focused commands. The recurring baseline is:

```bash
python3 -m py_compile <changed-python-files>
node --check <changed-js-files>
uv run pytest <focused-tests> -q
uv run python -m tagmemorag readiness browser-qa
git diff --check
```

For trial readiness/report work, also prefer:

```bash
uv run python -m tagmemorag pilot run --config examples/config/local-hashing-npz.yaml --suite tests/fixtures/eval/coffee.jsonl --docs tests/fixtures --workdir .tmp/trial-ops-pilot --include-browser-qa --output .tmp/trial-ops-pilot/report.json
```

## Review Gates

- Do not start a child before its `prd.md` is testable.
- Add `design.md` and `implement.md` for any child that touches multiple layers.
- Run `trellis-before-dev` before editing code in a child task.
- Run `trellis-check` before finishing each child task.
- Archive completed child tasks and record progress in the journal.
