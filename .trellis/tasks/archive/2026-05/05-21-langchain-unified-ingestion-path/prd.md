# LangChain Unified Ingestion Path

## Goal

Merge the optional LangChain loader/splitter adapter into a real, explicit
ingestion option so TagMemoRAG can index additional document types such as HTML
without losing the stability of the current native `.md` / `.txt` / `.pdf`
parser.

## User Value

- Use LangChain's broad loader ecosystem instead of hand-writing every future
  document loader.
- Keep existing product-manual retrieval quality and chunk identity behavior
  stable by default.
- Give operators a clear switch for expanded document support and clear errors
  when the optional dependency is not installed.

## Confirmed Facts

- Native rebuild currently scans only `SUPPORTED_DOCUMENT_SUFFIXES` from
  `parser.py`: `.md`, `.txt`, and `.pdf`.
- C1 added an optional `langchain` extra and `tagmemorag.langchain_adapter`
  with loaders for `.md`, `.txt`, `.pdf`, `.html`, and `.htm`.
- C1 did not route production rebuilds or incremental rebuilds through
  LangChain.
- `chunk_identity.parser_signature()` currently tracks parser sizing,
  overlap, PDF profile, and heading hints, but not a parser provider.

## Requirements

- **R1 — Explicit provider switch.** Add parser configuration that can choose
  native-only behavior or LangChain-extended behavior. Native remains default.
- **R2 — Unified suffix discovery.** Rebuild paths must discover the correct
  supported suffix set for the selected parser provider.
- **R3 — Expanded type support.** With LangChain enabled and optional
  dependency installed, `.html` and `.htm` documents can be parsed into chunks
  and indexed.
- **R4 — Native default preservation.** Existing `.md`, `.txt`, and `.pdf`
  native parser behavior and tests remain unchanged when the provider is
  native/default.
- **R5 — Clear missing-extra failure.** If LangChain provider is selected but
  the optional dependency is missing, rebuild fails with a clear sanitized
  configuration-style error, not an import traceback or silent skip.
- **R6 — Chunk identity compatibility.** Parser provider participates in
  parser signature or equivalent identity gating so incremental reuse does not
  mix native and LangChain chunk outputs.
- **R7 — Safe metadata.** LangChain metadata exposed on chunks remains bounded
  and sanitized; no raw text, absolute paths, vectors, or secrets appear in
  reports/logs/debug artifacts.
- **R8 — Eval gate discipline.** `coffee.jsonl` and `product_manuals.jsonl`
  must remain green for native/default mode; LangChain-expanded mode needs at
  least a small HTML fixture build/search test.

## Acceptance Criteria

- [x] Native/default config indexes `.md`, `.txt`, and `.pdf` through the
      existing native parser.
- [x] LangChain-enabled config indexes `.html` / `.htm` through the adapter.
- [x] Missing LangChain optional dependency produces a clear sanitized failure.
- [x] Parser signature changes when the provider changes.
- [x] Existing parser, chunk identity, and native eval gates remain green.
- [x] Tests cover HTML ingestion and default suffix preservation.
- [x] No production secrets/raw text/absolute paths are emitted in diagnostics.

## Completion Notes

- Added `parser.provider` with default `native` and opt-in `langchain`.
- Added `parser_provider.py` as the unified suffix discovery and parser
  dispatch boundary.
- Full rebuild, dirty chunk estimation, incremental rebuild, shadow build, and
  manual-library validation now use the effective parser provider.
- LangChain HTML parsing uses BeautifulSoup with Python's built-in
  `html.parser`, avoiding an extra `lxml` dependency.

## Out of Scope

- Replacing WAVE retrieval, QueryPlan, PlanLog, reranker, or answer generation.
- Making LangChain the default parser provider in this task.
- Supporting every LangChain loader type immediately.
- Refreshing eval baselines.
