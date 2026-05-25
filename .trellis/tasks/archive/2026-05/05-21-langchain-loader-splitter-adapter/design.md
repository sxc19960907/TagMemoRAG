# LangChain Loader and Splitter Adapter Spike — Design

## Scope

This child task evaluates LangChain document loaders and text splitters through
an optional adapter. It does not replace the current parser/chunker as the
default rebuild path. The output should make it cheap to compare LangChain
behavior against TagMemoRAG's native parser on controlled fixtures.

## Current Baseline

- Native ingestion supports `.md`, `.txt`, and text `.pdf` through
  `tagmemorag.parser`.
- Rebuild paths call `parse_document()` / `parse_document_with_ocr_summary()`
  from `state.py`, `incremental_rebuild.py`, and `indexgen/shadow_build.py`.
- Chunk identity compatibility depends on parser settings captured by
  `chunk_identity.parser_signature()`.
- Existing chunk lineage metadata includes `parser_profile`, `parser_version`,
  `lineage_id`, `chunk_id`, and source/page fields.
- `pyproject.toml` has no LangChain dependency today.

## Architecture

Add a narrow optional adapter boundary, not a broad framework rewrite.

```text
fixture/source file
  -> native parse_document(...)
  -> optional langchain adapter parse_langchain_document(...)
  -> comparable ChunkComparisonReport
  -> tests / eval gate notes
```

Recommended module shape:

- `src/tagmemorag/langchain_adapter/__init__.py`
- `src/tagmemorag/langchain_adapter/loader_splitter.py`
- `src/tagmemorag/langchain_adapter/compare.py`

The adapter returns existing `Chunk` objects or a task-local comparison model
that can be converted to `Chunk`. This keeps downstream contracts familiar and
avoids introducing LangChain document objects outside the adapter package.

## Dependency Boundary

LangChain must be optional. Import failures should produce a clear
adapter-local error or skip path; importing `tagmemorag.parser`, building a KB,
or running default tests must not require LangChain.

Preferred dependency shape:

- Add a new optional extra in `pyproject.toml`, for example
  `langchain = ["langchain-core>=...", "langchain-community>=...", "langchain-text-splitters>=..."]`.
- Do not add LangChain packages to base `dependencies`.
- Tests that import LangChain directly should skip when the extra is missing.

## Data Contract

Adapter-created chunks must preserve:

- `source_file`
- input metadata such as `manual_id`, tags, category, model, and brand
- deterministic ordering
- `parser_profile` clearly names the adapter, for example
  `langchain:<loader>:<splitter>`
- `parser_version` is adapter-specific and included in metadata
- no raw text in logs, exceptions, or debug summaries

If the adapter supports a new source type such as HTML, that suffix must stay
outside `SUPPORTED_DOCUMENT_SUFFIXES` unless the task also adds explicit
rebuild integration and eval proof.

## Comparison Strategy

The spike should compare native and LangChain output on:

- Markdown fixture
- TXT fixture
- PDF fixture, using a mocked/minimal PDF when possible
- one new loader type only if the optional dependency and test fixture remain
  lightweight

Metrics should be structural and safe:

- chunk count
- min/median/max chunk length
- source/page metadata coverage counts
- parser profile names
- text hash samples, not raw text

This comparison is not a quality win by itself. Any recommendation to switch
defaults needs retrieval eval evidence from `coffee.jsonl` and
`product_manuals.jsonl`.

## Compatibility

- Default `parse_document()` behavior remains unchanged.
- Existing parser tests remain authoritative for native behavior.
- Incremental rebuild fallback on parser config changes must not be weakened.
- Qdrant payload safety rules still apply: no raw chunk text or unbounded
  metadata dumps in generated reports.

## Rollback

Rollback is deleting the adapter package, tests, optional dependency entry, and
comparison docs. Because default rebuild paths remain native, rollback should
not require data migration.
