# Journal - suixingchen (Part 2)

> Continuation from `journal-1.md` (archived at ~2000 lines)
> Started: 2026-05-22

---



## Session 53: Journal rollover

**Date**: 2026-05-22
**Task**: Journal rollover
**Branch**: `codex/agent-loop-driver`

### Summary

Opened the next Trellis journal because journal-1.md reached the 2000-line threshold. No product or code changes.

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


## Session 94: Complementary evidence ranking

**Date**: 2026-05-24
**Task**: Improve complementary evidence ranking
**Branch**: `codex/agent-loop-driver`

### Summary

Investigated the remaining low-MRR real public-web cases after HTML cleanup. The relevant evidence was generally recalled but ranked behind broad overview/reference chunks because lexical scoring rewarded scattered query-term overlap more than compact answer-bearing evidence. Added a bounded public-web-only compact-window bonus for body text, preserving product-manual and mixed-domain behavior.

### Main Changes

- Added compact-window lexical scoring for `public_web/` body fields only.
- Added a deterministic lexical regression where a definition-style pull-request evidence chunk beats a broad overview chunk.
- Documented the public-web-only boundary and the rejected broader repeated-term variant.

### Git Commits

(Pending)

### Testing

- [OK] `.venv/bin/pytest tests/unit/test_lexical_search.py tests/unit/test_eval_runner.py tests/unit/test_diag_general_web_answer_eval.py -q`
- [OK] `.venv/bin/python -m tagmemorag eval run --suite tests/fixtures/eval/general_web.jsonl --docs .tmp/general-web-eval/general_web --config examples/config/local-hashing-npz.yaml --kb general_web --top-k 8 --min-recall-at-k 0.0 --min-mrr 0.0 --min-hit-at-k 0.0 --output .tmp/eval/complementary-general-web-compact-only.json`
- [OK] `.venv/bin/python scripts/diag_general_web_answer_eval.py --docs .tmp/general-web-eval/general_web --suite tests/fixtures/eval/general_web.jsonl --config examples/config/local-hashing-npz.yaml --kb general_web --top-k 8 --output .tmp/eval/complementary-general-web-answer-final.json`
- [OK] `.venv/bin/python scripts/diag_mixed_domain_eval.py --stage-from-defaults --suite tests/fixtures/eval/mixed_knowledge.jsonl --config examples/config/local-hashing-npz.yaml --kb mixed_knowledge --top-k 5 --output .tmp/eval/complementary-mixed-domain-compact-only.json`
- [OK] `.venv/bin/python -m tagmemorag eval run --suite tests/fixtures/eval/multiformat_real_knowledge.jsonl --docs .tmp/multiformat-real-knowledge/multiformat_real --config examples/config/local-hashing-npz.yaml --kb multiformat_real --top-k 8 --min-recall-at-k 0.0 --min-mrr 0.0 --min-hit-at-k 0.0 --output .tmp/eval/complementary-multiformat-final.json`
- [OK] `.venv/bin/python scripts/diag_multiformat_answer_eval.py --docs .tmp/multiformat-real-knowledge/multiformat_real --suite tests/fixtures/eval/multiformat_real_knowledge.jsonl --config examples/config/local-hashing-npz.yaml --kb multiformat_real --top-k 8 --output .tmp/eval/complementary-multiformat-answer-final.json`
- [OK] `.venv/bin/python -m tagmemorag eval run --suite tests/fixtures/eval/realmanuals.jsonl --docs product_manuals --config examples/config/local-hashing-npz.yaml --kb realmanuals --top-k 5 --min-recall-at-k 0.0 --min-mrr 0.0 --min-hit-at-k 0.0 --output .tmp/eval/complementary-realmanuals-final.json`

### Status

[OK] **Completed**

### Next Steps

- For further gains on GitHub/MDN multi-evidence cases, prefer an explicit reranker or context-level complementary objective over broader lexical boosts.


## Session 88: Mixed-domain RAG robustness diagnostic

**Date**: 2026-05-23
**Task**: Mixed-domain RAG robustness benchmark
**Branch**: `codex/agent-loop-driver`

### Summary

Returned to the RAG quality mainline after API slimming. Added a shared-KB mixed-domain retrieval diagnostic that stages real product manuals and seeded public web docs into one corpus, then verifies positives plus wrong-domain negatives. Real validation passed on `product_manuals/` plus `.tmp/general-web-eval/general_web`.

### Main Changes

- Added `tests/fixtures/eval/mixed_knowledge.jsonl` for real-manual and software-doc queries under one `mixed_knowledge` KB.
- Added `scripts/diag_mixed_domain_eval.py` with `--stage-from-defaults` to build the mixed temporary corpus and run the standard eval runner.
- Excluded `mixed_knowledge.jsonl` from fixture-only baseline/CI runs because it depends on materialized external docs.
- Documented the diagnostic in README and `.trellis/spec/backend/architecture.md`.

### Git Commits

| Hash | Message |
|------|---------|
| `bb0feba` | test(rag): add mixed-domain robustness diagnostic |
| `7b92859` | chore(task): archive 05-23-mixed-domain-rag-robustness |

### Testing

- [OK] `.venv/bin/python -m pytest tests/unit/test_diag_mixed_domain_eval.py tests/unit/test_run_eval_ci.py tests/unit/test_diag_general_web_answer_eval.py tests/unit/test_realmanuals_fixture.py tests/unit/test_cli.py::test_cli_pilot_run_passes_baseline_flags -q`
- [OK] `.venv/bin/python scripts/diag_mixed_domain_eval.py --stage-from-defaults --suite tests/fixtures/eval/mixed_knowledge.jsonl --config examples/config/local-hashing-npz.yaml --kb mixed_knowledge --top-k 5 --output .tmp/eval/mixed-domain-report.json`
- [OK] `git diff --check`

### Status

[OK] **Completed**

### Next Steps

- Improve intra-document ranking for long public web pages: mixed-domain validation passed with no cross-domain pollution, but GitHub/Python exact evidence ranked at positions 2-3 rather than always top-1.


## Session 89: Long-document chunk ranking

