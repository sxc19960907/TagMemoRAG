# General knowledge RAG robustness benchmark

## Goal

Reframe TagMemoRAG's next quality work from a product-manual-only RAG into a
general robust RAG benchmark path. Product manuals remain the first validated
domain, but the system must also prove it can ingest, retrieve, and answer over
other realistic public knowledge sources with different structure, vocabulary,
and reliability risks.

The first implementation slice should make evaluation less brittle against
real-document formatting noise, then add a small curated benchmark plan for
multiple public knowledge-source families.

## Confirmed Facts

- Current README still positions the engine primarily as "for product manuals".
- The codebase already has generic document contracts (`doc_id`, `domain`,
  `doc_type`, `attributes`) alongside manual-specific metadata.
- Existing eval fixtures are heavily manual/coffee-machine oriented.
- Recent real ManualsLib validation showed retrieval can succeed while
  `text_contains` can undercount correct hits because PDF/OCR extraction inserts
  line breaks or other whitespace inside expected phrases.
- Public candidate sources exist for a broader benchmark:
  - Software docs: Python documentation, GitHub Docs.
  - Government/policy PDFs or HTML: IRS publications.
  - Health/public information: MedlinePlus / NIH pages.
  - Help centers and FAQ-style docs: public support/help sites.

## Requirements

- Preserve product-manual eval compatibility.
- Make eval `text_contains` matching robust to whitespace and control-character
  extraction noise while keeping exact source/header/anchor/metadata matching
  semantics unchanged.
- Preserve raw eval report data; normalization should affect matching only, not
  rewrite stored expectations or snippets.
- Define an initial general-knowledge benchmark direction covering at least four
  source families with realistic RAG failure modes.
- Do not commit downloaded third-party document content in this first slice.
- Use only public, attributable sources for benchmark candidates.

## Acceptance Criteria

- [ ] Unit tests prove `text_contains` can match expected phrases across PDF/OCR
      line breaks, repeated whitespace, and non-printing control characters.
- [ ] Existing eval matching tests continue to pass, including missing-text
      rejection and metadata/source matching behavior.
- [ ] A planning artifact identifies the first public source families and the
      robustness risks each family is meant to test.
- [ ] Focused pytest validation passes for eval matching.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
