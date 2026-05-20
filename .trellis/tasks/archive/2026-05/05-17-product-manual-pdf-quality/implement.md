# Implementation Plan — Product manual PDF structure and retrieval quality

> Parent documents: [prd.md](./prd.md) · [design.md](./design.md)

## Stages

### Stage 1: Parser structure primitives

- [x] Add internal PDF line/block extraction helpers.
- [x] Add deterministic heading candidate detection helpers.
- [x] Add PDF page metadata (`page_start`, `page_end`, `pdf_header_source`) to chunks.
- [x] Preserve existing Markdown/TXT parser behavior.
- [x] Add parser unit tests using fake `PdfReader`/page objects.

### Stage 2: Section-like PDF chunking

- [x] Replace one-page raw chunks with detected section blocks when confidence is sufficient.
- [x] Keep page fallback for pages with no reliable heading.
- [x] Ensure `_post_process` preserves PDF metadata through split/merge.
- [x] Add tests for fallback, detected heading, split long section, and short chunk merge behavior.

### Stage 3: Realmanuals ground truth

- [x] Inspect real PDF extracted text for the current realmanuals queries.
- [x] Replace at least 8 placeholder relevant entries with real expectations.
- [x] Keep any unresolved cases explicitly informational or excluded from strict eval.
- [x] Add tests ensuring no strict case uses `__PLACEHOLDER__`.

### Stage 4: Diagnostic loop

- [x] Extend `scripts/diag_realmanuals_eval.py` or add a parser-quality diagnostic.
- [x] Report per-manual chunks, detected/fallback counts, sample headers, and retrieval metrics.
- [x] Save diagnostic output under this task's `research/` directory.

### Stage 5: Search/eval integration review

- [x] Check whether eval runner should use metadata narrowing by default.
- [x] Add targeted tests if search path changes are needed.
- [x] Confirm product-manual model/category narrowing still works with PDF chunk metadata.

### Stage 6: Validation and docs

- [x] Update README/product manual docs if PDF parser behavior changes.
- [x] Run focused parser/eval tests.
- [x] Run full tests.
- [x] Run hashing eval CI.
- [x] Record results in `check.jsonl`.
- [ ] Commit changes.

## Validation Commands

```bash
.venv/bin/python -m pytest tests/unit/test_parser.py -q
.venv/bin/python -m pytest tests/unit/test_diag_realmanuals_eval.py tests/unit/test_eval_runner.py -q
.venv/bin/python -m pytest tests/ -q
.venv/bin/python scripts/run_eval_ci.py
.venv/bin/python scripts/diag_realmanuals_eval.py --reuse-built-kb
```

## Review Gates

- **Gate A**: Parser unit tests prove fallback behavior remains safe.
- **Gate B**: Realmanuals expectations are real, not placeholder-based.
- **Gate C**: Full regression and eval CI pass.
- **Gate D**: Diagnostic report shows whether lightweight heuristics are enough or whether a stronger parser task is needed.

## Notes

- Do not add OCR in this task.
- Do not introduce heavyweight parser dependencies unless lightweight `pypdf` heuristics clearly fail.
- Do not rename public manual APIs.
- Do not broaden scope to non-product-manual domains.
- `HISENSE DHQE800BW2.pdf` still contains noisy/garbled extracted text under `pypdf`; treat OCR or a stronger PDF parser as a separate future task if answer-level quality on that manual becomes important.
