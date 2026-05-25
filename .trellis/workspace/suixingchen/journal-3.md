# Journal - suixingchen (Part 3)

> Continuation from `journal-2.md` (archived at ~2000 lines)
> Started: 2026-05-24

---



## Session 93: Journal rollover

**Date**: 2026-05-24
**Task**: Journal rollover
**Branch**: `codex/agent-loop-driver`

### Summary

Opened the next Trellis journal because journal-2.md was near the 2000-line threshold. No product, spec, or runtime code changes; this is workspace maintenance so future session records append to journal-3.md instead of pushing journal-2.md past the limit.

### Main Changes

(Add details)

### Git Commits

(No commits - planning session)

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 94: General-web ranking pressure diagnostic

**Date**: 2026-05-24
**Task**: General-web ranking pressure diagnostic
**Branch**: `codex/agent-loop-driver`

### Summary

Added an offline bounded diagnostic for general-web eval reports that identifies cases where expected evidence is reachable but under-ranked. The retained general-web report now produces two ranking-pressure items, both GitHub Hello World cases, while MDN stays resolved after evidence-label refinement. Added JSON/Markdown output and unit tests for classification, privacy defaults, and CLI output.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `9b62b40` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 95: Release readiness ranking pressure hint

**Date**: 2026-05-24
**Task**: Release readiness ranking pressure hint
**Branch**: `codex/agent-loop-driver`

### Summary

Surfaced optional general-web ranking pressure counts in release readiness as a non-blocking passed-status hint, with focused tests and validation preserving privacy boundaries.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `1c3015a` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 96: GitHub ranking pressure root cause

**Date**: 2026-05-24
**Task**: GitHub ranking pressure root cause
**Branch**: `codex/agent-loop-driver`

### Summary

Diagnosed the two GitHub Hello World general-web ranking-pressure cases, confirmed they are top-k hits with low MRR from overview/workflow chunks outranking answer-specific evidence, and kept runtime ranking unchanged pending a broader reranking batch.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `08acf40` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 97: Reranking evaluation gate plan

**Date**: 2026-05-24
**Task**: Reranking evaluation gate plan
**Branch**: `codex/agent-loop-driver`

### Summary

Planned the broader reranking/evidence-usefulness evaluation gate for future ranking changes, including required release slices, GitHub pressure baselines, privacy constraints, and ship gates that preserve passed release readiness.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `422c42e` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 98: Reranking evaluation gate runner

**Date**: 2026-05-24
**Task**: Reranking evaluation gate runner
**Branch**: `codex/agent-loop-driver`

### Summary

Added an offline reranking evaluation gate that compares baseline and candidate readiness/ranking-pressure reports, emits bounded JSON or Markdown, and fails unsafe candidates before future ranking changes can ship.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `f6168a5` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 99: Document reranking evaluation gate

**Date**: 2026-05-24
**Task**: Document reranking evaluation gate
**Branch**: `codex/agent-loop-driver`

### Summary

Documented when and how to run the reranking evaluation gate in the README and eval baseline workflow, including example commands, exit codes, and bounded-output privacy rules.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `c7efc9f` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 100: Complete general RAG stability program

**Date**: 2026-05-25
**Task**: Complete general RAG stability program
**Branch**: `codex/agent-loop-driver`

### Summary

Completed the long-running general RAG stability parent: same-page ordering moved from diagnostics through guarded default-on rollout, with rollback config preserved and final gates passing.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `d1c479a` | (see git log) |
| `bcffa6c` | (see git log) |
| `b77af8c` | (see git log) |
| `60dc36b` | (see git log) |
| `fe7a9fb` | (see git log) |
| `713c748` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 101: Local QA demo path

**Date**: 2026-05-25
**Task**: Local QA demo path
**Branch**: `codex/agent-loop-driver`

### Summary

Added an offline demo qa CLI path for the seeded coffee-machine RAG fixture, documented the workflow, and verified the answer/evidence smoke path.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `13848a9` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 102: Web QA RAG validation

**Date**: 2026-05-25
**Task**: Web QA RAG validation
**Branch**: `codex/agent-loop-driver`

### Summary

Validated the browser QA RAG flow with the local demo KB and tightened the QA route evidence window so first-screen answers avoid weak related sources.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `6a2511c` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 103: Manual library to QA smoke

**Date**: 2026-05-25
**Task**: Manual library to QA smoke
**Branch**: `codex/agent-loop-driver`

### Summary

Added and validated a deterministic local smoke for managed manual upload, rebuild, and QA answer against the newly added manual content.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `8b75b08` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 104: Document browser RAG user flow

**Date**: 2026-05-25
**Task**: Document browser RAG user flow
**Branch**: `codex/agent-loop-driver`

### Summary

Documented the local managed-manual RAG user path and added an opt-in browser smoke covering Manual Library to QA with cited demo-service-manual evidence.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `3548529` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 105: Browser upload QA smoke

**Date**: 2026-05-25
**Task**: Browser upload QA smoke
**Branch**: `codex/agent-loop-driver`

### Summary

Added an opt-in browser smoke that uploads a manual through the Manual Library UI, triggers rebuild, verifies searchable/clear state, then asks the QA page and checks cited uploaded-manual evidence.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `928ee6d` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete
