# Implementation Plan

1. [x] Inspect current general-web answer diagnostic report under tight token budget.
2. [x] Add a focused unit test around `build_retrieve_response`, `NoopAnswerGenerator`, and answer-quality evaluation using local synthetic chunks and a tight token budget.
3. [x] Assert the generated answer includes both complementary support points and citations.
4. [x] Run focused answer-quality/retrieval tests.
5. [x] Run seeded general-web answer diagnostic and mixed-domain diagnostic.
6. [ ] Archive task, commit, and record journal.
