# Real PDF And Document Intake Test - 2026-05-27

This report records the current local support boundary for real PDF manuals and Word-style documents.

## Scope

- Real text-based product manual PDFs under `product_manuals/`.
- Existing strict eval cases in `tests/fixtures/eval/realmanuals.jsonl`.
- Direct Manual Library source validation for `.doc` and `.docx`.
- Existing multiformat fixture path where remote `.docx` content is converted to Markdown before indexing.

Out of scope: native `.doc`/`.docx` parsing, OCR for scanned image-only PDFs, live providers, and remote downloads.

## Result

Real product-manual PDF intake is locally usable with the current parser and hashing embedding profile.

Focused real-PDF eval command:

```bash
uv run pytest tests/unit/test_eval_runner.py::test_run_eval_real_product_manual_pdfs_pass_current_quality_bar -q
```

Observed local metrics from the exploratory run:

| Metric | Value |
| --- | ---: |
| cases | 10 |
| recall@k | 0.966667 |
| MRR | 0.833333 |
| hit@k | 1.0 |

The retained regression test now enforces:

- `recall_at_k >= 0.95`
- `mrr >= 0.75`
- `hit_at_k == 1.0`

## PDF Notes

The real PDFs build and retrieve successfully, but `pypdf` emits repeated rotated-text warnings:

```text
Rotated text discovered. Output will be incomplete.
```

These warnings do not block the current build or eval pass. They are still important operator UX signals: a future parser/readiness task should summarize them into a bounded warning count instead of letting raw parser warnings flood logs.

## Doc And Docx Boundary

The project already has a limited `.docx` OpenXML text extractor in `scripts/seed_multiformat_real_knowledge.py`. That path converts `.docx` content into Markdown before indexing and preserves original-source metadata such as `source_format=docx`.

Direct `.doc` and `.docx` intake through Manual Library/source suffix validation is not currently supported by the native parser or the LangChain parser provider.

Current supported direct source suffixes:

- native parser: `.md`, `.pdf`, `.txt`
- LangChain parser: `.htm`, `.html`, `.md`, `.pdf`, `.txt`

The supported workaround for `.docx` today is that existing conversion path: extract OpenXML text, materialize a `.md` document, then index the Markdown. The multiformat fixture covers this path while preserving `source_format=docx` metadata.

## Recommendation

Next implementation should be one of these, in order:

1. Add operator-facing parser warning summarization for real PDFs, especially rotated text.
2. Promote the existing `.docx` OpenXML-to-Markdown extractor into an explicit Manual Library import path that materializes Markdown and preserves original-source metadata.
3. Consider `.doc` only after `.docx` is stable, because legacy binary Word files need a different dependency/tooling decision.
