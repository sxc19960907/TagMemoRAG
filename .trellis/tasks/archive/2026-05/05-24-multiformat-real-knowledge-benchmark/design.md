# Design

## Architecture

Build a new opt-in multi-format benchmark lane on top of the existing build/eval pipeline:

1. Source list stores public URLs plus source-format metadata.
2. Materializer downloads or fetches documents into `.tmp/multiformat-real-knowledge/`.
3. HTML uses the existing `public_web_import` path and becomes Markdown.
4. PDF is saved as `.pdf` plus a metadata sidecar, then parsed by the native PDF parser during build.
5. DOCX is converted to Markdown with metadata sidecar, then parsed by the native Markdown parser during build.
6. `tagmemorag eval run` builds the corpus and validates retrieval.
7. A live answer diagnostic validates final generated answers from retrieved context.

This keeps parser/build contracts stable while adding format diversity at the source-materialization layer.

## Data Flow

```text
Public URL manifest
  -> materialize script
  -> .tmp/multiformat-real-knowledge/<kb>/...
  -> native build_kb / eval run
  -> retrieve payload
  -> noop answer generator / answer-quality diagnostic
```

## Contracts

Each materialized document must have a `.metadata.json` sidecar with:

- `manual_id`: stable safe id derived from source URL or explicit manifest id.
- `source_file`: relative path under the KB corpus.
- `domain`: domain category such as `software_docs`, `public_service`, or `technical_standard`.
- `doc_type`: e.g. `documentation`, `help_article`, `pdf_report`, `docx_guidance`.
- `remote_id` / `url`: original public source URL.
- `source_format`: original source format (`html`, `pdf`, `docx`).
- `tags`: bounded human-readable tags.

## Source Selection

Prefer stable official documents with extractable text and permissive public access. Candidate types:

- HTML: reuse existing general-web sources such as MDN or USAGov.
- PDF: public government/standards/report PDF with stable headings and body text.
- DOCX: public guidance/template document available from a stable official source. If direct DOCX sources are unreliable, use an explicitly documented fallback that converts a stable Word-compatible OpenXML sample downloaded from a public source.

## Optimization Policy

This task may include one tightly scoped optimization only after the multi-format eval exposes a concrete failure. Examples:

- Metadata/source-format preservation if eval cannot filter by format.
- DOCX materialization cleanup if paragraphs/tables are unreadable.
- PDF generic heading profile adjustment if real online PDF chunks are too noisy.

Avoid broad ranking rewrites in the same task.

## Compatibility

- Existing `general_web` and `mixed_knowledge` suites remain unchanged except for documentation references.
- The new multi-format suite remains opt-in and excluded from fixture-only CI if it depends on runtime materialized docs.
- Build path remains `.md/.txt/.pdf`; DOCX conversion happens before build.

## Rollback

Remove the new script, suite, and docs. Existing real-web and realmanuals benchmarks continue to run independently.
