# General-web retrieval MRR diagnostic

## Goal

Diagnose the remaining `general_web_retrieval` release-readiness warning and make
only evidence-backed, narrow improvements that preserve the current
general-purpose RAG behavior.

The release is currently warning only because general-web retrieval MRR is below
target. All other release-readiness stages are green after the completed
fit-aware context merge compaction work. This task must keep that separation
clear: the completed context-packing optimization is not part of this task's
implementation scope.

## Confirmed Facts

- The active direction is a general-purpose RAG system, not an Agentic roadmap.
- Latest release-readiness report:
  `.tmp/eval/release-readiness-after-fit-compaction-defaults.json`.
- Only warning stage:
  `general_web_retrieval` with `hit@k=1.0`, `recall_at_k=0.928571`,
  `MRR=0.651361`; target warning threshold is `MRR >= 0.75`.
- Previously completed work fixed the tight-budget multi-format context warning
  without changing retrieval ordering.
- Existing diagnostic notes show weak general-web cases are ranking/multi-evidence
  cases, especially GitHub Hello World and MDN HTTP caching.
- Existing `lexical_evidence_score` does not reliably separate expected evidence
  chunks from broad related overview/action chunks in those weak cases.

## Requirements

- Produce a structured diagnostic for the weak general-web retrieval cases before
  changing ranking code.
- Compare expected and non-expected top-k chunks with deterministic, local
  features such as:
  - matched expected indexes
  - retrieval score and lexical evidence score
  - ordinary query-term coverage in body and heading
  - compact/proximity evidence cues
  - source/page-chrome or title-only indicators
  - definition, overview, and action/workflow cue words
  - source file and rank position
- If a stable, non-case-specific signal emerges, apply only a narrow classic-RAG
  change. The change must be deterministic and local to retrieval ranking or
  diagnostics.
- Preserve the current public-web corpus policy: fetched third-party bodies stay
  under `.tmp/` and are not committed.
- Preserve unrelated working-tree files, including `.codegraph/` and `.mcp.json`.
- Keep completed archived task work separate from this task; do not reopen or
  mix archived artifacts into implementation.

## Acceptance Criteria

- [ ] A `diagnostic-notes.md` file explains the weak cases, observed signals, and
      whether a ranking change is safe.
- [ ] If code changes are made, `general_web_retrieval` improves MRR toward or
      beyond `0.75` without reducing recall below `0.928571` or hit@k below
      `1.0`.
- [ ] If no safe code change is made, the task records why available signals are
      unsafe and what future data or fixture refinement is needed.
- [ ] Existing passed release-readiness stages remain passed after validation:
      multi-format retrieval/context/answer, mixed-domain retrieval,
      realmanuals retrieval, general-web context/answer, and product QA answer
      quality.
- [ ] No Agentic path, WAVE/geodesic change, external reranker, or broad generic
      evidence-score boost is introduced.
- [ ] Task artifacts are complete enough that the next session can resume without
      relying on chat history.

## Out of Scope

- Enabling Agentic retrieval, loop drivers, CRAG, WAVE/geodesic search, or an
  external reranker.
- Broad additive priors that reward identity fields, page titles, source files,
  or general topic overlap as ordinary evidence.
- Parser reshaping or broad HTML filtering changes.
- Committing fetched third-party page bodies or runtime eval outputs from `.tmp/`.

## Notes

- This is a complex task because it may affect retrieval ordering and release
  gates. It needs `design.md`, `implement.md`, `implement.jsonl`, and
  `check.jsonl` before activation.
