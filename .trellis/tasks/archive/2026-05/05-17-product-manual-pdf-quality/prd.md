# Product manual PDF structure and retrieval quality

## Goal

Make TagMemoRAG materially better on product-manual PDFs by improving the structure of indexed chunks and turning the real-manual diagnostic into an actionable quality loop. The focus is **not** generic multi-domain RAG. The generic metadata work remains a foundation; this task should make device/product manuals work well enough for the current product direction.

## Background / Known Context

- User direction: do not expand into multi-domain chunking now; first make product manuals solid.
- Current parser supports `.md`, `.txt`, and `.pdf`.
- Current PDF parsing in `src/tagmemorag/parser.py` uses `pypdf.PdfReader` and creates one raw chunk per page with `header="Page N"` and `path=("Page N",)`.
- Archived real-manual eval found the main bottleneck is not algorithm flags: `vec-only`, `wave-baseline`, `wave-residuals`, and `wave-resonance` all produced the same routing metrics on current PDF page chunks.
- `tests/fixtures/eval/realmanuals.jsonl` currently contains 12 realistic product-manual queries, but relevant expectations are placeholders, so it is informational rather than a strict gate.
- Product manuals in `product_manuals/` currently include 5 real PDFs:
  - ASKO W6564 washer
  - HISENSE BSA5221 oven
  - HISENSE DHGA901NL dryer
  - HISENSE DHQE800BW2 dryer
  - HISENSE HR6FDFF701SW refrigerator
- Previous task added metadata narrowing, so model / brand / category identity can now narrow candidate scope before ranking.

## Problem

Page-level PDF chunks are too coarse and structurally flat:

- One page can mix multiple unrelated topics.
- Headers are synthetic page labels, not section titles.
- Graph edges lose parent / child / sibling semantics, leaving mostly consecutive-page structure.
- Ground truth for real manuals is not strict enough to tell whether parser/chunking changes improve product-search quality.

This makes the retrieval system look worse than its core algorithm because the input chunks do not represent the logical structure of manuals.

## Product Direction

For product manuals, retrieval should behave like this:

- User asks a model/category-specific question.
- Metadata narrowing restricts the candidate set to the right manual/category when possible.
- Chunks represent manual sections, troubleshooting rows, or focused page regions rather than entire pages.
- Search results expose useful headers/path/page context so a user can identify the manual section.
- A real-manual eval suite can catch regressions in routing and exact section retrieval.

## Requirements

### R1 Product-manual PDF structure extraction

- Improve PDF parsing beyond one chunk per page.
- Preserve page number metadata for every PDF chunk.
- Detect useful section-like boundaries using lightweight deterministic heuristics available from `pypdf`.
- The MVP should not require OCR or heavyweight external services.
- Scanned image-only PDFs may remain unsupported, but failure mode must be documented.

Recommended MVP:

- Use `pypdf` layout extraction and/or visitor text metadata where available.
- Identify candidate headings using text features such as:
  - short standalone lines
  - numbered headings (`1`, `1.2`, `3.4.5`)
  - all-caps / title-like lines
  - common manual headings (`Troubleshooting`, `Maintenance`, `Installation`, `Operation`, `Safety`, Chinese equivalents)
  - repeated table-of-content style lines should not become chunks by themselves.
- Build chunks under detected section headers where possible.
- Fall back to page chunks when no reliable structure exists.

### R2 Product-manual chunk metadata

- Add PDF-specific metadata to chunks:
  - `page_start`
  - `page_end`
  - `pdf_header_source` or equivalent debug marker (`detected`, `page_fallback`)
  - existing manual metadata / generic document metadata must remain intact.
- Result objects should continue to expose existing fields without breaking API compatibility.
- Optional debug metadata should not leak full document text.

### R3 Chunk quality for manual retrieval

- Keep chunks focused enough for operation / maintenance / troubleshooting questions.
- Avoid exploding chunk count uncontrollably.
- Do not split tables or short procedure lists into meaningless fragments when a page section should stay together.
- Keep deterministic behavior for unit tests and eval reproducibility.

### R4 Real-manual eval ground truth

- Convert at least the highest-value subset of `realmanuals.jsonl` from placeholder expectations to real expectations.
- Cover at minimum:
  - washer operation / safety / drain-related question
  - dryer program / not-dried / ionizer question
  - oven cooking system / steam clean question
  - refrigerator ice maker / display / troubleshooting question
- Each strict case should match by stable fields that survive parser improvements:
  - `source_file`
  - `metadata.product_model` or category where useful
  - `text_contains`
  - optionally `page_start` / `page_end` once available
- Keep any not-yet-labeled query explicitly informational rather than silently placeholder-gated.

### R5 Retrieval integration

- Ensure API/CLI/eval search paths benefit from metadata narrowing and improved chunks.
- If eval runner still bypasses auto narrowing, either integrate narrowing there or document why diagnostic scripts cover the behavior.
- Existing `product_manuals.jsonl` hashing CI must remain green.

### R6 Diagnostics

- Add a lightweight parser-quality diagnostic or report that records:
  - chunks per manual
  - fallback-page chunk count
  - detected-section chunk count
  - example headers for each real PDF
  - realmanuals routing / strict retrieval metrics before/after if practical.

## Non-Functional Requirements

- Deterministic and offline-testable.
- No mandatory network dependency.
- Avoid new heavyweight dependencies unless the MVP clearly cannot work with `pypdf`.
- Backward compatible with current Markdown/TXT parsing.
- Backward compatible with existing manual library rebuild, incremental rebuild, Qdrant sync, and result shapes.
- Performance should remain acceptable for the current 5 real PDFs and managed-library rebuilds.

## Acceptance Criteria

- [ ] Product-manual PDF parsing produces section-like chunks when reliable headings are detected.
- [ ] PDF chunks include page metadata (`page_start` / `page_end`) and a parser-source marker.
- [ ] Fallback behavior still indexes PDFs with no detected structure.
- [ ] Existing Markdown/TXT parser tests continue to pass.
- [ ] New parser unit tests cover heading detection, page fallback, metadata preservation, and chunk splitting/merging.
- [ ] At least 8 realmanuals eval cases have non-placeholder expectations.
- [ ] Real-manual diagnostic/report shows parser chunk statistics and retrieval metrics.
- [ ] Existing full tests pass.
- [ ] Hashing eval CI passes.

## Out of Scope

- General multi-domain RAG chunking strategy.
- Full OCR for scanned PDFs.
- Heavy parser pipeline such as `marker-pdf` / `unstructured` unless the lightweight MVP fails and the trade-off is explicitly accepted.
- Full UI redesign.
- Renaming `/manuals` to `/documents`.
- More WAVE algorithm flag tuning as the primary solution.

## Open Questions

- Should the first implementation prioritize **low-risk pypdf heuristics** or jump directly to a stronger PDF parser dependency?

## Recommendation

Use low-risk `pypdf` heuristics first. This keeps the task small, deterministic, and compatible with current deployment. If the resulting chunk stats / realmanuals strict cases are still weak, create a follow-up task for a stronger parser/OCR pipeline with evidence in hand.

## Research References

- Archived task: `.trellis/tasks/archive/2026-05/05-17-pdf-manual-real-eval/`
- Empirical report: `.trellis/tasks/archive/2026-05/05-17-pdf-manual-real-eval/research/realmanuals-eval-report.md`
- Current parser: `src/tagmemorag/parser.py`
- Real manual fixture: `tests/fixtures/eval/realmanuals.jsonl`
- Real manuals: `product_manuals/`
