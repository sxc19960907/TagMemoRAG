# RAG Answer Quality Diagnostics — Design

## Scope

Add an optional, offline-first diagnostics path for answer quality. The first
implementation should produce a bounded JSON report that helps compare
grounded and ungrounded answers without changing `/answer`, retrieval, ranking
eval, or provider defaults.

This task is a quality instrument, not a runtime answer feature.

## Goals

- Measure answer quality along small, explicit dimensions:
  - faithfulness / evidence support;
  - context relevance;
  - answer relevance;
  - citation support;
  - refusal quality.
- Keep the default path deterministic and network-free.
- Allow a provider-gated judge backend later, skipped safely when env is
  absent.
- Ensure reports do not leak raw document text beyond already-authored test
  fixture content.

## Non-Goals

- Do not add Ragas or another judge dependency to the base install in this
  task unless a narrow optional extra proves necessary.
- Do not block `/answer` responses on diagnostics.
- Do not refresh ranking eval baselines unless fixture changes require it.
- Do not replace existing eval/replay infrastructure.

## Proposed Shape

### Fixture Contract

Create a small diagnostics fixture under `tests/fixtures/answer_quality/`.
Each case is authored test data and may include:

- `case_id`
- `question`
- `contexts`: bounded evidence snippets with optional citation ids
- `answer`
- `expected`: expected booleans or score bands for each diagnostic dimension
- `notes`: optional reviewer-only rationale

The fixture must include at least:

- one grounded answer with citation support;
- one ungrounded answer with unsupported claims;
- one refusal-quality case if implementation cost stays small.

### Diagnostics Contract

Add a narrow backend module, likely `src/tagmemorag/eval/answer_quality.py`,
with pure dataclasses/functions where possible:

- `AnswerQualityCase`
- `AnswerQualityResult`
- `AnswerQualityReport`
- `run_answer_quality_diagnostics(cases, judge=...)`

The deterministic first-pass judge should be local and simple:

- citation support checks whether cited ids exist in supplied contexts;
- unsupported-claim checks use explicit fixture labels or phrase markers rather
  than trying to infer truth from arbitrary text;
- refusal quality checks expected refusal vs non-refusal labels.

This is deliberately conservative: it creates a repeatable harness first, then
future provider-backed judges can plug into the same result schema.

### Report Contract

Reports should be bounded JSON:

- `schema_version`
- `generated_at`
- `summary`: case count and per-dimension pass/fail counts
- `cases`: one result per case with bounded fields
- `warnings`: provider skipped, malformed case skipped, etc.

Do not include:

- raw provider responses;
- secrets or env values;
- full document chunks from runtime indexes;
- stack traces.

Because initial fixtures are hand-authored and small, including the authored
question/answer may be acceptable only if existing eval report conventions do
so. Prefer case ids and compact failure reasons in default CLI output.

### Entry Point

Prefer a CLI subcommand under the existing eval command surface if one exists,
for example:

```bash
python -m tagmemorag eval answer-quality \
  --suite tests/fixtures/answer_quality/basic.jsonl \
  --output .tmp/answer-quality/report.json
```

If the existing CLI layout makes this awkward, add a script-level entry point
with the same pure backend module underneath. Do not add API endpoints in this
task.

### Provider-Gated Extension Point

Define the judge boundary so a future live judge can be added behind explicit
settings/env gates. In this task:

- default judge is fake/local;
- provider judge, if present, must skip when required env vars are missing;
- tests should not require network access.

## Data Flow

```text
answer-quality fixture
  -> JSONL loader
  -> local/fake judge
  -> AnswerQualityReport
  -> JSON output + bounded CLI summary
```

No runtime KB rebuild, vector store, `/retrieve`, or `/answer` mutation is
required for the first implementation.

## Compatibility

- Existing answer API behavior remains unchanged by default.
- Existing ranking eval and baselines remain unchanged unless a new suite
  explicitly requires baseline work.
- Future C5 prompt/context work can consume the report schema without knowing
  which judge backend produced it.

## Rollback

Rollback is delete-only:

- remove the answer-quality module / command;
- remove the new fixture and tests;
- existing ranking eval and answer runtime continue unchanged.