**Date**: 2026-05-24
**Task**: Improve long-document chunk ranking
**Branch**: `codex/agent-loop-driver`

### Summary

Improved same-document ranking for long public web docs by adding a small bounded body-only proximity bonus for adjacent/near-adjacent ordinary query terms. This lifts evidence-bearing prose such as `standard library` and `source or binary` above repeated page-title/navigation chunks without giving metadata/title fields the same evidence weight.

### Main Changes

- Added body-only ordinary-term proximity scoring in `src/tagmemorag/lexical_search.py`.
- Added focused lexical regression tests for long web documentation chunks.
- Recorded the body-only proximity rule in `.trellis/spec/backend/architecture.md`.

### Git Commits

| Hash | Message |
|------|---------|
| `e6ef726` | fix(rag): boost long-document body phrase matches |
| `926cd46` | chore(task): archive 05-24-long-document-chunk-ranking |

### Testing

- [OK] `.venv/bin/python -m pytest tests/unit/test_lexical_search.py tests/unit/test_diag_mixed_domain_eval.py tests/unit/test_diag_general_web_answer_eval.py tests/unit/test_realmanuals_fixture.py -q`
- [OK] `.venv/bin/python scripts/diag_mixed_domain_eval.py --stage-from-defaults --suite tests/fixtures/eval/mixed_knowledge.jsonl --config examples/config/local-hashing-npz.yaml --kb mixed_knowledge --top-k 5 --output .tmp/eval/long-doc-final.json`
- [OK] `.venv/bin/python scripts/diag_general_web_answer_eval.py --docs .tmp/general-web-eval/general_web --suite tests/fixtures/eval/general_web.jsonl --config examples/config/local-hashing-npz.yaml --kb general_web --output .tmp/eval/general-web-answer-long-doc.json`
- [OK] `.venv/bin/python -m tagmemorag eval run --suite tests/fixtures/eval/realmanuals.jsonl --docs product_manuals --config examples/config/local-hashing-npz.yaml --kb realmanuals --top-k 5 --min-recall-at-k 0.0 --min-mrr 0.0 --min-hit-at-k 0.0 --output .tmp/eval/realmanuals-long-doc.json`
- [OK] `git diff --check`

### Status

[OK] **Completed**

### Next Steps

- Revisit multi-evidence query evaluation: the GitHub README case still ranks README evidence above repository/folder evidence, which may be acceptable for answer quality but is stricter than the current single expected chunk.


## Session 90: Multi-evidence mixed-domain fixture

**Date**: 2026-05-24
**Task**: Represent multi-evidence eval cases
**Branch**: `codex/agent-loop-driver`

### Summary

Aligned the mixed-domain GitHub fixture with the existing general-web multi-evidence semantics. The query asks about repository, README, Markdown, project, and folder concepts, so both the repository/folder definition and README/Markdown explanation are now marked relevant. No retrieval algorithm changes were made.

### Main Changes

- Added README/Markdown as a second relevant evidence entry for `mixed-docs-github-readme`.
- Added a fixture regression test so the mixed GitHub case keeps multi-evidence support.
- Documented multi-evidence eval authoring in the backend architecture spec.

### Git Commits

| Hash | Message |
|------|---------|
| `b19cc81` | test(rag): model mixed-domain multi-evidence case |
| `a545520` | chore(task): archive 05-24-multi-evidence-eval-cases |

### Testing

- [OK] `.venv/bin/python -m pytest tests/unit/test_mixed_knowledge_fixture.py tests/unit/test_diag_mixed_domain_eval.py tests/unit/test_eval_dataset.py tests/unit/test_diag_general_web_answer_eval.py -q`
- [OK] `.venv/bin/python scripts/diag_mixed_domain_eval.py --stage-from-defaults --suite tests/fixtures/eval/mixed_knowledge.jsonl --config examples/config/local-hashing-npz.yaml --kb mixed_knowledge --top-k 5 --output .tmp/eval/multi-evidence-final.json`
- [OK] `.venv/bin/python scripts/diag_general_web_answer_eval.py --docs .tmp/general-web-eval/general_web --suite tests/fixtures/eval/general_web.jsonl --config examples/config/local-hashing-npz.yaml --kb general_web --output .tmp/eval/multi-evidence-general-web-answer.json`
- [OK] `git diff --check`

### Status

[OK] **Completed**

### Next Steps

- Continue answer-quality work by checking whether retrieval context packing prefers complementary evidence over duplicate chunks for multi-evidence questions.


## Session 91: Complementary context evidence

**Date**: 2026-05-24
**Task**: Prefer complementary context evidence
**Branch**: `codex/agent-loop-driver`

### Summary

Improved answer context packing so tight budgets do not get consumed by near-duplicate adjacent chunks before shorter complementary evidence can be included. Retrieval results, evidence ids, and citation ids remain in original retrieval order; only `context_pack.items` selection now prefers lower-overlap fitting evidence after the first selected item.

### Main Changes

- Added deterministic complementary evidence selection in `src/tagmemorag/retrieval.py`.
- Added a regression test where the context pack chooses repository evidence plus README evidence instead of two near-duplicate repository chunks.
- Documented context pack diversity in `.trellis/spec/backend/architecture.md`.

### Git Commits

| Hash | Message |
|------|---------|
| `bc8adf1` | fix(rag): prefer complementary context evidence |
| `8406bf6` | chore(task): archive 05-24-complementary-context-evidence |

### Testing

- [OK] `.venv/bin/python -m pytest tests/unit/test_retrieval.py tests/unit/test_answer_generator.py tests/unit/test_answer_prompt.py tests/unit/test_answer_api.py tests/unit/test_diag_mixed_domain_eval.py tests/unit/test_diag_general_web_answer_eval.py -q`
- [OK] `.venv/bin/python scripts/diag_general_web_answer_eval.py --docs .tmp/general-web-eval/general_web --suite tests/fixtures/eval/general_web.jsonl --config examples/config/local-hashing-npz.yaml --kb general_web --output .tmp/eval/context-pack-general-web-answer.json`
- [OK] `.venv/bin/python scripts/diag_mixed_domain_eval.py --stage-from-defaults --suite tests/fixtures/eval/mixed_knowledge.jsonl --config examples/config/local-hashing-npz.yaml --kb mixed_knowledge --top-k 5 --output .tmp/eval/context-pack-mixed.json`
- [OK] `.venv/bin/python -m tagmemorag eval run --suite tests/fixtures/eval/realmanuals.jsonl --docs product_manuals --config examples/config/local-hashing-npz.yaml --kb realmanuals --top-k 5 --min-recall-at-k 0.0 --min-mrr 0.0 --min-hit-at-k 0.0 --output .tmp/eval/context-pack-realmanuals.json`
- [OK] `git diff --check`

