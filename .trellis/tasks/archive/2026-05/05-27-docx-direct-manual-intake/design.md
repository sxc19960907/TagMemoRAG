# Docx Direct Manual Intake Design

## Existing Facts

- Native parser indexes `.md`, `.txt`, and `.pdf`.
- Existing multiformat seeding code can extract basic `.docx` OpenXML paragraphs into Markdown.
- Manual Library validates source suffix before writing source files.
- `ManualMetadata.extra` already preserves generic metadata fields such as `remote_id` and `source_format`.

## Design

Keep parser/indexing stable by normalizing `.docx` at intake time:

1. Detect `.docx` metadata source paths in Manual Library writes.
2. Convert uploaded `.docx` bytes to Markdown using a library module based on the existing OpenXML paragraph extractor.
3. Rewrite the managed `source_file` from `.docx` to `.md` before validation/writing.
4. Preserve original-source metadata:
   - `source_format=docx`;
   - `remote_id=<original source_file>`;
   - append a short notes hint when no notes are present.
5. Store/checksum the converted Markdown bytes. The managed source file becomes Markdown, so rebuild uses the existing Markdown parser.

This avoids making the core parser directly parse `.docx` and avoids adding a production dependency.

## Compatibility

- Existing `.md`, `.txt`, and `.pdf` bytes pass through unchanged.
- `.doc` remains unsupported.
- Registry and file-backed library paths both receive converted bytes/metadata before storage.
- Bulk import uses the same `upsert_manual` path for committed rows, so it inherits conversion.

## Failure Behavior

Malformed `.docx` raises `INVALID_INPUT` with a bounded message. No raw document text is included in error details.
