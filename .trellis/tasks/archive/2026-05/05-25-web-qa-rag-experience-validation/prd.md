# Web QA RAG experience validation

## Goal

Validate and, if needed, repair the web QA RAG experience so a normal user can open the local QA page, ask a seeded demo question, and see a grounded answer with source evidence.

## User Value

The CLI demo proves the backend RAG loop works. This task checks the next user-facing layer: the browser page should make the same capability usable without requiring users to compose CLI/API calls by hand.

## Confirmed Facts

- `/qa` renders `qa_page.html` and calls `POST /qa/answer`.
- `/admin/rag-workbench` renders a more operator-oriented answer/evidence workbench.
- `examples/config/qa-demo.yaml` enables local hashing embeddings and noop answers.
- `scripts/seed_qa_demo.sh` builds the coffee-machine demo KB.
- The CLI demo answer path already passes for `蒸汽很小怎么办？`.

## Requirements

- Seed the local demo KB and run the FastAPI app with the QA demo config.
- Validate `/qa?kb_name=default` in a browser: page loads, question can be submitted, answer appears, citations/sources appear, and no blocking console errors occur.
- Prefer fixing small defects found during validation over only reporting them.
- Keep changes scoped to the web QA experience or startup/config glue needed for this flow.
- Do not require network services, API keys, Qdrant, S3, or live LLM providers.

## Acceptance Criteria

- [x] `bash scripts/seed_qa_demo.sh` succeeds.
- [x] The local server starts with `examples/config/qa-demo.yaml`.
- [x] Browser validation submits `蒸汽很小怎么办？` on `/qa?kb_name=default`.
- [x] The rendered answer contains the expected weak-steam/nozzle/water/E05 guidance.
- [x] The page renders at least one cited source/evidence item.
- [x] No uncaught browser console error blocks the flow.
- [x] Focused tests or an explicit browser smoke are recorded.

## Validation Notes

- Browser smoke after fix: `/qa?kb_name=default` rendered a high-confidence answer with `cit_001` and `cit_002`; no `制作咖啡` weak-related source appeared; browser error logs were empty.
- Focused tests: `.venv/bin/pytest tests/unit/test_answer_api.py tests/unit/test_manual_library_ui.py -q` passed with 19 tests.

## Out of Scope

- New visual design or a redesign of the QA page.
- Live model/provider onboarding.
- Manual-library upload workflow fixes unless they directly block QA demo use.
- Broad retrieval quality tuning.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