### Status

[OK] **Completed**

### Next Steps

- Add a live answer-quality case that forces a tight context budget and verifies the generated answer cites complementary evidence points.


## Session 93: Real benchmark retrieval gaps

**Date**: 2026-05-24
**Task**: Find real benchmark retrieval gaps
**Branch**: `codex/agent-loop-driver`

### Summary

Ran the real public-web, multi-format, mixed-domain, and product-manual retrieval slices to identify the next genuine quality issue. The only top-k miss was the MDN HTTP caching case, caused by public-web HTML import carrying page chrome/navigation noise into indexed Markdown. Tightened HTML extraction to skip structural chrome and prefer `<main>` content when available.

### Main Changes

- Updated `public_web_import` to skip `nav`, `header`, `footer`, and `aside` alongside existing script/style/media-only exclusions.
- Added `<main>`-first extraction with fallback to all visible blocks for pages without semantic main content.
- Added unit coverage for chrome exclusion and fallback behavior.
- Recorded the diagnostic summary and the public-web import rule in Trellis docs.

### Git Commits

(Pending)

### Testing

- [OK] `.venv/bin/pytest tests/unit/test_public_web_import.py tests/unit/test_cli_source_import.py tests/unit/test_cli.py -q`
- [OK] `scripts/seed_general_web_eval.sh`
- [OK] `.venv/bin/python -m tagmemorag eval run --suite tests/fixtures/eval/general_web.jsonl --docs .tmp/general-web-eval/general_web --config examples/config/local-hashing-npz.yaml --kb general_web --top-k 8 --min-recall-at-k 0.0 --min-mrr 0.0 --min-hit-at-k 0.0 --output .tmp/eval/gap-general-web-after-main.json`
- [OK] `.venv/bin/python scripts/diag_general_web_answer_eval.py --docs .tmp/general-web-eval/general_web --suite tests/fixtures/eval/general_web.jsonl --config examples/config/local-hashing-npz.yaml --kb general_web --top-k 8 --output .tmp/eval/gap-general-web-answer-after-main.json`
- [OK] `.venv/bin/python scripts/seed_multiformat_real_knowledge.py --output-dir .tmp/multiformat-real-knowledge --kb multiformat_real`
- [OK] `.venv/bin/python -m tagmemorag eval run --suite tests/fixtures/eval/multiformat_real_knowledge.jsonl --docs .tmp/multiformat-real-knowledge/multiformat_real --config examples/config/local-hashing-npz.yaml --kb multiformat_real --top-k 8 --min-recall-at-k 0.0 --min-mrr 0.0 --min-hit-at-k 0.0 --output .tmp/eval/gap-multiformat-after-html-clean.json`
- [OK] `.venv/bin/python scripts/diag_multiformat_answer_eval.py --docs .tmp/multiformat-real-knowledge/multiformat_real --suite tests/fixtures/eval/multiformat_real_knowledge.jsonl --config examples/config/local-hashing-npz.yaml --kb multiformat_real --top-k 8 --output .tmp/eval/gap-multiformat-answer-after-html-clean.json`
- [OK] `.venv/bin/python scripts/diag_mixed_domain_eval.py --stage-from-defaults --suite tests/fixtures/eval/mixed_knowledge.jsonl --config examples/config/local-hashing-npz.yaml --kb mixed_knowledge --top-k 5 --output .tmp/eval/gap-mixed-domain-after-html-clean.json`
- [OK] `.venv/bin/python -m tagmemorag eval run --suite tests/fixtures/eval/realmanuals.jsonl --docs product_manuals --config examples/config/local-hashing-npz.yaml --kb realmanuals --top-k 5 --min-recall-at-k 0.0 --min-mrr 0.0 --min-hit-at-k 0.0 --output .tmp/eval/gap-realmanuals-after-html-clean.json`

### Status

[OK] **Completed**

### Next Steps

- Treat remaining general-web low-MRR cases as a ranking/reranking problem for complementary multi-evidence answers, not an HTML-import problem.


## Session 92: Complementary answer quality

**Date**: 2026-05-24
**Task**: Validate complementary evidence answers
**Branch**: `codex/agent-loop-driver`

### Summary

Extended the complementary evidence work from context selection into final answer quality. The local noop answer path now prefers selected context items before falling back to full evidence, normalizes simple English plurals for relevance matching, and has a tight-budget regression proving the generated answer cites both repository/folder and README/Markdown evidence.

### Main Changes

- Tightened `NoopAnswerGenerator` so answer citations come from `context_pack.items` when selected context exists, keeping generated answers aligned with prompt context and answer-quality diagnostics.
- Added simple plural normalization to English relevance terms so public documentation wording like `file`/`files` does not drop relevant evidence.
- Added an answer-quality regression that exercises `build_retrieve_response`, prompt citation validation, noop answer generation, and `evaluate_answer_quality_case` together under a tight token budget.

### Git Commits

| Hash | Message |
|------|---------|
| `12145b5` | chore(task): archive 05-24-complementary-evidence-answer-quality |
| `3d63242` | test(rag): validate complementary evidence answers |

### Testing

