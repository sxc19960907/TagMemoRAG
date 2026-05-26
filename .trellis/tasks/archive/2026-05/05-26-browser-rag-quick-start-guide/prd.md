# Browser RAG quick start guide

## Goal

Give first-time local users a short, browser-first path to experience TagMemoRAG RAG without API keys, external services, or command-line-only interaction.

## Requirements

- Add a concise guide for the local browser RAG experience using the existing offline hashing/noop demo configuration.
- Cover install, demo seeding, starting the server, opening the browser pages, asking a cited question, and the upload/rebuild/QA loop.
- Link the guide from README near the existing quick start/demo section.
- Keep the guide focused on local experience; do not duplicate production deployment runbooks or provider setup details.

## Acceptance Criteria

- [x] A new docs page gives a 5-10 minute browser-first RAG walkthrough.
- [x] README points users to that page from Quick Start.
- [x] Commands use existing config/scripts and avoid requiring API keys or remote services.
- [x] Documentation checks relevant to the changed docs pass.

## Outcome

- Added `docs/browser-rag-quick-start.md` for the offline browser-first RAG path.
- Linked the guide from README near the existing local QA demo instructions.
- Verified the guide's demo command with `uv run python` because this environment does not expose a bare `python` command.

## Validation

- `uv run python -m tagmemorag demo library-qa --config examples/config/qa-demo.yaml --output .tmp/tagmemorag-qa-demo/library-qa-response.json` -> passed with `"status": "passed"`.
- `.venv/bin/python -m pytest tests/unit/test_manual_library_ui.py -q` -> `16 passed`.
- `git diff --check` -> passed.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
