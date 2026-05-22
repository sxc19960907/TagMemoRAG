# Demo QA seed smoke

## Goal

Make the local `/qa` page demonstrably useful by seeding a default demo KB from the existing coffee machine fixture and providing a repeatable local command path that builds the KB, serves the app with noop answers, and lets `/qa` return an answer with sources.

## Requirements

- Reuse the existing `tests/fixtures/coffee_machine.md` demo content.
- Add a local demo config that uses hashing embeddings, local NPZ storage, and `answer.provider=noop` so the answer path is deterministic and offline.
- Add a small script that builds the `default` KB from the coffee fixture using the demo config.
- Document the local QA demo flow in README.
- Do not require network access, provider keys, Qdrant, or manual UI uploads.
- Keep the demo data under `.tmp/` so generated KB files are not committed.

## Acceptance Criteria

- [x] A documented command builds `default` from the coffee fixture into `.tmp/tagmemorag-qa-demo/data`.
- [x] Serving with the demo config loads `kb_count=1`.
- [x] `POST /qa/answer` for “蒸汽很小怎么办？” returns `route.kind="answered"` and source evidence.
- [x] `/qa` remains the user-facing page; admin/debug pages are unchanged.
- [x] Focused tests or smoke commands prove the demo path works offline.

## Notes

- Lightweight task: PRD-only is sufficient because this adds demo configuration, a build helper, and documentation around existing build/serve/answer paths.
