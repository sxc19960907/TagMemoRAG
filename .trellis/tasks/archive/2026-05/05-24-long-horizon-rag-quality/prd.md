# Long-horizon RAG quality program

## Goal

Run a longer, continuous RAG quality program instead of stopping after every tiny fix. The work should improve TagMemoRAG as a general-purpose RAG system across real public-web docs, real product manuals, mixed-domain KBs, and multi-format sources.

The user intent is explicit: plan and execute a larger arc of work, not a single narrow patch followed by a stop.

## Requirements

- Build and maintain a single quality baseline matrix across the current real eval slices:
  - general public-web retrieval and answer quality
  - multi-format real knowledge retrieval and answer quality
  - mixed-domain shared-KB retrieval
  - real product manual retrieval
  - existing product-manual answer-quality fixtures
- Expand or improve real-data coverage where the current matrix is thin, using public, stable, non-news sources and avoiding checked-in third-party document bodies.
- Diagnose weaknesses from per-case reports before making retrieval, parser, context-packing, or answer-generation changes.
- Implement improvements in coherent batches: finish a diagnosis plus at least one meaningful validated improvement before reporting completion.
- Preserve safety boundaries from prior work:
  - no WAVE/geodesic promotion without separate evidence
  - no external reranker on the critical path unless explicitly planned and evaluated
  - no broad lexical boosts that regress product manuals or mixed-domain ranking
  - no committing downloaded third-party PDFs/DOCX/HTML bodies
- Keep API/CLI slimming work out of scope unless it directly blocks this RAG quality program.
- Leave unrelated untracked files such as `.codegraph/` and `.mcp.json` untouched.

## Acceptance Criteria

- [ ] A retained baseline matrix records metrics for all current real retrieval and answer-quality slices.
- [ ] At least one real-data coverage improvement lands, or a diagnostic proves that existing coverage is sufficient for the current phase.
- [ ] At least one retrieval/ranking/context/answer-quality improvement lands and is verified against the full baseline matrix.
- [ ] Any regression or rejected optimization attempt is documented with the reason it was rejected.
- [ ] Architecture/spec notes and journal entries describe the final state and next recommended phase.
- [ ] Work is committed as one or more coherent commits, not a chain of tiny unexplained patches.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
