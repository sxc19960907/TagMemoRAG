# Program Log

## 2026-05-24 Kickoff

User asked for a long-running task: make a plan, keep executing based on each
task's results, and preserve system stability.

Current baseline:

- Release readiness: `passed`
- General-web retrieval: `hit@k=1.0`, `recall_at_k=0.971429`, `MRR=0.773810`
- Ranking pressure: `2` cases, highest pressure ranks `5`
- Reranking evaluation gate exists and is documented.

Decision:

- Create this parent program and keep it active.
- First child: baseline batch self-check.
- No runtime ranking change until gates prove a candidate is safe.

## 2026-05-24 Child 1: Baseline Batch Self-Check

Child task: `05-24-baseline-batch-self-check`

Result:

- Focused tests: `22 passed`
- Release readiness: `passed`
- General-web retrieval: `hit@k=1.0`, `recall_at_k=0.971429`, `MRR=0.773810`
- Ranking pressure: `2` cases, highest pressure ranks `5`
- Reranking gate self-check: `passed`, failed checks `[]`

Classification: `ship`

Decision:

- Baseline is stable enough to continue.
- Next child should automate the self-check into a batch runner, so future
  candidate tasks use one repeatable command instead of manual command stitching.
