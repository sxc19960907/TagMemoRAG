# Diagnostic Notes

## Starting Point

The previous task fixed public-web HTML chrome noise and moved the MDN HTTP caching case from a top-k miss to `hit@k=1.0`. Remaining general-web weaknesses are low MRR rather than missing recall.

From `.tmp/eval/gap-general-web-after-main.json`:

- `github-hello-world-repository`: relevant README/Markdown evidence at rank 6; repository/folder evidence is still missing from top 8.
- `github-hello-world-pull-request`: exact pull-request definition evidence at rank 4.
- `mdn-http-cache-no-cache-private`: private directive evidence at rank 7; no-cache/revalidation evidence is still missing from top 8.
- `irs-free-file-agi-guided-tax`: two relevant chunks at ranks 3 and 4.

## Hypothesis

The deterministic lexical layer rewards adjacent query-term pairs but does not reward compact evidence phrases that combine one query term with a salient neighboring document term, such as `private directive`, `repository ... folder`, or `AGI threshold`, when the query terms are not adjacent in the query string. This can let overview chunks with many broad query terms outrank answer-bearing chunks.

## Outcome

Implemented a bounded compact-window body bonus for `public_web/` chunks only. Earlier variants that also rewarded repeated query terms improved general-web recall further, but regressed mixed-domain MRR by promoting table-of-contents or broad reference chunks. The final public-web-only compact-window version improves the general-web aggregate MRR while preserving mixed-domain, real-manual, and multi-format baselines.

Final validation:

- General web retrieval: 7 cases, `hit@k=1.0`, `recall@k=0.857143`, `mrr=0.556122`.
- General web answer quality: 7 cases, failed=0.
- Mixed-domain retrieval: 4 cases, `hit@k=1.0`, `recall@k=1.0`, `mrr=1.0`.
- Multi-format retrieval: 3 cases, `hit@k=1.0`, `recall@k=1.0`, `mrr=0.611111`.
- Multi-format answer quality: 3 cases, failed=0.
- Real manuals retrieval: 10 cases, `hit@k=1.0`, `recall@k=0.966667`, `mrr=0.708333`.

Remaining gap: GitHub repository and MDN multi-evidence cases still have relevant chunks below rank 1. Pushing these further likely needs an explicit reranker or context-level complementary evidence objective rather than broader lexical boosts.
