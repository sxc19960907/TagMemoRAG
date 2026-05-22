# Production Pilot Verification v2

## Goal

Upgrade the repeatable pilot gate so it covers both retrieval eval and
answer-quality diagnostics in one retained, sanitized report.

## User Value

The project now has stronger RAG components: QueryPlan/replay, optional
LangChain ingestion, answer-quality diagnostics, production answer prompt
guards, agentic production tools, and bulk import severity fixes. The next
pilot gate should prove these reliability checks compose before more surface
area is added.

## Confirmed Facts

- `python -m tagmemorag pilot run` already composes config validation,
  provider probe, local readiness smoke, retrieval eval, and optional
  hashing-vs-production baseline diagnosis.
- `scripts/production_verify.py` wraps the pilot report into a higher-level
  production verification report.
- Answer-quality diagnostics already exist at
  `python -m tagmemorag eval answer-quality --suite ...`.
- The default answer-quality fixture is deterministic/offline and contains
  citation-miss plus conflicting-evidence cases.
- Existing pilot reports are intentionally sanitized and must not include raw
  queries, snippets, provider bodies, secrets, or generated answer text.

## Requirements

- Add an answer-quality diagnostics stage to `run_production_pilot`.
- The stage must be enabled by default with
  `tests/fixtures/answer_quality/basic.jsonl`.
- Operators can disable the stage explicitly for profiles that only want
  retrieval/readiness gates.
- Operators can override the answer-quality suite path.
- The stage must summarize only bounded diagnostics: schema version, case
  count, pass/fail counts, and failing case ids/reasons.
- The stage must fail the pilot when answer-quality diagnostics fail or the
  suite is invalid.
- `scripts/production_verify.py` should inherit the pilot-stage behavior and
  expose CLI options for answer-quality suite/disable.
- CLI help/runbook docs should describe the new gate and its offline/default
  behavior.

## Acceptance Criteria

- [x] Default `pilot run` includes `answer_quality` between readiness and
      retrieval eval.
- [x] `--skip-answer-quality` removes the stage.
- [x] `--answer-quality-suite <path>` overrides the default suite.
- [x] Pilot JSON/Markdown reports stay sanitized and do not include raw fixture
      answer/context text.
- [x] `scripts/production_verify.py` exposes matching answer-quality options
      and passes them to `run_production_pilot`.
- [x] Focused production pilot and verification tests pass.

## Out of Scope

- Do not run paid/live LLM answer generation as part of the default
  answer-quality gate.
- Do not add real PDF/HTML live provider reruns in this task.
- Do not change retrieval eval thresholds or baselines.
- Do not change answer-quality evaluator semantics beyond report integration.

## Rollback

Revert the pilot stage, CLI options, and docs. Existing pilot retrieval/readiness
behavior remains the fallback gate.
