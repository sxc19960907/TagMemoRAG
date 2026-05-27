# Deployment Pilot Readiness Pass Implementation Plan

## Checklist

- [x] Start the child task.
- [x] Read Trellis backend/frontend quality guidance.
- [x] Add browser QA readiness opt-in arguments to `pilot run`.
- [x] Add browser QA readiness stage to the production pilot report.
- [x] Update CLI and production pilot unit tests.
- [x] Update operator docs and quality gate guidance.
- [x] Mark parent task child 6 progress accurately.
- [x] Run focused static, unit, pilot, and browser checks.
- [x] Commit and archive the child task.

## Validation Commands

```bash
python3 -m py_compile src/tagmemorag/cli_parser.py src/tagmemorag/cli_eval.py src/tagmemorag/production_pilot.py src/tagmemorag/browser_qa_readiness.py
uv run pytest tests/unit/test_production_pilot.py tests/unit/test_cli.py -q
uv run python -m tagmemorag pilot run --config examples/config/local-hashing-npz.yaml --suite tests/fixtures/eval/coffee.jsonl --docs tests/fixtures --workdir .tmp/pilot-browser-qa --include-browser-qa --output .tmp/pilot-browser-qa/report.json
uv run python -m tagmemorag readiness browser-qa
git diff --check
```

## Risk Points

- Browser readiness is slower than the existing local pilot gate, so it must stay opt-in.
- Unit tests should mock the browser runner; real Playwright should only run in explicit validation commands.
- Existing `production_pilot.v1` schema consumers should tolerate the new optional stage without changing the schema version.
