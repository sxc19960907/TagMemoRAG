# Design

## Boundary

This task works only on the classic retrieval path for the general-purpose RAG
system. The first deliverable is diagnostic-only. A ranking change is allowed
only if the diagnostic finds a stable feature that distinguishes evidence-bearing
body text from broad related chunks without relying on case-specific strings.

The task must not enable or alter Agentic behavior, WAVE/geodesic propagation, or
external reranking. It must also avoid broad scoring changes that make source
identity, page titles, or topical overlap look like body evidence.

## Diagnostic Shape

The diagnostic consumes the current general-web eval report and fixture:

- `.tmp/eval/release-readiness-after-fit-compaction-defaults.json`
- `.tmp/eval/general-web-after-evidence-prior.json`
- `tests/fixtures/eval/general_web.jsonl`

For each warning-relevant case, record:

- suite metrics and per-case MRR/recall
- top-k rank, score, source, header, and matched expected indexes
- `lexical_evidence_score(query, node-like-result)`
- body and heading query-term coverage
- compact-window/proximity evidence cues where available
- chrome/title-only indicators
- definition, overview, and action/workflow cue indicators
- a short interpretation of why expected evidence ranks below competitors

The diagnostic should be deterministic and reproducible from committed fixtures
plus local `.tmp` reports. It should not fetch network content.

## Ranking Change Gate

Only make a ranking change if all of the following hold:

- The signal applies across more than one weak case or is clearly domain-general.
- The signal uses body/header evidence rather than source identity.
- The signal is bounded, deterministic, and explainable.
- A quick before/after eval shows no recall regression in general-web.
- Broader release-readiness validation remains green for stages that already
  passed.

If the diagnostic shows that current features cannot separate expected evidence
from broad related chunks, stop at documentation and preserve current behavior.

## Compatibility

API schemas, stored indexes, query-plan persistence, context-pack lineage, and
answer-generation contracts must remain unchanged unless a later task explicitly
scopes those changes.

Runtime third-party documents and generated eval reports remain under `.tmp/`.
Task notes may summarize findings but should not copy fetched document bodies.

## Rollback

Diagnostic-only changes are rolled back by removing the new task note/script.
Any scoring change must be small enough to revert in one patch and must have
validation output identifying the changed metric surface.
