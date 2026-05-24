# Implementation Plan

## Phase 1: Diagnose

1. [x] Summarize `general_web_retrieval` weak cases from
   `.tmp/eval/general-web-after-evidence-prior.json`.
2. [x] Summarize `multiformat_context_tight` weak cases from
   `.tmp/eval/context-quality-multiformat-budget260-after-adjacent-merge.json`.
3. [x] Write `diagnostic-notes.md` with the candidate safe levers and rejected
   risky levers.

## Phase 2: Hardening Batch

4. [x] Implement the smallest safe ranking or context hardening change exposed
   by Phase 1.
5. [x] Add focused unit tests for changed scoring, ranking, compression, or
   context selection behavior.
6. [x] Document rejected tuning attempts in `diagnostic-notes.md`.

## Phase 3: Full Matrix

7. [ ] Rerun general-web retrieval and answer diagnostics.
8. [x] Rerun multi-format retrieval, context-quality, and answer diagnostics.
9. [ ] Rerun mixed-domain retrieval, real-manual retrieval, and product-manual
   QA answer quality.
10. [x] Regenerate release-readiness JSON and Markdown.

## Phase 4: Finish

11. [x] Update task notes with final metrics and remaining risks.
12. [x] Run focused unit tests and any lint/type checks used by touched modules.
13. [ ] Commit the coherent hardening batch.

## Validation Commands

```bash
scripts/seed_general_web_eval.sh
.venv/bin/python -m tagmemorag eval run \
  --suite tests/fixtures/eval/general_web.jsonl \
  --docs .tmp/general-web-eval/general_web \
  --config examples/config/local-hashing-npz.yaml \
  --kb general_web \
  --top-k 8
.venv/bin/python scripts/diag_general_web_answer_eval.py \
  --docs .tmp/general-web-eval/general_web \
  --suite tests/fixtures/eval/general_web.jsonl \
  --config examples/config/local-hashing-npz.yaml \
  --kb general_web \
  --top-k 8

.venv/bin/python scripts/seed_multiformat_real_knowledge.py \
  --output-dir .tmp/multiformat-real-knowledge \
  --kb multiformat_real
.venv/bin/python -m tagmemorag eval run \
  --suite tests/fixtures/eval/multiformat_real_knowledge.jsonl \
  --docs .tmp/multiformat-real-knowledge/multiformat_real \
  --config examples/config/local-hashing-npz.yaml \
  --kb multiformat_real \
  --top-k 8
.venv/bin/python scripts/diag_context_quality.py \
  --docs .tmp/multiformat-real-knowledge/multiformat_real \
  --suite tests/fixtures/eval/multiformat_real_knowledge.jsonl \
  --config examples/config/local-hashing-npz.yaml \
  --kb multiformat_real \
  --top-k 8 \
  --token-budget 260
.venv/bin/python scripts/diag_multiformat_answer_eval.py \
  --docs .tmp/multiformat-real-knowledge/multiformat_real \
  --suite tests/fixtures/eval/multiformat_real_knowledge.jsonl \
  --config examples/config/local-hashing-npz.yaml \
  --kb multiformat_real \
  --top-k 8

.venv/bin/python scripts/diag_mixed_domain_eval.py \
  --stage-from-defaults \
  --suite tests/fixtures/eval/mixed_knowledge.jsonl \
  --config examples/config/local-hashing-npz.yaml \
  --kb mixed_knowledge
.venv/bin/python -m tagmemorag eval run \
  --suite tests/fixtures/eval/realmanuals.jsonl \
  --docs product_manuals \
  --config examples/config/qa-demo.yaml \
  --kb product_manuals \
  --top-k 8
.venv/bin/python -m tagmemorag eval answer-quality \
  --suite tests/fixtures/answer_quality/qa_product_manual.jsonl

.venv/bin/pytest tests/unit/test_lexical_search.py tests/unit/test_retrieval.py tests/unit/test_answer_generator.py tests/unit/test_release_readiness.py -q
```

## Risk Points

- Broad ranking priors can reduce recall even when MRR improves.
- Tight-budget context changes can accidentally drop complementary evidence or
  citation lineage.
- Real web and multi-format seeders fetch external stable sources into `.tmp/`;
  do not commit fetched document bodies.
