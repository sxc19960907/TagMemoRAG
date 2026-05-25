# Manualslib real manual validation

## Goal

Make it easy to expand real-manual RAG validation with ManualsLib Hisense manuals while continuing to improve retrieval and answer quality against realistic product documentation.

## Requirements

- Use the ManualsLib Hisense brand/manual pages as a source of additional real manuals, starting with a small deterministic sample rather than unbounded bulk crawling.
- Prefer reproducible tooling over committing third-party manual content. Downloaded/extracted manuals should be local runtime artifacts unless explicitly curated later.
- Support concrete manual URLs, not broad automatic crawling, so operators can choose categories/models and avoid accidental large downloads.
- Produce files that the existing TagMemoRAG ingestion path can build directly: a supported text/PDF document plus a `<manual>.metadata.json` sidecar.
- Preserve source attribution metadata such as source URL, brand, product model, category, language, and import source.
- Keep the tool network-optional in tests by covering parsing/materialization with local fixture HTML.
- Validate with at least one real ManualsLib Hisense manual sample under `.tmp/`, plus the existing realmanuals and answer-quality gates.
- Do not bypass website interaction barriers or authenticated areas; if PDF download requires browser/user interaction, use the browser-readable manual page as the first supported source.

## Acceptance Criteria

- [x] A ManualsLib import/materialization utility exists and can convert a supplied manual URL into local manual document files compatible with `build_kb`.
- [x] Unit tests cover parsing a ManualsLib-like page into markdown sections and metadata without network.
- [x] A small real ManualsLib Hisense sample is materialized under `.tmp/` and successfully built/searched or evaluated with the hashing profile.
- [x] Existing focused retrieval/answer tests pass.
- [x] The current `product_manuals` real PDF retrieval slice does not regress.
- [x] Any durable lesson about third-party real-manual ingestion is captured in `.trellis/spec/`.

## Result

Added `python -m tagmemorag manualslib import-url` for explicit ManualsLib manual URLs. It extracts browser-visible PDF text from page HTML, writes markdown plus a metadata sidecar, and keeps real imported samples as local runtime artifacts.

Real sample used: `https://www.manualslib.com/manual/4119276/Hisense-Dh105m3-Series.html`, imported to `.tmp/manualslib-hisense-sample` with `--max-pages 30`. The sample built successfully as `manualslib_hisense` with 122 chunks and search returned relevant capacity/program-table evidence. It also exposed a future ranking target: generic `drying` evidence can outrank `program`/`cycle selector` intent when the query is phrased as "how to choose drying program".

Regression gates:

- `tests/unit/test_manualslib_import.py tests/unit/test_cli.py`: passed.
- realmanuals retrieval: `hit@5=1.0`, `recall@5=0.966667`, `mrr=0.691667`.
- answer-quality: passed 6 cases.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
