# Program Log

## 2026-05-25 Kickoff

The previous general RAG stability program completed same-page ordering
default-on rollout with gates passing and config rollback preserved.

Current baseline:

- `search.same_page_ordering_enabled=true`
- `search.same_page_ordering_min_group_size=2`
- Default-on general-web eval: cases `7`, recall@k `0.971429`, MRR
  `1.000000`, hit@k `1.000000`
- Candidate-aware gate batch: `passed`
- Release readiness: `passed`
- Reranking gate: `passed`
- Failed checks: `[]`

Decision:

- Create this parent program to keep the next phase stable and evidence-led.
- First child: retained corpus inventory.
- Do not make more ranking/retrieval behavior changes until retained coverage
  gaps are known.

## 2026-05-25 Child 1: Retained Corpus Inventory

Child task: `05-25-05-25-retained-corpus-inventory`

Result:

- Inventoried committed eval suites under `tests/fixtures/eval/`.
- Inventoried reusable local corpus locations without committing local corpus
  bodies.
- Recorded key retained default-on and same-page enabled aggregate reports.
- Confirmed latest default-on gate outputs remain available under
  `.tmp/eval/default-on-implementation-gate/`.
- Identified that core post-default-on monitoring slices exist but are small:
  general-web `7`, mixed-domain `4`, multiformat `3`, realmanuals `10`.
- Identified that monitoring is still manually assembled from report paths.

Classification: `ship`

Decision:

- Next child should create a default-on retained monitoring manifest and batch
  summary before adding more corpus cases.
- Do not change retrieval/ranking behavior until a repeatable monitoring
  manifest exists.