- [OK] `.venv/bin/python -m pytest tests/unit/test_answer_generator.py tests/unit/test_retrieval.py tests/unit/test_answer_quality_eval.py tests/unit/test_diag_general_web_answer_eval.py -q`
- [OK] `.venv/bin/python scripts/diag_general_web_answer_eval.py --docs .tmp/general-web-eval/general_web --suite tests/fixtures/eval/general_web.jsonl --config examples/config/local-hashing-npz.yaml --kb general_web --output .tmp/eval/complementary-answer-quality-general-web.json`
- [OK] `.venv/bin/python scripts/diag_mixed_domain_eval.py --stage-from-defaults --suite tests/fixtures/eval/mixed_knowledge.jsonl --config examples/config/local-hashing-npz.yaml --kb mixed_knowledge --top-k 5 --output .tmp/eval/complementary-answer-quality-mixed.json`
- [OK] `git diff --check`

### Status

[OK] **Completed**

### Next Steps

- Move back to the main RAG quality track with answer synthesis/reranking improvements that can help arbitrary knowledge bases, not just product manuals.


## Session 93: Real web knowledge benchmark

**Date**: 2026-05-24
**Task**: Real web knowledge eval benchmark
**Branch**: `codex/agent-loop-driver`

### Summary

Expanded the opt-in general-web benchmark from two software documentation pages into a broader real-public-document slice. The seed script now materializes Python, GitHub, MDN HTTP caching, USAGov passport, and IRS Free File pages into `.tmp`; committed fixtures store only URLs and expected evidence strings, not fetched third-party content.

### Main Changes

- Added MDN, USAGov, and IRS source groups to `scripts/seed_general_web_eval.sh` with distinct `domain` and `doc_type` metadata.
- Added real-web retrieval cases for HTTP caching directives, lost/stolen passport guidance, and IRS Free File AGI/guided-tax information.
- Added a no-network unit test to keep the seed script covering multiple real domains.
- Documented the expanded real-web eval slice in README and `.trellis/spec/backend/architecture.md`.

### Git Commits

| Hash | Message |
|------|---------|
| `db67363` | chore(task): archive 05-24-real-web-knowledge-eval |
| `f53ae5c` | test(rag): expand real web knowledge benchmark |

### Testing

- [OK] `scripts/seed_general_web_eval.sh`
- [OK] `.venv/bin/python -m tagmemorag eval run --suite tests/fixtures/eval/general_web.jsonl --docs .tmp/general-web-eval/general_web --config examples/config/local-hashing-npz.yaml --kb general_web --top-k 8 --min-recall-at-k 0.0 --min-mrr 0.0 --min-hit-at-k 0.0 --output .tmp/eval/real-web-knowledge-eval.json` (`cases=7`, `hit@k=0.857143`, `mrr=0.528571`)
- [OK] `.venv/bin/python scripts/diag_general_web_answer_eval.py --docs .tmp/general-web-eval/general_web --suite tests/fixtures/eval/general_web.jsonl --config examples/config/local-hashing-npz.yaml --kb general_web --top-k 8 --output .tmp/eval/real-web-knowledge-answer.json` (`cases=7 failed=0`)
- [OK] `.venv/bin/python scripts/diag_mixed_domain_eval.py --stage-from-defaults --suite tests/fixtures/eval/mixed_knowledge.jsonl --config examples/config/local-hashing-npz.yaml --kb mixed_knowledge --top-k 5 --output .tmp/eval/real-web-knowledge-mixed.json`
- [OK] `.venv/bin/python -m pytest tests/unit/test_general_web_seed_script.py tests/unit/test_public_web_import.py tests/unit/test_diag_general_web_answer_eval.py tests/unit/test_diag_mixed_domain_eval.py tests/unit/test_run_eval_ci.py -q`
- [OK] `git diff --check`

### Status

[OK] **Completed**

### Next Steps

- Use the expanded real-web benchmark before future retrieval or answer-synthesis tuning, and consider adding more document types only when they are stable enough to fetch reproducibly.


## Session 94: Multi-format real knowledge benchmark

**Date**: 2026-05-24
**Task**: Multi-format real knowledge benchmark
**Branch**: `codex/agent-loop-driver`

### Summary

Added an opt-in benchmark lane for real online knowledge documents across HTML, PDF, and DOCX-style sources. HTML still uses the existing public-web importer, PDF is downloaded and indexed by the native text-PDF parser, and DOCX is safely converted from OpenXML text into Markdown before indexing. Fetched third-party content remains under `.tmp`; committed files contain only source URLs, metadata contracts, scripts, and eval expectations.

### Main Changes

- Added `scripts/seed_multiformat_real_knowledge.py` to materialize MDN HTML, IRS PDF, and EPA DOCX sources into a shared local corpus.
- Added `scripts/diag_multiformat_answer_eval.py` and `tests/fixtures/eval/multiformat_real_knowledge.jsonl`.
- Preserved `source_format` metadata through manual/document metadata so eval can verify format lineage.
- Added no-network unit tests for DOCX extraction and multi-format materialization.
- Documented the multi-format real-knowledge slice in README and `.trellis/spec/backend/architecture.md`.

### Git Commits

| Hash | Message |
|------|---------|
| `9cd42ee` | chore(task): archive 05-24-multiformat-real-knowledge-benchmark |
| `bb2296f` | test(rag): add multi-format real knowledge benchmark |

### Testing

- [OK] `.venv/bin/python -m pytest tests/unit/test_multiformat_real_knowledge.py tests/unit/test_manual_metadata.py tests/unit/test_document_metadata.py tests/unit/test_run_eval_ci.py -q`
- [OK] `.venv/bin/python scripts/seed_multiformat_real_knowledge.py --output-dir .tmp/multiformat-real-knowledge --kb multiformat_real`
- [OK] `.venv/bin/python -m tagmemorag eval run --suite tests/fixtures/eval/multiformat_real_knowledge.jsonl --docs .tmp/multiformat-real-knowledge/multiformat_real --config examples/config/local-hashing-npz.yaml --kb multiformat_real --top-k 8 --min-recall-at-k 0.0 --min-mrr 0.0 --min-hit-at-k 0.0 --output .tmp/eval/multiformat-real-knowledge.json` (`cases=3`, `hit@k=0.666667`, `mrr=0.444444`)
- [OK] `.venv/bin/python scripts/diag_multiformat_answer_eval.py --docs .tmp/multiformat-real-knowledge/multiformat_real --suite tests/fixtures/eval/multiformat_real_knowledge.jsonl --config examples/config/local-hashing-npz.yaml --kb multiformat_real --top-k 8 --output .tmp/eval/multiformat-real-answer.json` (`cases=3 failed=0`)
- [OK] `git diff --check`

