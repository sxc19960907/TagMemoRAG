# Eval case review report design

## Boundary

The tool is a report summarizer. It reads an eval report already produced by `tagmemorag eval run --output` and emits a bounded review queue.

In scope:

- `scripts/summarize_eval_case_review.py`
- Tests for helper functions and CLI behavior
- README / eval workflow docs

Out of scope:

- Running eval itself
- Calling embedding providers
- Editing fixtures or baselines
- Replacing `scripts/relabel_eval_fixture.py`

## Input

Expected input is the existing eval report JSON shape:

- top-level `suite`, `summary`, and `cases`
- each case may contain `id`, `query`, `kb_name`, `metrics`, `expected`, `actual_top_k`, `failures`, and `negative_hits`

The script must tolerate missing optional fields and fail clearly when the file is unreadable or not a JSON object.

## Output Contract

Schema: `eval_case_review.v1`

Top-level fields:

- `schema_version`
- `report_path`
- `suite`
- `summary`
- `items`

Each item:

- `case_id`
- `kb_name`
- `severity`: 0-3
- `status`: `ok`, `review`, or `urgent`
- `reasons`
- `metrics`
- `failures`
- `expected_count`
- `matched_expected_indexes`
- `top_results`: bounded list of `{rank, source_file, header, matched_expected_indexes, score}`
- `negative_hits`
- `query`: only present when `--include-query` is set

## Severity Rules

- Severity 3 / `urgent`: explicit failures, negative hits, `hit_at_k == 0`, or `recall_at_k == 0`.
- Severity 2 / `review`: `recall_at_k < 0.75`, `mrr < 0.5`, or matched expectations are fewer than expected.
- Severity 1 / `review`: `recall_at_k < 1.0` or `mrr < 1.0`.
- Severity 0 / `ok`: no review signal.

Suite-level synthetic cases such as `__suite__` stay in the output if they have failures, but their `top_results` is empty.

## CLI

```bash
python scripts/summarize_eval_case_review.py \
  --report .tmp/eval-report.json \
  --format markdown \
  --output .tmp/eval-review.md
```

Options:

- `--format json|markdown`
- `--output <path>`
- `--include-query`
- `--max-results`, default `5`
- `--include-ok`, default false

Exit codes:

- `0`: report produced
- `2`: invalid input

## Privacy

Default output excludes `query`, raw result text, metadata, vectors, and unbounded source lists. It includes source file and header names because those are fixture identifiers needed for review.
