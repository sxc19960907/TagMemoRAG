# Browser QA Readiness Quality Gate Implementation Plan

## Checklist

- [x] Start the child task.
- [x] Read Trellis backend and quality guidelines.
- [x] Add a small browser QA readiness runner.
- [x] Wire `readiness browser-qa` into CLI parser and dispatch.
- [x] Add unit tests for focused/full command behavior and failure mapping.
- [x] Update README readiness docs.
- [x] Run static and focused unit tests.
- [x] Run the focused browser QA readiness command once.
- [ ] Commit and archive the child task.

## Validation Commands

```bash
python3 -m py_compile src/tagmemorag/cli_parser.py src/tagmemorag/cli_eval.py src/tagmemorag/browser_qa_readiness.py tests/unit/test_cli.py
uv run pytest tests/unit/test_cli.py -q
uv run python -m tagmemorag readiness browser-qa
```

## Risk Points

- The CLI command should work from a source checkout where pytest is installed, which matches the intended development readiness use.
- Unit tests should monkeypatch the subprocess call so they remain fast and do not launch Playwright.
