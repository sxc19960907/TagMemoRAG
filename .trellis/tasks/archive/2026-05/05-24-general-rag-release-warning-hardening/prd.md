# General-purpose RAG release warning hardening

## Goal

Continue the general-purpose RAG quality track after the long-horizon quality
program. The work should reduce the remaining release-readiness warnings for
the classic RAG path without opening the default-off Agentic path or creating
unexplained behavior differences between current `/retrieve` and `/answer`
consumers.

## User Value

Operators should be able to discuss general RAG readiness from one explicit
release report instead of scattered diagnostics. Public-web, multi-format,
mixed-domain, real-manual, and answer-quality slices should continue to move
together, with regressions caught before any tuning is kept.

## Confirmed Facts

- The previous task `05-24-long-horizon-rag-quality` is archived and produced a
  release-readiness report at
  `.tmp/eval/release-readiness-after-evidence-prior-defaults.json`.
- The current release-readiness status is `warning`.
- Remaining warning stages:
  - `general_web_retrieval`: `MRR=0.651361`, below target `0.75`.
  - `multiformat_context_tight`: selected expected rate `2/3`, below target
    `1.0`.
- Passed stages that must not regress:
  - multi-format retrieval: `hit@k=1.0`, `recall@k=1.0`, `MRR=0.777778`
  - mixed-domain retrieval: `hit@k=1.0`, `recall@k=1.0`, `MRR=1.0`
  - real-manual retrieval: `hit@k=1.0`, `recall@k=0.966667`, `MRR=0.775`
  - normal and tight general-web context quality: `7/7`
  - normal multi-format context quality: `3/3`
  - general-web answer, multi-format answer, and product-manual QA answer
    diagnostics have zero failures.
- Prior rejected tuning showed that broad additive evidence priors can improve
  general-web MRR while dropping general-web recall from `0.928571` to
  `0.857143`; this class of trade-off is not acceptable for this task.
- The architecture spec requires retrieval-affecting work to name its eval
  slices before implementation starts.
- Dirty untracked files `.codegraph/` and `.mcp.json` are unrelated and must
  remain untouched.

## Requirements

- R1: Work only on the classic general-purpose RAG path: retrieval ranking,
  context packing/compression, diagnostics, tests, and release readiness.
- R2: Do not enable or route through Agentic mode, WAVE/geodesic promotion, or
  external rerankers on the critical path.
- R3: Start from diagnostics of the two warning stages before changing code.
- R4: Any kept ranking change must preserve or improve general-web recall and
  must not regress multi-format, mixed-domain, or real-manual retrieval.
- R5: Any kept tight-context change must preserve normal-budget context
  quality and answer-quality diagnostics.
- R6: Rejected tuning attempts must be documented with the reason they were
  rejected.
- R7: Regenerate release-readiness JSON/Markdown after the kept batch.

## Eval Slices

The task must exercise these slices before completion:

- `tests/fixtures/eval/general_web.jsonl`
- `tests/fixtures/eval/multiformat_real_knowledge.jsonl`
- `tests/fixtures/eval/mixed_knowledge.jsonl`
- `tests/fixtures/eval/realmanuals.jsonl`
- context-quality diagnostics for general-web and multi-format at normal and
  tight budgets
- `tests/fixtures/answer_quality/general_web.jsonl`
- multi-format answer diagnostics
- `tests/fixtures/answer_quality/qa_product_manual.jsonl`
- release-readiness report

## Acceptance Criteria

- [ ] Diagnostic notes identify the concrete cases behind
      `general_web_retrieval` and `multiformat_context_tight` warnings.
- [ ] A coherent hardening batch lands, or the diagnostic proves one warning is
      not safely reducible without a larger follow-up such as a first-class
      reranker/evidence compressor.
- [ ] General-web retrieval MRR improves from `0.651361` without reducing
      general-web recall below `0.928571`, or the rejected attempts are
      documented and release warning remains explicit.
- [ ] Tight-budget multi-format context improves from `2/3` selected expected
      cases, or the blocker is documented as a larger chunk-boundary/evidence
      compression follow-up.
- [ ] Passed retrieval, context, and answer-quality stages from the previous
      release-readiness report remain passed.
- [ ] Release-readiness JSON and Markdown are regenerated after the batch.
- [ ] No Agentic mode activation, WAVE/geodesic promotion, external reranker
      critical-path dependency, parser-wide chunk reshaping, or checked-in
      third-party document bodies are introduced.

## Out of Scope

- General Agent / Agentic path activation.
- API/CLI slimming unrelated to the warning stages.
- Broad parser rewrites or corpus-wide chunking changes unless diagnostics
  prove they are the only safe path and the task is replanned first.
- New third-party corpora beyond stable runtime `.tmp/` materialization.
