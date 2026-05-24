# Implementation Plan

1. [x] Inspect multi-format eval `actual_top_k` for weak cases.
2. [x] Correct the DOCX eval expectations to match real chunk boundaries.
3. [x] Rerun multi-format retrieval eval and compare metrics.
4. [x] Rerun multi-format answer eval.
5. [x] If corrected eval still fails, implement a tightly scoped ranking/parser fix.
6. [x] Run focused tests and `git diff --check`.
7. [ ] Archive task, commit, and journal.
