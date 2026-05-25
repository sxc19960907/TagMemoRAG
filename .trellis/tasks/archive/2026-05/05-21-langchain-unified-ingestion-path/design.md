# LangChain Unified Ingestion Path — Design

## Scope

This task turns the C1 adapter into an opt-in ingestion path used by rebuild
code. It expands source discovery to LangChain-supported suffixes only when
the parser provider asks for it. Native remains the default provider.

## Configuration

Extend `ParserConfig` with a provider field:

- `provider = "native"` by default.
- `provider = "langchain"` enables LangChain loaders/splitters for all
  supported adapter suffixes.

The task may also support `"auto"` only if it can be implemented without
ambiguity. If not, use explicit `"native"` and `"langchain"` first.

## Data Flow

```text
build / incremental / shadow build
  -> supported suffixes for cfg.parser.provider
  -> parse source with selected parser provider
  -> Chunk[]
  -> existing embedder / graph / storage pipeline
```

Recommended shared helper:

- `parser_provider.py` or a narrow addition in `parser.py`
- `supported_document_suffixes(cfg.parser)`
- `parse_document_for_config(path, cfg.parser, ...)`

This avoids scattering provider checks across `state.py`,
`incremental_rebuild.py`, and `indexgen/shadow_build.py`.

## Provider Behavior

Native provider:

- Supports `.md`, `.txt`, `.pdf`.
- Calls existing `parse_document()` / `parse_document_with_ocr_summary()`.
- Preserves OCR summary behavior for PDFs.

LangChain provider:

- Supports `.md`, `.txt`, `.pdf`, `.html`, `.htm`.
- Calls `parse_langchain_document()`.
- Returns empty/default OCR summary because OCR is not part of the LangChain
  path in this task.
- Requires optional `langchain` extra at runtime; missing extra surfaces as a
  clear rebuild/config failure.

## Chunk Identity

`chunk_identity.parser_signature()` must include parser provider. This ensures
incremental rebuilds do not reuse native chunks when the operator switches to
LangChain or vice versa.

## Compatibility

- Default config produces the same native suffix set and parser behavior as
  before.
- Manual library validation and connector materialization should continue to
  use the effective supported suffix set.
- LangChain metadata remains sanitized by the existing adapter.
- No eval baseline refresh is expected because default mode remains native.

## Rollback

Rollback is removing the provider config, unified helper, LangChain rebuild
wiring, tests, and docs. Existing native parser entry points remain intact.
