# Diagnostic Notes

## Release Warning Baseline

Source report: `.tmp/eval/release-readiness-after-evidence-prior-defaults.json`.

- Overall status: `warning`.
- Warning stages:
  - `general_web_retrieval`: `MRR=0.651361`, target `0.75`.
  - `multiformat_context_tight`: selected expected rate `2/3`, target `1.0`.

## General-web Retrieval Warning

Weak cases from `.tmp/eval/general-web-after-evidence-prior.json`:

- `github-hello-world-repository`
  - `recall@k=1.0`, but first expected evidence is rank 6 and the second is
    rank 8.
  - Higher-ranked chunks are broad tutorial overview, page title/source chrome,
    and workflow/action steps.
- `github-hello-world-pull-request`
  - Expected pull-request definition evidence is rank 4.
  - Rank 1-3 are broad tutorial overview, review/action text, and page
    title/source chrome.
- `mdn-http-cache-no-cache-private`
  - `recall@k=0.5`; private-cache expected evidence is rank 7, while the
    no-cache expected evidence is still outside top-k.
  - Rank 1-3 are all closely related but do not match the exact expected
    support statement.

Evidence-score check:

- Existing `lexical_evidence_score` does not reliably separate expected chunks
  from broad but related chunks in these cases. For example, GitHub repository
  overview/action chunks score higher than the rank-6/rank-8 expected chunks.
- This supports the previous warning: broad additive evidence priors are risky.
  A kept change needs a narrower diagnostic or context/evidence objective, not
  a stronger generic score.

Rejected direction for now:

- Do not add a broad evidence-score additive prior across all results. Prior
  work already showed that this improves some MRR values while reducing
  general-web recall.

## Tight Multi-format Context Warning

Source report:
`.tmp/eval/context-quality-multiformat-budget260-after-adjacent-merge.json`.

- `multiformat-html-mdn-no-cache`
  - Expected evidence is retrieved but selected expected count is `0`.
  - Selected context items are related same-source MDN chunks, but not the exact
    expected no-cache support chunk.
- `multiformat-docx-epa-waiver-certifications`
  - Three expected chunks are retrieved; two are selected under the 260-token
    budget.
  - The selected context contains a merged first item and a short second item.
  - The remaining unselected expected chunk likely needs either stronger
    compression or a more explicit multi-evidence packing objective.

Rejected direction for now:

- Do not globally reshape parser chunks to make the DOCX or MDN cases easier.
  Parser-level changes have already caused real-manual regressions in the
  previous long-horizon task.

## Candidate Safe Levers

- Add a diagnostic-only helper for public-web multi-evidence cases before
  changing ranking, so future tuning can compare body evidence vs overview
  chunks without looking at raw report snippets by hand.
- For context packing, prefer a bounded "expected-style multi-evidence
  coverage" improvement: stronger query-relevant sentence compaction and
  same-source packing while preserving `evidence_refs` / `citation_ids`.
- Keep any ranking modification bounded to public-web body evidence; do not
  use source_file, title, or identity fields as ordinary topic evidence.

## Kept Batch: Fit-aware Context Merge Compaction

Change:

- During context item bundling, when a same-source merge candidate does not fit
  the remaining budget as full text, try compacting that candidate to the
  exact remaining token budget before rejecting it.
- Consider up to three same-source merge candidates instead of two, still under
  the existing merge eligibility checks and token budget.

Why this is bounded:

- Retrieval result order, evidence list order, citations, and API schemas are
  unchanged.
- The change only affects `context_pack.items` content and lineage when a
  candidate was already eligible for same-source context merging.
- `evidence_refs` and `citation_ids` preserve lineage for compacted merged
  content.

Observed target result:

- `context-quality-multiformat-budget260-after-fit-compaction.json` improved
  tight-budget multi-format context from `2/3` to `3/3` cases with expected
  evidence selected.
- The MDN no-cache case now selects expected evidence into context. The DOCX
  case still selects two of three expected chunks, but the release-readiness
  stage counts case-level completeness and is now green for all three cases.
- `release-readiness-after-fit-compaction-defaults.json` now has one warning
  stage: `general_web_retrieval`.

Remaining retrieval warning:

- `general_web_retrieval` remains a ranking/MRR warning. Current evidence-score
  diagnostics show that broad overview chunks can score higher than expected
  chunks, so this needs a stricter public-web multi-evidence ranking diagnostic
  before any further scoring changes.
