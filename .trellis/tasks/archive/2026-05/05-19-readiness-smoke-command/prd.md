# Readiness smoke command

## Goal

Add a deterministic local readiness smoke command that operators can run before deployment, after config changes, or after upgrades to verify the MVP critical paths compose end-to-end without network dependencies.

The command should answer: "Can this checkout/config build a tiny KB, retrieve evidence, optionally generate a noop answer, persist a QueryPlan, and round-trip a manual bundle?"

## Confirmed Facts

- `tagmemorag` already has CLI subcommands for build/search/eval/manual-library/qdrant/feedback.
- `model.provider=hashing` is documented for CI/offline runs and avoids downloads or network calls.
- Recent MVP integration tests prove the same deterministic composition in unit tests.
- `/retrieve` and `/answer` share QueryPlan ids and persist per-KB SQLite records.
- Manual-library bundle export/import is available through service functions and CLI subcommands.

## Requirements

- Add a CLI command under `tagmemorag readiness smoke`.
- The smoke command must create and use an isolated temporary workspace by default.
- The smoke command must use deterministic local providers only:
  - hashing embedder
  - noop answer provider
  - local JSON/NPZ storage
  - local file manual library and blob store
- The command must exercise at least:
  - build a tiny KB from fixture content
  - retrieve evidence from that KB
  - call answer generation in noop mode over the same evidence
  - verify a QueryPlan row was persisted for the answer/retrieve flow
  - export/import a bundle for the fixture manual
- Output must be JSON by default with a concise `status`, per-check results, temporary workspace location when retained, and no raw secrets/vectors/local storage internals.
- Exit code must be `0` only when all checks pass; non-zero when any check fails.
- Provide `--keep-workdir` so operators can inspect artifacts after a failed or explicit retained run.
- Provide `--workdir` so operators/CI can choose where the isolated smoke workspace is created.
- Document the command in README and/or the production operations guide.

## Acceptance Criteria

- [ ] `tagmemorag readiness smoke` runs offline and exits `0` on a healthy checkout.
- [ ] The JSON result reports passing checks for build, retrieve, answer, QueryPlan persistence, and bundle round-trip.
- [ ] A failure path returns non-zero and includes a bounded error reason without dumping raw document text, vectors, secrets, storage keys, or checksums.
- [ ] `--keep-workdir` retains the workspace and reports its path.
- [ ] Focused CLI tests cover success and at least one failure path.
- [ ] Docs show the command and clarify that it is a local smoke check, not a production traffic or HA validation.
- [ ] Final validation includes the new tests, relevant CLI/manual bundle/queryplan tests, and `git diff --check`.

## Out Of Scope

- Live API server probing.
- Remote embedding/reranker/LLM/OCR/visual provider validation.
- Qdrant, S3, or multi-replica readiness.
- Performance benchmarking or eval quality thresholds.
- Changing the public `/retrieve` or `/answer` API schema.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
