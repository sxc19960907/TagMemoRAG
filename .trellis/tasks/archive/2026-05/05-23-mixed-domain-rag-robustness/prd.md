# Mixed-Domain RAG Robustness Benchmark

## Problem

TagMemoRAG has separate validation slices for real product manuals and public web documentation. That proves each domain can work in isolation, but it does not prove a shared knowledge base stays robust when very different knowledge types are indexed together.

The next mainline risk is cross-domain contamination: a product-manual query should not retrieve generic software documentation, and a documentation query should not be answered from appliance manuals just because broad words overlap.

## Goals

- Add a reproducible mixed-domain retrieval benchmark that indexes multiple knowledge families into one KB.
- Include real product manual PDFs from `product_manuals/` in the intended live validation path.
- Include public web/software documentation materialized by the existing general-web sampler path.
- Use positive expectations and negative expectations so regressions show both missed evidence and wrong-domain evidence.
- Keep the benchmark explicit and opt-in when it depends on runtime/materialized docs.

## Non-Goals

- Do not change tenant or KB isolation semantics.
- Do not add a crawler or broad website scraping.
- Do not tune ranking heuristics blindly before the mixed-domain benchmark exists.
- Do not require network access for unit tests.

## Acceptance Criteria

- A new mixed-domain eval suite exists under `tests/fixtures/eval/` with one shared `kb_name` and cases spanning product manuals and public documentation.
- A diagnostic script can build/run the mixed-domain suite from a single docs directory and produce a bounded JSON report.
- The diagnostic script can optionally stage a mixed docs directory from:
  - real manuals under `product_manuals/`
  - existing public web docs under `.tmp/general-web-eval/general_web`
- Unit tests cover the diagnostic using local fixture docs, including negative-domain assertions.
- README or nearby docs explain how to seed/run the mixed-domain validation.
- Real validation is run against available real product manuals and materialized public web docs when present.

