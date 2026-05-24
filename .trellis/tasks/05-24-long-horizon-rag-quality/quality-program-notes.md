# Quality Program Notes

## Intent

This task intentionally groups multiple RAG quality steps into one longer work arc. Do not stop after a single tiny patch unless a regression, missing product decision, or external dependency blocks the phase.

## Starting Context

Recent completed work:

- Public-web HTML cleanup moved the MDN HTTP caching case from a top-k miss to `hit@k=1.0`.
- Public-web compact evidence lexical scoring improved general-web MRR while preserving mixed-domain, real-manual, and multi-format baselines.

Known remaining gaps:

- Some multi-evidence public-web cases still have relevant chunks below rank 1.
- Further gains likely require explicit reranking or context-level complementary evidence objectives rather than broader lexical boosts.

## Phase 1 Baseline Matrix

Reports are retained under `.tmp/eval/long-program-*.json`.

| Slice | Cases | hit@k | recall@k | MRR | Status |
|-------|-------|-------|----------|-----|--------|
| General web retrieval | 7 | 1.000000 | 0.857143 | 0.556122 | passed |
| Multi-format retrieval | 3 | 1.000000 | 1.000000 | 0.611111 | passed |
| Mixed-domain retrieval | 4 | 1.000000 | 1.000000 | 1.000000 | passed |
| Real manuals retrieval | 10 | 1.000000 | 0.966667 | 0.708333 | passed |

Answer diagnostics:

- General web answer: 7 cases, failed=0.
- Multi-format answer: 3 cases, failed=0.
- Product-manual QA answer quality: 6 cases, all grounded/relevant/citation/refusal checks passed.

Weakest cases:

- General web: GitHub repository (`mrr=0.166667`, `recall@k=0.5`), MDN no-cache/private (`mrr=0.142857`, `recall@k=0.5`), IRS Free File (`mrr=0.333333`).
- Real manuals: `hisense-oven-steam-clean` (`mrr=0.25`, `recall@k=0.666667`), with supporting chunks at ranks 4 and 5.

Selected Phase 3 target: real-manual oven steam-clean retrieval. It is a concrete product-manual weakness with lower recall/MRR than the other manual cases, and product manuals remain a core use case while the system expands toward general RAG.

## Phase 2 Coverage Review

Current committed/opt-in real slices cover:

- Real product manuals: washer, dryer, oven, refrigerator PDFs; Chinese and English queries; troubleshooting, controls, maintenance, and operation.
- Public web: Python, GitHub, MDN, USAGov, IRS HTML-derived Markdown.
- Multi-format: HTML-derived Markdown, public PDF, DOCX-derived Markdown.
- Mixed-domain: product manuals and public web docs in one KB with wrong-domain negatives.
- Answer quality: product-manual QA and public-web/multi-format deterministic answer checks.

Decision for this phase: existing coverage is sufficient to proceed without adding another external corpus. The baseline already exposes an actionable real-manual weakness (`hisense-oven-steam-clean`) that appears in both the real-manual and mixed-domain slices. Expanding sources before fixing that would add breadth but not improve the clearest current bottleneck.

## Phase 3 Quality Batch

Target: `hisense-oven-steam-clean`.

Baseline behavior:

- Rank 1 was a sparse PDF heading-only chunk: `USING THE STEAM CLEAN FUNCTION TO`.
- The actual operating step (`Pour 0.6 l of water into a glass...`) was rank 11 in an expanded top-20 diagnostic, outside the default top-5 evidence window.
- The default top-5 still passed hit checks, but the first context item was not useful enough for answer generation.

Rejected attempt:

- Tried merging standalone PDF heading runs into the following body chunk during parser post-processing.
- Unit tests could make the narrow oven example pass, but real-manual regression fell from `hit@k=1.0 / recall=0.966667 / MRR=0.708333` to as low as `hit@k=0.9 / recall=0.7 / MRR=0.633333`.
- Root cause: parser-level chunk-shape changes disturbed legitimate product-manual chunks, especially cooking-system pages. This was not kept.

Kept improvement:

- Retrieval context now expands sparse PDF heading-only results with adjacent same-page body text when constructing evidence/context packs.
- This keeps retrieval ranking and parser chunk boundaries stable, while giving answer generation the nearby actionable text.
- Real Hisense BSA5221 check: the first Steam Clean evidence now contains `Pour 0.6 l of water...`, `After 30 minutes...`, and the damp-cloth cleanup instruction.
- Unit coverage: `tests/unit/test_retrieval.py::test_build_retrieve_response_expands_sparse_pdf_heading_with_adjacent_body`.

## Phase 4 Regression Matrix

Reports are retained under `.tmp/eval/long-program-*-after-context-expansion.json`.

| Slice | Cases | hit@k | recall@k | MRR | Status |
|-------|-------|-------|----------|-----|--------|
| General web retrieval | 7 | 1.000000 | 0.857143 | 0.556122 | passed |
| Multi-format retrieval | 3 | 1.000000 | 1.000000 | 0.611111 | passed |
| Mixed-domain retrieval | 4 | 1.000000 | 1.000000 | 1.000000 | passed |
| Real manuals retrieval | 10 | 1.000000 | 0.966667 | 0.708333 | passed |

Answer diagnostics:

- General web answer: 7 cases, failed=0.
- Multi-format answer: 3 cases, failed=0.
- Product-manual QA answer quality: 6 cases passed.

Local test command:

- `.venv/bin/pytest tests/unit/test_retrieval.py tests/unit/test_parser.py tests/unit/test_answer_generator.py -q` -> 56 passed.

Next recommended phase:

- Move from context rescue to ranking quality: demote directory/table-of-contents style chunks or add a first-class lightweight evidence usefulness score. The current batch proved that sparse heading chunks are useful entry points, but they should not be the only text passed to generation.
