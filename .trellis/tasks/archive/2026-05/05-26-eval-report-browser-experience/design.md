# Design: Eval report browser experience

## Architecture

Add a read-only admin report viewer that mirrors the existing admin UI pattern:

- Template: `src/tagmemorag/web/templates/eval_report.html`
- Static module: `src/tagmemorag/web/static/eval_report.js`
- Shared styling: extend `manual_library.css`
- API helper module: `src/tagmemorag/api_eval_report.py`
- Route wiring: `src/tagmemorag/api.py`

The API endpoint reads a caller-provided local report path, validates that it is a JSON object with a `cases` list, and returns a bounded UI summary. It does not run eval, write files, or alter the report. The route requires `admin` scope because it reads local filesystem paths and exposes retrieval evidence details.

## Data Flow

1. Retrieval Quality promotion returns `summary.report_path`.
2. `retrieval_quality.js` renders an `Open report` link to `/admin/eval-report?kb_name=<kb>&report_path=<encoded report_path>`.
3. `eval_report.html` reads initial config from the URL/default template context.
4. `eval_report.js` calls `GET /eval/report?path=<encoded report_path>` using the shared admin token.
5. `api_eval_report.summarize_eval_report_payload` converts raw report JSON into top-level metadata, metrics, count cards, sorted review items, bounded expected evidence, bounded actual top results, and config snapshot.

## Report Summary Contract

The response shape is intentionally UI-oriented and additive:

```json
{
  "schema_version": "eval_report_view.v1",
  "report_path": "...",
  "suite": "...",
  "docs": "...",
  "kb_names": ["default"],
  "top_k": 5,
  "summary": {"passed": false, "cases": 3, "precision_at_k": 0.5},
  "counts": {"passed": 1, "failed": 2, "urgent": 1, "review": 1, "ok": 1},
  "cases": [
    {
      "id": "case-id",
      "status": "urgent",
      "severity": 3,
      "query": "...",
      "metrics": {},
      "failures": [],
      "expected": [],
      "actual_top_k": [],
      "matched_expected_indexes": [0]
    }
  ],
  "config_snapshot": {}
}
```

## Severity Heuristic

The viewer is not a new evaluator. It explains existing eval output using conservative labels:

- `urgent`: explicit failures, negative hits, hit@k below 1, or recall 0.
- `review`: partial recall, low MRR, or no matched expected evidence.
- `ok`: case passed with at least one matching signal or no detected review signal.

These labels help operators triage, but the authoritative pass/fail state remains the eval report's own `passed` and `failures` fields.

## Compatibility

- Existing eval JSON reports remain unchanged.
- Existing `tagmemorag eval run` behavior remains unchanged.
- Existing Retrieval Quality export flow remains valid without a report file present; the viewer will show a missing-file error until the user runs the command.

## Rollback

The feature is isolated to one new read-only endpoint/page and one link from Retrieval Quality. Rolling back removes the new route/template/static asset and the link rendering without touching eval generation or feedback storage.
