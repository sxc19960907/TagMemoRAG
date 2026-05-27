# Browser QA Readiness Quality Gate Design

## Scope

Add a CLI command under the existing `readiness` group. Reuse the existing browser tests rather than creating duplicate browser automation.

## Command Shape

```bash
python -m tagmemorag readiness browser-qa
python -m tagmemorag readiness browser-qa --full
```

The focused command runs:

```bash
TAGMEMORAG_RUN_BROWSER_UI=1 pytest tests/integration/test_browser_admin_ui.py::test_browser_manual_library_to_qa_user_flow -q
```

The full command runs:

```bash
TAGMEMORAG_RUN_BROWSER_UI=1 pytest tests/integration/test_browser_admin_ui.py -q
```

## Report

Print JSON to stdout:

```json
{
  "schema_version": "browser_qa_readiness.v1",
  "status": "passed",
  "mode": "focused",
  "target": "tests/integration/test_browser_admin_ui.py::test_browser_manual_library_to_qa_user_flow",
  "command": ["python", "-m", "pytest", "..."],
  "return_code": 0,
  "duration_seconds": 1.23
}
```

Do not include browser logs, raw page content, tokens, or large pytest output in the report. Pytest output can stream directly to the terminal.

## Boundaries

- Keep orchestration in a small readiness module rather than embedding subprocess logic in parser setup.
- Do not introduce a new browser test framework.
- Do not make this a replacement for backend `readiness smoke`; it is an additional user-experience gate.
