# ManualsLib real sample quality slice

## Goal

Use the OpenCLI-backed ManualsLib import path to create a small, category-diverse real manual sample and measure retrieval quality against realistic user questions.

## Requirements

- Import a bounded runtime-only sample from ManualsLib using `manualslib import-opencli`.
- Cover at least three Hisense categories when available, prioritizing dryer, washer, refrigerator, TV, and air conditioner.
- Keep imported third-party manual content under `.tmp/` or another ignored runtime directory.
- Build a hashing-profile KB from the imported sample so validation is deterministic and cheap.
- Create a runtime eval JSONL under `.tmp/` with realistic questions tied to imported manual URLs/models.
- Run retrieval evaluation and record metrics plus notable failure patterns.
- Do not commit downloaded ManualsLib manual content.

## Acceptance Criteria

- [x] Runtime sample includes at least three imported ManualsLib manuals from at least three categories, or records why fewer were available.
- [x] Imported sample can build successfully with the hashing provider.
- [x] A runtime eval suite exists under `.tmp/` and runs against the sample KB.
- [x] Retrieval metrics and failure observations are recorded in this task.
- [x] Existing realmanuals retrieval and answer-quality gates are not regressed.

## Notes

- This task is validation/data-quality oriented. Code changes are optional and should only happen if the validation exposes a narrow, well-understood fix.

## Result

Runtime-only sample was imported under `.tmp/manualslib-quality-slice` using the OpenCLI-backed command:

- Dryer: `HDGE80H`, 20 pages, 433 extracted lines.
- Washer: `WDQE8014EVJM`, 20 pages, 47 extracted lines.
- Refrigerator: `RQ5P470SYID`, 20 pages, 559 extracted lines.
- TV: `58A7100F`, 20 pages, 666 extracted lines.

The sample built successfully as KB `manualslib_quality` with 239 chunks using `.tmp/manualslib-quality-config.yaml`.

Runtime eval:

- Suite: `.tmp/manualslib-quality-eval.jsonl`
- Report: `.tmp/manualslib-quality-report-fixed.json`
- Result: `cases=6`, `precision@5=0.200000`, `recall@5=1.000000`, `mrr=0.833333`, `hit@5=1.000000`

Regression gates:

- `tests/fixtures/eval/realmanuals.jsonl` on `product_manuals`: `precision@5=0.320000`, `recall@5=0.966667`, `mrr=0.691667`, `hit@5=1.000000`
- `tests/fixtures/answer_quality/qa_product_manual.jsonl`: passed 6 cases.

Observations:

- The OpenCLI import path is usable for category-diverse real samples without committing third-party manual content.
- ManualsLib extraction quality varies by manual: `WDQE8014EVJM` produced sparse text in the first 20 pages and is less useful for retrieval validation unless more pages or a different washer candidate is selected.
- The eval matcher is sensitive to PDF/OCR line breaks. Initial expectations using visually continuous phrases undercounted hits even when correct chunks ranked in the top results. Runtime eval expectations were adjusted to actual chunk text. A future evaluation-tooling task should consider normalized whitespace matching for `text_contains`.