### Status

[OK] **Completed**

### Next Steps

- Use the multi-format benchmark to drive the next optimization pass. The first obvious pressure point is improving recall/ranking on long real PDF/DOCX-derived documents without overfitting one fixture.


## Session 95: Multi-format eval chunk alignment

**Date**: 2026-05-24
**Task**: Improve multiformat long document ranking
**Branch**: `codex/agent-loop-driver`

### Summary

Investigated the weak first-pass multi-format retrieval metrics. The DOCX case was returning the right EPA waiver chunks near the top, but the eval expectation combined phrases from adjacent chunks into one relevant item, producing a false negative. The suite now models the DOCX question as three chunk-aligned complementary evidence points.

### Main Changes

- Split the EPA DOCX waiver-certification expectation into chunk-level relevant entries for waiver certification, Section 508/plain-language certification, and HTTPS/OMB certification evidence.
- Documented the rule that long-document eval expectations must not combine adjacent chunks into one expected result.

### Git Commits

| Hash | Message |
|------|---------|
| `abf49c7` | chore(task): archive 05-24-improve-multiformat-long-doc-ranking |
| `dac4b5b` | test(rag): align multiformat eval with chunk evidence |

### Testing

- [OK] `.venv/bin/python -m tagmemorag eval run --suite tests/fixtures/eval/multiformat_real_knowledge.jsonl --docs .tmp/multiformat-real-knowledge/multiformat_real --config examples/config/local-hashing-npz.yaml --kb multiformat_real --top-k 8 --min-recall-at-k 0.0 --min-mrr 0.0 --min-hit-at-k 0.0 --output .tmp/eval/multiformat-real-knowledge-corrected.json` (`hit@k=1.0`, `recall@k=1.0`, `mrr=0.611111`)
- [OK] `.venv/bin/python scripts/diag_multiformat_answer_eval.py --docs .tmp/multiformat-real-knowledge/multiformat_real --suite tests/fixtures/eval/multiformat_real_knowledge.jsonl --config examples/config/local-hashing-npz.yaml --kb multiformat_real --top-k 8 --output .tmp/eval/multiformat-real-answer-corrected.json`
- [OK] `.venv/bin/python -m pytest tests/unit/test_multiformat_real_knowledge.py tests/unit/test_run_eval_ci.py -q`
- [OK] `git diff --check`

### Status

[OK] **Completed**

### Next Steps

- Continue with genuine ranking improvements only after corrected real-document evals expose actual retrieval misses, not fixture-boundary artifacts.


## Session 54: QA demo seed smoke

**Date**: 2026-05-22
**Task**: QA demo seed smoke
**Branch**: `codex/agent-loop-driver`

### Summary

Added an offline QA demo path using the coffee fixture, qa-demo config, and seed script. Verified build, config validation, /qa/answer answered route, citations, evidence, and focused tests.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `0c0ebfd` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 55: Extractive noop demo answers

**Date**: 2026-05-22
**Task**: Extractive noop demo answers
**Branch**: `codex/agent-loop-driver`

### Summary

Made the local noop answer provider return deterministic evidence-backed excerpts with citations, updated docs/specs, and verified the seeded QA demo endpoint.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `16a544f` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 56: Multi evidence extractive answers

**Date**: 2026-05-22
**Task**: Multi evidence extractive answers
**Branch**: `codex/agent-loop-driver`

### Summary

Improved the offline noop answer provider to synthesize a bounded set of relevant evidence excerpts with valid citations, with focused tests and seeded QA smoke verification.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `34fd658` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 57: Clickable QA citations

**Date**: 2026-05-22
**Task**: Clickable QA citations
**Branch**: `codex/agent-loop-driver`

### Summary

Turned inline QA citations into clickable chips that focus and highlight matching source cards, with focused UI/API tests and browser smoke verification.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `a07b788` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 58: Stepwise QA answer UX

**Date**: 2026-05-22
**Task**: Stepwise QA answer UX
**Branch**: `codex/agent-loop-driver`

### Summary

Formatted offline QA answers as a recommendation plus numbered steps, rendered numbered lines as lists while preserving citation chips, and verified focused tests plus demo endpoint output.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `033844c` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 59: QA quick starts and copy

**Date**: 2026-05-22
**Task**: QA quick starts and copy
**Branch**: `codex/agent-loop-driver`

### Summary

Added suggested starter questions and a copy-answer action to the user QA page, with focused UI/API tests and browser smoke verification for the suggestion flow.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `2047ecd` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 60: QA answer polish UX

**Date**: 2026-05-22
**Task**: QA answer polish UX
**Branch**: `codex/agent-loop-driver`

### Summary

Polished /qa answer UX with staged loading, local feedback, follow-up suggestions, expandable source snippets, richer empty state, focused tests, and browser smoke verification.

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


## Session 61: QA local conversation UX

**Date**: 2026-05-22
**Task**: QA local conversation UX
**Branch**: `codex/agent-loop-driver`

### Summary

Added local /qa conversation history with pending/answered/error turn tracking, click-to-restore answers and sources, clear history, race-safe active turn rendering, focused tests, and browser smoke verification.

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


## Session 62: QA follow-up context

**Date**: 2026-05-22
**Task**: QA follow-up context
**Branch**: `codex/agent-loop-driver`

### Summary

Extended /qa/answer with bounded page-session conversation context, frontend follow-up context sending, context-aware routing/retrieval for ambiguous follow-ups, original-question response preservation, focused tests, and browser smoke verification.

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


## Session 63: QA session memory

**Date**: 2026-05-22
**Task**: QA session memory
**Branch**: `codex/agent-loop-driver`

### Summary

Upgraded /qa short-term memory to sanitized sessionStorage-backed tab-session recovery, preserving recent answered turns, sources, follow-ups, feedback state, and clear-history behavior without backend persistence or debug identifiers.

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


## Session 64: QA context transparency

