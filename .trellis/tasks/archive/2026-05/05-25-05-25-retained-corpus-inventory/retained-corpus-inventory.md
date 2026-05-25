# Retained Corpus Inventory

## Scope

This inventory records committed eval suites, reusable local corpus locations,
retained reports, and monitoring gaps for the post-default-on general RAG
stability program. It intentionally stores only bounded metadata and aggregate
metrics.

## Committed Eval Suites

| Suite | Cases | Current Role |
| --- | ---: | --- |
| `tests/fixtures/eval/general_web.jsonl` | 7 | General public-web retrieval slice. |
| `tests/fixtures/eval/mixed_knowledge.jsonl` | 4 | Mixed manual plus public-web retrieval slice. |
| `tests/fixtures/eval/multiformat_real_knowledge.jsonl` | 3 | HTML/PDF/DOCX real-source retrieval slice. |
| `tests/fixtures/eval/realmanuals.jsonl` | 10 | Real manual retrieval slice. |
| `tests/fixtures/eval/product_manuals.jsonl` | 14 | Product-manual fixture retrieval slice. |
| `tests/fixtures/eval/coffee.jsonl` | 7 | Small baseline product-manual slice. |
| `tests/fixtures/eval/cross_kb_negatives.jsonl` | 5 | Cross-KB negative safety slice. |
| `tests/fixtures/eval/fault_codes.jsonl` | 5 | Fault-code retrieval slice. |
| `tests/fixtures/eval/mixed_language.jsonl` | 5 | Mixed-language product-manual slice. |
| `tests/fixtures/eval/model_numbers.jsonl` | 5 | Model-number precision slice. |
| `tests/fixtures/eval/tag_cooccurrence.jsonl` | 5 | Tag co-occurrence retrieval slice. |
| `tests/fixtures/eval/tag_rerank_edge.jsonl` | 5 | Tag rerank edge-case slice. |
| `tests/fixtures/eval/agentic_*.jsonl` | 12 total | Agentic eval slices; out of scope for this RAG monitoring phase. |

Observation: the core post-default-on slices exist, but the most important
general RAG slices are small: mixed-domain has 4 cases and multiformat has 3.

## Reusable Local Corpus Locations

These are local, non-committed corpus or built-index locations available for
repeatable checks on this machine.

| Location | Files | Notes |
| --- | ---: | --- |
| `.tmp/general-web-eval/general_web` | 10 | Materialized public-web source corpus for `general_web`. |
| `.tmp/real-web-materialized/general_web` | 6 | Smaller materialized public-web source corpus. |
| `.tmp/multiformat-real-knowledge/multiformat_real` | 6 | Materialized HTML/PDF/DOCX real-source corpus. |
| `.tmp/manualslib-quality-slice` | 8 | Manualslib quality sample across several product categories. |
| `.tmp/product-manuals-pdf-only` | 10 | PDF-only product-manual sample. |
| `data/realmanuals` | 5 | Built local realmanuals KB artifacts. |
| `data/default` | 4 | Built default KB artifacts. |

Observation: there are enough local corpora to run monitoring now, but only some
have clean, documented eval commands and retained aggregate reports.

## Key Retained Reports

| Report | Cases | Recall@k | MRR | Hit@k | Status |
| --- | ---: | ---: | ---: | ---: | --- |
| `.tmp/eval/default-on-general-web.json` | 7 | 0.971429 | 1.000000 | 1.000000 | passed |
| `.tmp/eval/same-page-enabled-mixed-domain.json` | 4 | 1.000000 | 1.000000 | 1.000000 | passed |
| `.tmp/eval/same-page-enabled-multiformat-cross-guard.json` | 3 | 1.000000 | 0.777778 | 1.000000 | passed |
| `.tmp/eval/same-page-enabled-realmanuals-cross-guard.json` | 10 | 0.966667 | 0.825000 | 1.000000 | passed |
| `.tmp/eval/general-web-ranking-pressure.json` | 7 | 0.971429 | 0.773810 | 1.000000 | baseline pressure |

Gate outputs:

- `.tmp/eval/default-on-implementation-gate/batch-summary.json`: `passed`
- `.tmp/eval/default-on-implementation-gate/release-readiness.json`: `passed`
- `.tmp/eval/default-on-implementation-gate/reranking-gate.json`: `passed`
- `.tmp/eval/default-on-implementation-gate/candidate-ranking-pressure.json`

Observation: default-on evidence exists for the core slices, but the report set
is manually assembled. There is not yet one monitoring command that reruns all
retained slices and writes a bounded rollup.

## Existing Tooling

Relevant scripts:

- `scripts/reranking_gate_batch.py`
- `scripts/release_readiness.py`
- `scripts/diag_general_web_ranking_pressure.py`
- `scripts/diag_mixed_domain_eval.py`
- `scripts/diag_realmanuals_eval.py`
- `scripts/diag_multiformat_answer_eval.py`
- `scripts/seed_general_web_eval.sh`
- `scripts/seed_multiformat_real_knowledge.py`
- `scripts/run_eval_ci.py`

Relevant unit coverage:

- `tests/unit/test_eval_runner.py`
- `tests/unit/test_reranking_gate_batch.py`
- `tests/unit/test_reranking_eval_gate.py`
- `tests/unit/test_release_readiness.py`
- `tests/unit/test_diag_general_web_ranking_pressure.py`
- `tests/unit/test_diag_mixed_domain_eval.py`
- `tests/unit/test_diag_realmanuals_eval.py`
- `tests/unit/test_multiformat_real_knowledge.py`

Observation: primitives exist, but monitoring still requires knowing which
report paths belong together.

## Coverage Gaps

- Mixed-domain retained retrieval has only 4 committed cases.
- Multiformat retained retrieval has only 3 committed cases.
- General-web retained retrieval has only 7 committed cases and is concentrated
  in a small set of documentation/public-service sources.
- Realmanuals has stronger case count, but post-default-on monitoring does not
  yet run as part of a single retained-slice batch.
- Product-manual, model-number, mixed-language, tag, and cross-KB negative
  suites are not yet integrated into the post-default-on monitoring path.
- Release readiness currently references fixed report paths rather than a
  default-on monitoring manifest.

## Recommendation

Next child: create a default-on retained monitoring manifest and batch summary.

The child should not add new ranking behavior. It should define a small manifest
of retained slice names, suite paths, corpus paths, output paths, and thresholds;
then run or dry-run the existing eval/gate primitives through that manifest to
produce one bounded monitoring rollup. That gives the program a stable base
before expanding mixed-domain or multiformat case counts.
