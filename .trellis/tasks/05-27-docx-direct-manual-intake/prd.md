# Docx direct manual intake

## Goal

Allow normal users to upload `.docx` manuals/documents through the existing Manual Library and QA upload paths by converting readable OpenXML text into Markdown before indexing.

## User Value

Users often have Word documents rather than Markdown or PDF files. Since the project already has a limited `.docx` OpenXML-to-Markdown extractor in the multiformat seeding script, promote that capability into the managed intake path so users can upload `.docx` files without command-line preprocessing.

## Requirements

- Accept `.docx` files in Manual Library upload, bulk import, file replace, and QA-page upload.
- Convert `.docx` content into Markdown before writing the managed library source file, so the existing parser/indexer can continue to process `.md`.
- Preserve original-source metadata:
  - `source_format=docx`;
  - `remote_id` or equivalent original file name when available.
- Keep existing `.md`, `.txt`, and `.pdf` behavior unchanged.
- Fail malformed/unreadable `.docx` uploads with a clear validation/input error.
- Update browser file accept hints and quick-start documentation.
- Add unit/static tests for conversion, metadata preservation, validation, and upload UI hints.

## Acceptance Criteria

- [ ] Direct `.docx` upload through `upsert_manual` stores a `.md` managed source and indexes extracted text.
- [ ] Metadata preserves `source_format=docx` and an original filename marker.
- [ ] `.docx` is accepted by Manual Library / QA file pickers.
- [ ] Direct `.doc` remains unsupported with a clear error.
- [ ] Malformed `.docx` fails clearly.
- [ ] Focused parser/manual-library/UI/documentation tests pass.
- [ ] `git diff --check` passes.

## Out Of Scope

- Legacy binary `.doc` support.
- Full Word layout fidelity, tables, comments, images, headers/footers, or tracked changes.
- OCR or scanned document support.
- Live provider or GitHub push.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