**Date**: 2026-05-22
**Task**: QA context transparency
**Branch**: `codex/agent-loop-driver`

### Summary

Added /qa follow-up context explainability and correction: API context metadata, user-facing context notice, history context marker, Ask as new override, focused tests, spec update, and browser smoke verification after server restart.

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


## Session 65: QA answer quality eval

**Date**: 2026-05-22
**Task**: QA answer quality eval
**Branch**: `codex/agent-loop-driver`

### Summary

Added the first fixed /qa product-manual answer-quality slice, extended deterministic answer-quality diagnostics with CJK n-gram matching for Chinese relevance/support checks, covered the new suite in unit and CLI tests, and documented the eval command in architecture.

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


## Session 66: QA answer generator quality

**Date**: 2026-05-22
**Task**: QA answer generator quality
**Branch**: `codex/agent-loop-driver`

### Summary

Improved deterministic noop answer generation for product manuals with stepwise troubleshooting, safety-prioritized answers, unsupported repair/part-number refusal framing, stricter relevance filtering, focused tests, answer-quality diagnostics, and real PDF manual validation.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `3c0723b` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 67: Real manual retrieval quality

**Date**: 2026-05-22
**Task**: Real manual retrieval quality
**Branch**: `codex/agent-loop-driver`

### Summary

Improved real PDF manual retrieval by adding CJK bi/tri-gram lexical matching with generic term filtering and multi-term lexical scoring; realmanuals hit@5 improved from 0.4 to 0.8, recall@5 from 0.283333 to 0.633333, mrr from 0.233333 to 0.516667.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `3066b98` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 68: Manual evidence ranking quality

**Date**: 2026-05-22
**Task**: Manual evidence ranking quality
**Branch**: `codex/agent-loop-driver`

### Summary

Improved real manual evidence ranking by separating lexical identity fields from topic fields and rewarding specific multi-term heading/body matches; realmanuals improved from hit@5=0.8, recall@5=0.633333, mrr=0.516667 to hit@5=1.0, recall@5=0.966667, mrr=0.691667. Answer-quality diagnostics and focused retrieval/answer tests passed.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `7d67050` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 69: Manualslib real manual validation

**Date**: 2026-05-22
**Task**: Manualslib real manual validation
**Branch**: `codex/agent-loop-driver`

### Summary

Added explicit ManualsLib URL import tooling that materializes browser-visible manual text into markdown plus metadata sidecars, validated against a real Hisense DH105M3 Series sample from ManualsLib. The sample built as a hashing KB with 122 chunks and exposed a future ranking target around generic drying terms vs program/cycle-selector intent. Focused tests, answer-quality diagnostics, and realmanuals retrieval regression gates passed.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `71dbed4` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 70: ManualsLib OpenCLI batch import

**Date**: 2026-05-22
**Task**: ManualsLib OpenCLI batch import
**Branch**: `codex/agent-loop-driver`

### Summary

Added a manualslib import-opencli command that uses the local OpenCLI adapter to preview and batch-import selected ManualsLib URLs through the existing explicit URL importer. Verified focused unit tests, compileall, OpenCLI preview, and a one-page real smoke import.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `22380f3` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 71: ManualsLib real sample quality slice

**Date**: 2026-05-22
**Task**: ManualsLib real sample quality slice
**Branch**: `codex/agent-loop-driver`

### Summary

Imported a runtime-only ManualsLib sample across Dryer, Washer, Refrigerator, and TV using the OpenCLI bridge, built a hashing KB with 239 chunks, created a .tmp retrieval eval slice, and validated recall@5=1.0/mrr=0.833333/hit@5=1.0. Regression gates for realmanuals and QA answer quality passed; noted that eval text_contains is sensitive to OCR line breaks.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `c2b5da7` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 72: General RAG robustness direction

**Date**: 2026-05-22
**Task**: General RAG robustness direction
**Branch**: `codex/agent-loop-driver`

### Summary

Started the general-knowledge RAG robustness track, documented candidate public knowledge-source families, and hardened eval text_contains matching against whitespace/control-character extraction noise. Verified focused eval tests and the real product-manual retrieval gate.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `109d771` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 73: Public web knowledge sampler

**Date**: 2026-05-22
**Task**: Public web knowledge sampler
**Branch**: `codex/agent-loop-driver`

### Summary

Added a general knowledge sample-web CLI that fetches public HTML pages into Markdown plus sidecar metadata, preserved remote/domain/doc_type metadata through connector materialization, documented usage, and validated with Python/GitHub docs preview plus a Python docs build/search smoke.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `f98dcef` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 74: Generic document metadata

**Date**: 2026-05-22
**Task**: Generic document metadata
**Branch**: `codex/agent-loop-driver`

### Summary

Made sidecar-declared generic domain/doc_type metadata survive build/search, preserved remote_id/url attributes for public web samples, and verified both public web and real product-manual paths remain green.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `e95a188` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 75: General web eval suite

**Date**: 2026-05-22
**Task**: General web eval suite
**Branch**: `codex/agent-loop-driver`

### Summary

Added a reproducible public web documentation benchmark for the general RAG direction. The suite seeds Python and GitHub docs into .tmp, checks generic software_docs/documentation metadata, excludes the live-corpus suite from fixture-only CI/baseline generation, and documents the hashing baseline plus its current GitHub repository miss as a future retrieval-quality target.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `7a1d37f` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 76: General web multi-evidence eval

**Date**: 2026-05-22
**Task**: General web multi-evidence eval
**Branch**: `codex/agent-loop-driver`

### Summary

Corrected the general web GitHub repository eval case to model two independently retrieved evidence chunks instead of requiring both snippets in one chunk. Re-ran the live-seeded public web suite with stricter recall/hit thresholds at 1.0 and documented the multi-evidence behavior in README.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `27a4b8e` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 77: Aggregate generic multi-evidence answers

**Date**: 2026-05-23
**Task**: Aggregate generic multi-evidence answers
**Branch**: `codex/agent-loop-driver`

### Summary

