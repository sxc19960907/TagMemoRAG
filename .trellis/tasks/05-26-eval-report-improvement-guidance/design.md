# Design: Eval report improvement guidance

## Architecture

Extend the existing read-only report viewer summary. The raw eval report remains unchanged; `api_eval_report.py` derives guidance from case fields and includes it in the UI-oriented response.

Changed surfaces:

- `src/tagmemorag/api_eval_report.py`: deterministic guidance heuristics and aggregate guidance counts.
- `src/tagmemorag/web/static/eval_report.js`: render guidance cards inside each case.
- `src/tagmemorag/web/static/manual_library.css`: compact guidance card styles.
- `src/tagmemorag/web/static/i18n.js`: Chinese labels for new guidance copy.
- Tests: focused API/UI/browser coverage.

## Contract

Each case summary gains:

```json
{
  "primary_issue": "no_expected_match",
  "guidance": [
    {
      "code": "no_expected_match",
      "severity": "urgent",
      "title": "No expected evidence matched",
      "explanation": "None of the expected evidence appeared in the retrieved top results.",
      "next_action": "Check whether the source exists in the KB and whether the expected matcher is specific enough."
    }
  ]
}
```

Top-level response gains:

```json
{
  "guidance_counts": {"no_expected_match": 3, "partial_recall": 1}
}
```

## Heuristics

- `no_expected_match`: expected evidence exists and no `matched_expected_indexes` are present.
- `partial_recall`: some expected evidence matched but recall is below 1.
- `low_rank`: expected evidence matched, but the first matching rank is after rank 1 or MRR is below 0.5.
- `negative_hit`: report contains `negative_hits`.
- `threshold_failure`: case has explicit `failures`.
- `weak_matcher`: expected evidence is absent or expected entries lack `source_file`, `text_contains`, `header`, `anchor_key`, and metadata.

Guidance is advisory only. Existing `passed`, `failures`, and metric values remain the authoritative eval results.

## Compatibility

The API response is additive. Existing UI tests and clients that ignore unknown fields keep working. No CLI or report schema changes are made.
