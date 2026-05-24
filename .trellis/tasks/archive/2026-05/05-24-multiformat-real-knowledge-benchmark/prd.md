# Multi-format Real Knowledge Benchmark

## Goal

Move RAG optimization onto a broad real-knowledge foundation: every benchmark document should come from real public web sources, and the benchmark should cover multiple source formats including HTML, PDF, and Word-style documents. Use the resulting eval evidence to guide overall RAG improvements across parsing, retrieval, context selection, and answer quality.

## User Value

The system should behave like a general-purpose RAG engine for arbitrary knowledge bases, not a product-manual-only or synthetic-fixture demo. Real public documents in different formats expose format conversion, parser, metadata, ranking, and answer synthesis weaknesses that short fake snippets cannot reveal.

## Confirmed Facts

- The current native parser supports `.md`, `.txt`, and text-based `.pdf` files.
- Public HTML pages are already handled through `knowledge sample-web`, which fetches real URLs and materializes Markdown plus metadata sidecars under `.tmp`.
- The current general-web benchmark covers real HTML-derived Markdown pages from Python, GitHub, MDN, USAGov, and IRS.
- Existing real manual validation covers local PDFs in `product_manuals/`, but the user's requirement is now broader: source documents should be real online knowledge docs across formats, not only the local product manual set.
- DOC/DOCX is not currently supported by the native build path. The first safe path is to materialize DOCX into Markdown with metadata, then reuse existing build/eval.
- Fetched third-party content should stay out of git; scripts, URLs, metadata contracts, and eval expectations may be committed.

## Requirements

- Add a multi-format real knowledge sampling/eval lane that can materialize public online HTML, PDF, and DOCX/DOC-style source documents into a local `.tmp` corpus.
- Use only real public source documents from the web for this benchmark; do not add fake text snippets as source docs.
- Commit no third-party fetched document bodies; keep downloads/materialized content under `.tmp` or operator-supplied runtime directories.
- Preserve source attribution in metadata: original URL, source format, domain, doc type, and stable manual/doc id.
- Add eval cases that validate at least one HTML-derived, one PDF-derived, and one DOCX-derived document in a shared knowledge base.
- Add answer-quality or answer diagnostic coverage for at least one non-HTML format when feasible in the first pass.
- Let optimization be eval-driven: if the new benchmark exposes failures, fix a tightly scoped parser/retrieval/answer issue and document the evidence.

## Acceptance Criteria

- [ ] A script or command path materializes a real multi-format corpus from public URLs into `.tmp` without committing fetched content.
- [ ] The corpus includes at least HTML-derived Markdown, a real online PDF, and a real online DOCX/DOC-style document converted/materialized for indexing.
- [ ] A committed eval suite verifies retrieval over the multi-format corpus with format/domain metadata expectations.
- [ ] The multi-format retrieval eval runs successfully with the local hashing config.
- [ ] At least one answer-quality/live answer diagnostic validates final grounded answer output for the multi-format corpus.
- [ ] Focused unit tests cover the materialization logic without network access.
- [ ] README and backend architecture docs explain the multi-format real-knowledge benchmark and its opt-in nature.

## Out of Scope

- Do not build a full production-grade crawler.
- Do not commit third-party document text, PDFs, or DOCX files.
- Do not introduce a broad new dependency stack unless the first-pass DOCX/PDF materialization cannot be handled with existing dependencies and Python standard libraries.
- Do not enable WAVE or other experimental rerank paths without eval evidence from this benchmark.