Improved the local extractive answer baseline so generic documentation questions with multiple supporting chunks use a neutral multi-evidence answer prefix and cite each item. The fallback path now keeps up to MAX_EXTRACTIVE_EXCERPTS allowed excerpts instead of only the first excerpt, while preserving safety and unsupported-repair behavior.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `7953eb3` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 78: General web answer quality suite

**Date**: 2026-05-23
**Task**: General web answer quality suite
**Branch**: `codex/agent-loop-driver`

### Summary

Added a checked-in answer-quality suite for generic public documentation answers covering multi-evidence GitHub docs, Python tutorial grounding, and an unsupported GitHub security claim. Wired the suite into unit and CLI coverage and documented the command next to the general web retrieval benchmark.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `20b38e6` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 79: Live general web answer diagnostic

**Date**: 2026-05-23
**Task**: Live general web answer diagnostic
**Branch**: `codex/agent-loop-driver`

### Summary

Added scripts/diag_general_web_answer_eval.py to bridge live general_web retrieval with the local noop answer generator and answer-quality diagnostics. The script builds the seeded corpus in isolated eval storage, generates grounded/cited answers from retrieved context, emits a concise JSON report, and is covered by a local no-network unit test plus README usage docs.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `239c3ea` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 80: Answer intent classification

**Date**: 2026-05-23
**Task**: Answer intent classification
**Branch**: `codex/agent-loop-driver`

### Summary

Moved deterministic answer intent rules into the answer layer, preserved product troubleshooting and safety wording, kept generic software documentation answers neutral, and recorded the no-API/CLI-growth convention.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `219253d` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 81: API CLI entrypoint slimming

**Date**: 2026-05-23
**Task**: API CLI entrypoint slimming
**Branch**: `codex/agent-loop-driver`

### Summary

Extracted QA context formatting from api.py and reusable argparse/file helpers from cli.py into focused modules, added tests, and documented the new module boundaries.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `8a50ac2` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 82: CLI feedback command extraction

**Date**: 2026-05-23
**Task**: CLI feedback command extraction
**Branch**: `codex/agent-loop-driver`

### Summary

Moved feedback CLI command execution out of cli.py into cli_feedback.py, added direct command-module tests, and kept the existing feedback workflow behavior unchanged.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `b0225c3` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 83: CLI source import command extraction

**Date**: 2026-05-23
**Task**: CLI source import command extraction
**Branch**: `codex/agent-loop-driver`

### Summary

Moved ManualsLib and public-web source import CLI execution out of cli.py into cli_source_import.py, added direct failure-path tests, and kept existing CLI behavior covered.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `c2e5575` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 84: CLI provider command extraction

**Date**: 2026-05-23
**Task**: CLI provider command extraction
**Branch**: `codex/agent-loop-driver`

### Summary

Moved provider probe and production-provider smoke/verify command execution out of cli.py into cli_provider.py, added direct command-module tests, and kept existing CLI behavior covered.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `085d059` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 85: Complete CLI entrypoint split

**Date**: 2026-05-23
**Task**: Complete CLI entrypoint split
**Branch**: `codex/agent-loop-driver`

### Summary

Finished the CLI slimming pass by reducing cli.py to a thin parser/dispatch wrapper, moving parser construction to cli_parser.py, command routing to cli_dispatch.py, and remaining command execution into cli_basic.py, cli_eval.py, and cli_manual.py. CLI-focused tests passed.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `b801c2d` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 86: Slim API entrypoint

**Date**: 2026-05-23
**Task**: Slim API entrypoint
**Branch**: `codex/agent-loop-driver`

### Summary

Reduced api.py by extracting Pydantic request models into api_models.py, QA routing helpers into api_qa.py, and manual-library parsing/rebuild/diagnostics helpers into api_manual.py. Preserved tagmemorag.api imports and verified API-focused tests.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `da9f6a4` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 87: Complete API entrypoint split

**Date**: 2026-05-23
**Task**: Complete API entrypoint split
**Branch**: `codex/agent-loop-driver`

### Summary

Finished API slimming by reducing api.py to FastAPI wiring plus compatibility wrappers. Extracted search/retrieve/answer execution into api_search.py, feedback execution into api_feedback.py, admin/cache/generation helpers into api_admin.py, and manual route execution into api_manual_routes.py. API-focused tests passed.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `3a8582a` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 88: Long-horizon RAG quality batch

**Date**: 2026-05-24
**Task**: Long-horizon RAG quality program
**Branch**: `codex/agent-loop-driver`

### Summary

Ran a longer real-data quality batch across public web, multi-format, mixed-domain, real product manuals, and answer-quality diagnostics. Rejected parser-level PDF heading merging after it regressed real-manual retrieval, then kept a safer retrieval-context enhancement that expands sparse PDF heading-only evidence with adjacent same-page body text for answer generation.

### Main Changes

- Added context-pack expansion for sparse PDF heading-only retrieval results.
- Added unit coverage for adjacent body expansion on a real Hisense Steam Clean style scenario.
- Recorded baseline/regression/final matrix in `.trellis/tasks/05-24-long-horizon-rag-quality/quality-program-notes.md`.

### Testing

- [OK] `.venv/bin/pytest tests/unit/test_retrieval.py tests/unit/test_parser.py tests/unit/test_answer_generator.py -q`
- [OK] realmanuals retrieval: 10 cases, hit@k=1.0, recall@k=0.966667, MRR=0.708333
- [OK] mixed-domain retrieval: 4 cases, hit@k=1.0, MRR=1.0
- [OK] general-web retrieval and answer diagnostics
- [OK] multi-format retrieval and answer diagnostics
- [OK] product-manual QA answer quality

### Status

[OK] **Implementation and verification complete**

### Next Steps

- Consider a ranking-layer evidence usefulness score to demote table-of-contents and other low-answerability chunks while preserving useful adjacent context.


## Session 89: Public-web lexical evidence tie-break

**Date**: 2026-05-24
**Task**: Long-horizon RAG quality program
**Branch**: `codex/agent-loop-driver`

### Summary

Continued the long-horizon RAG quality task after the sparse-heading context batch. Diagnosed public-web low-MRR cases and found repeated title/identity fields saturating lexical scores. Added lightweight English plural normalization plus a bounded body-only evidence tie-break to improve public-web ordering without disturbing product manuals or mixed-domain retrieval.

