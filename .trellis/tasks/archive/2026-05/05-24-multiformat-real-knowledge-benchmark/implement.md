# Implementation Plan

1. [x] Identify stable real public PDF and DOCX/DOC-style sources that can be fetched in this environment.
2. [x] Add a multi-format materializer script or source module that writes HTML-derived Markdown, PDF files, DOCX-derived Markdown, and metadata sidecars under `.tmp`.
3. [x] Add a multi-format eval suite with HTML/PDF/DOCX cases and metadata expectations.
4. [x] Add a live answer diagnostic or extend an existing one for the multi-format suite.
5. [x] Run materialization and initial eval; inspect failures and decide whether a small optimization is needed.
6. [x] Implement the smallest needed optimization, if any.
7. [x] Add no-network unit tests for materialization behavior and suite/script coverage.
8. [x] Update README and backend architecture docs.
9. [x] Run focused tests, real multi-format eval, answer diagnostic, `git diff --check`; archive, commit, and journal.

## Validation Commands

```bash
.venv/bin/python -m pytest tests/unit/test_multiformat_real_knowledge.py -q
.venv/bin/python scripts/seed_multiformat_real_knowledge.py --output-dir .tmp/multiformat-real-knowledge --kb multiformat_real
.venv/bin/python -m tagmemorag eval run --suite tests/fixtures/eval/multiformat_real_knowledge.jsonl --docs .tmp/multiformat-real-knowledge/multiformat_real --config examples/config/local-hashing-npz.yaml --kb multiformat_real --top-k 8 --min-recall-at-k 0.0 --min-mrr 0.0 --min-hit-at-k 0.0 --output .tmp/eval/multiformat-real-knowledge.json
.venv/bin/python scripts/diag_multiformat_answer_eval.py --docs .tmp/multiformat-real-knowledge/multiformat_real --suite tests/fixtures/eval/multiformat_real_knowledge.jsonl --config examples/config/local-hashing-npz.yaml --kb multiformat_real --top-k 8 --output .tmp/eval/multiformat-real-answer.json
git diff --check
```

## Risk Points

- Public DOCX URLs can disappear or block automated fetches. Keep source choices explicit and easy to replace.
- DOCX extraction should avoid macro/script execution; only read zipped OpenXML text parts.
- PDF text extraction can be noisy; choose text-based PDFs and use broad but meaningful `text_contains` expectations.
- Live URL materialization should stay opt-in and out of normal unit-test CI.
