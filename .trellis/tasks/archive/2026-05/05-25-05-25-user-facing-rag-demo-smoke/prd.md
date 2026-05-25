# User-facing RAG demo smoke path

## Goal

Make the RAG system usable as a normal local demo path: a user can seed the sample knowledge base, ask a question, and see a grounded answer with citation/evidence counts using only offline defaults.

## User Value

The current repository has the retrieval and answer pieces, but a normal user must stitch together build/search/API commands to experience RAG. This task provides a small, deterministic "try it now" path that proves the build -> retrieve -> answer loop without requiring provider keys, Qdrant, S3, or a running server.

## Confirmed Facts

- `examples/config/qa-demo.yaml` already configures hashing embeddings, NPZ vector storage, and the noop answer provider under `.tmp/tagmemorag-qa-demo/`.
- `scripts/seed_qa_demo.sh` already copies `tests/fixtures/coffee_machine.md` and builds KB `default`.
- The API has `/answer` and `/qa/answer`; the CLI currently exposes `build` and `search`, but not a direct local answer/demo command.
- `readiness smoke` checks internal composition, but it uses an isolated readiness fixture rather than the user-facing coffee-machine demo content.

## Requirements

- Add a deterministic offline CLI demo command for asking a question against the demo KB and producing a bounded JSON answer summary.
- The command must reuse the existing answer/retrieve implementation path rather than duplicating ranking, evidence, QueryPlan, or answer formatting logic.
- The command must work with `examples/config/qa-demo.yaml`, KB `default`, and the seeded coffee-machine fixture.
- Output must include answer kind/text/citation count, retrieve evidence/citation counts, plan/build identifiers, warnings, and a small source summary sufficient for a user to inspect where the answer came from.
- Any retained or documented report must avoid raw provider bodies, secrets, vectors, and unbounded candidate lists. The demo may show the generated noop answer text and bounded source metadata because that is the user-visible demo response.
- Keep the path offline by default and independent of network, live LLM providers, Qdrant, and S3.
- Document the normal-user quick path in the README.

## Acceptance Criteria

- [ ] A user can run the seed script without depending on `uv` being the only Python runner.
- [ ] A user can run one CLI command to ask `蒸汽很小怎么办？` against the demo KB and get JSON containing `answer.kind == "answer"`.
- [ ] The demo response includes at least one citation or evidence item for the coffee-machine fixture.
- [ ] A focused unit test covers the CLI wiring and output contract.
- [ ] A real local smoke command is run with `examples/config/qa-demo.yaml` and passes.
- [ ] README documents the seed and ask commands.

## Out of Scope

- Building a new web UI.
- Adding a live provider-backed answer model.
- Changing retrieval ranking behavior or default production settings.
- Expanding retained evaluation corpora.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
