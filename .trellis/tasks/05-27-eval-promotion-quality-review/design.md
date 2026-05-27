# Eval Promotion Quality Review Design

## Scope

This task hardens the quality review around feedback-to-eval promotion. It does not change eval runner matching semantics.

## Data Flow

`SearchFeedback -> _feedback_to_eval_case -> preview/export response -> Retrieval Quality promotion summary -> Eval Report`

The promoted case keeps the existing eval fields. A new optional `quality` object is added to preview/export cases:

```json
{
  "quality": {
    "level": "strong|weak",
    "message": "...",
    "signals": ["text_contains", "anchor_key"]
  }
}
```

The eval runner ignores unknown fields, so this remains backward compatible for JSONL suites while giving the browser UI a visible quality signal.

## Matcher Strength

- Strong: any relevant matcher has `text_contains` or `anchor_key`.
- Weak: matchers only use broader fields such as `source_file`, `header`, or `metadata`.

Weak matchers are still exportable because real feedback sometimes starts with broad evidence. The UI should tell operators to run the browser eval and inspect the report before treating the case as a regression gate.
