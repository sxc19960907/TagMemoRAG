# User-facing RAG demo smoke path implementation plan

## Checklist

- [x] Activate the task.
- [x] Add a `demo qa` parser branch and dispatch path.
- [x] Implement a narrow demo QA service that delegates to the existing API answer path.
- [x] Add focused unit tests for CLI wiring/output and bounded source summary.
- [x] Update `scripts/seed_qa_demo.sh` with a Python runner fallback.
- [x] Update README with the seed and ask workflow.
- [x] Run focused tests and a real local demo smoke.
- [ ] Update parent/task notes, commit, and archive the child task.

## Validation Commands

```bash
.venv/bin/pytest tests/unit/test_cli.py -q
bash scripts/seed_qa_demo.sh
.venv/bin/python -m tagmemorag demo qa "蒸汽很小怎么办？" --config examples/config/qa-demo.yaml --output .tmp/tagmemorag-qa-demo/qa-response.json
```

## Risk Points

- Importing API globals in CLI code can accidentally use default config. The demo service must explicitly replace `api.settings`, `api.embedder`, and `api.app_state` before calling `api.answer`.
- The command should summarize output without leaking debug internals or unbounded candidate data.
- Keep generated `.tmp/` data out of git.