### Main Changes

- Normalized simple English plural ordinary terms in lexical matching.
- Added a tiny post-cap body evidence tie-break based on body term hits and compact evidence windows.
- Added unit coverage for plural normalization on GitHub repository/README style evidence.

### Testing

- [OK] `.venv/bin/pytest tests/unit/test_lexical_search.py tests/unit/test_search_runtime_phase1.py tests/unit/test_retrieval.py -q`
- [OK] general-web retrieval: 7 cases, hit@k=1.0, recall@k=0.928571, MRR=0.579932
- [OK] realmanuals retrieval: 10 cases, hit@k=1.0, recall@k=0.966667, MRR=0.708333
- [OK] multi-format retrieval: 3 cases, hit@k=1.0, recall@k=1.0, MRR=0.611111
- [OK] mixed-domain retrieval: 4 cases, hit@k=1.0, MRR=1.0
- [OK] general-web and multi-format answer diagnostics
- [OK] product-manual QA answer quality

### Status

[OK] **Implementation and verification complete**

### Next Steps

- Avoid pushing lexical boosts much further; the next quality step should be a first-class evidence usefulness/reranking signal for definition-style and answer-bearing chunks.


## Session 90: Context usefulness ordering

**Date**: 2026-05-24
**Task**: Long-horizon RAG quality program
**Branch**: `codex/agent-loop-driver`

### Summary

Added query-aware usefulness scoring to context-pack selection. This keeps retrieval ranking stable while improving which evidence reaches answer generation first, especially for public-web cases where useful chunks are present but broad overview/navigation chunks can consume early context slots.

### Main Changes

- Passed `query_text` into context packing.
- Added bounded context usefulness scoring for definition/contains/is-a style evidence.
- Balanced follow-up context selection between answer usefulness and low overlap.
- Added unit coverage for first-slot answer-bearing selection under tight token budget.

### Testing

- [OK] `.venv/bin/pytest tests/unit/test_retrieval.py -q`
- [OK] general-web retrieval: 7 cases, hit@k=1.0, recall@k=0.928571, MRR=0.579932
- [OK] realmanuals retrieval: 10 cases, hit@k=1.0, recall@k=0.966667, MRR=0.708333
- [OK] multi-format retrieval: 3 cases, hit@k=1.0, recall@k=1.0, MRR=0.611111
- [OK] mixed-domain retrieval: 4 cases, hit@k=1.0, MRR=1.0
- [OK] general-web and multi-format answer diagnostics
- [OK] product-manual QA answer quality

### Status

[OK] **Implementation and verification complete**

### Next Steps

- Add a context-quality diagnostic report for weak public-web cases before further heuristic tuning.


## Session 91: Context quality diagnostics

**Date**: 2026-05-24
**Task**: Long-horizon RAG quality program
**Branch**: `codex/agent-loop-driver`

### Summary

Added a real-data context-quality diagnostic so we can inspect whether top-k evidence actually reaches the answer prompt. Used it on general-web and multi-format slices with normal and tight budgets, then added a bounded rank/score prior for high-coverage context evidence to reduce tight-budget misses without changing retrieval ranking.

### Main Changes

- Added `scripts/diag_context_quality.py` and `tagmemorag.eval.context_quality`.
- Added bounded `context_evidence_diagnostics()` output without raw snippets.
- Added a context-selection score prior for high-query-coverage evidence.
- Added unit coverage for diagnostic sanitization and tight-budget high-rank evidence retention.

### Testing

- [OK] `.venv/bin/pytest tests/unit/test_retrieval.py -q`
- [OK] context quality, normal budget: general-web 7/7 selected expected; multi-format 3/3 selected expected
- [OK] context quality, tight budget: general-web 6/7 selected expected; multi-format improved from 1/3 to 2/3
- [OK] general-web answer: 7 cases, failed=0
- [OK] multi-format answer: 3 cases, failed=0
- [OK] mixed-domain retrieval: 4 cases, hit@k=1.0, MRR=1.0
- [OK] realmanuals retrieval: 10 cases, hit@k=1.0, recall@k=0.966667, MRR=0.708333
- [OK] product-manual QA answer quality: 6 cases passed

### Status

[OK] **Implementation and verification complete**

### Next Steps

- Consider budget-aware adjacent evidence joining/compression before further context heuristic tuning.


## Session 92: Budget-aware context compression

**Date**: 2026-05-24
**Task**: Long-horizon RAG quality program
**Branch**: `codex/agent-loop-driver`

### Summary

Added budget-aware context compaction and adjacent same-source evidence merging. The goal was to make release-facing answers see denser evidence without changing retrieval ranking, parser chunking, or API route behavior.

### Main Changes

- Added query-aware sentence compaction for long context items.
- Made context selection estimate tokens after compaction.
- Added same-document/same-page adjacent evidence merging when it fits the remaining context budget.
- Preserved merged evidence lineage via `evidence_refs` and `citation_ids`.
- Added focused unit coverage for sentence compaction and adjacent support merging.

### Testing

- [OK] `.venv/bin/pytest tests/unit/test_retrieval.py tests/unit/test_answer_generator.py tests/unit/test_lexical_search.py tests/unit/test_search_runtime_phase1.py -q`
- [OK] context quality, normal budget: general-web 7/7 selected expected; multi-format 3/3 selected expected
- [OK] context quality, tight budget: general-web improved from 6/7 to 7/7; multi-format stayed 2/3
- [OK] general-web answer: 7 cases, failed=0
- [OK] multi-format answer: 3 cases, failed=0
- [OK] mixed-domain retrieval: 4 cases, hit@k=1.0, MRR=1.0
- [OK] realmanuals retrieval: 10 cases, hit@k=1.0, recall@k=0.966667, MRR=0.708333
- [OK] product-manual QA answer quality: 6 cases passed

### Status

[OK] **Implementation and verification complete**

### Next Steps

- Build a bounded release-readiness report that combines retrieval, context-quality, answer-quality, config, and residual-risk signals.
