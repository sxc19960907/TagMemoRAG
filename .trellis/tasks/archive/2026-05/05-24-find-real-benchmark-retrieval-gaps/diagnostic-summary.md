# Diagnostic Summary

## Baseline

- General web: 7 cases, `hit@k=0.857143`, `recall@k=0.857143`, `mrr=0.528571`.
- Multi-format: 3 cases, `hit@k=1.0`, `recall@k=1.0`, `mrr=0.611111`.
- Mixed-domain: 4 cases, `hit@k=1.0`, `mrr=1.0`.
- Real manuals: 10 cases, `hit@k=1.0`, `recall@k=0.966667`, `mrr=0.708333`.

## Weakest Real Case

`mdn-http-cache-no-cache-private` was the only general-web top-k miss. The relevant chunks existed in the parsed MDN document, but the top results included page chrome and broad HTTP cache sections before the exact `private`/`no-cache` evidence.

## Fix

Public-web HTML import now ignores structural chrome tags (`nav`, `header`, `footer`, `aside`) and prefers readable blocks inside `<main>` when present, with fallback to all visible blocks for pages without `<main>`.

## Post-Fix Validation

- General web retrieval: 7 cases, `hit@k=1.0`, `recall@k=0.857143`, `mrr=0.484694`.
- General web answer quality: 7 cases, failed=0.
- Multi-format retrieval: 3 cases, `hit@k=1.0`, `recall@k=1.0`, `mrr=0.611111`.
- Multi-format answer quality: 3 cases, failed=0.
- Mixed-domain retrieval: 4 cases, `hit@k=1.0`, `mrr=1.0`.
- Real manuals retrieval: 10 cases, `hit@k=1.0`, `recall@k=0.966667`, `mrr=0.708333`.

## Remaining Gap

The remaining low-MRR general-web cases are not primarily HTML extraction bugs. They are multi-evidence ranking/context issues where an overview chunk, a complementary chunk, and the exact expected evidence all support the same answer. The next quality task should focus on ranking or reranking complementary evidence, not on adding site-specific HTML filters.
