# Readiness Next Action Center Design

## Backend

Extend `api_rag_readiness.rag_readiness_summary` without changing the route path or existing field meanings.

New fields:

```json
{
  "primary_action": {"label": "...", "href": "...", "kind": "primary"},
  "recommendations": [
    {
      "code": "...",
      "label": "...",
      "severity": "warning",
      "href": "...",
      "action_label": "...",
      "kind": "warning"
    }
  ]
}
```

Actions remain links only. They route to existing browser pages with `kb_name` and, where safe, `report_path`.

## Frontend

`rag_readiness.js` will:

- Render `primary_action` prominently in the hero action area.
- Render recommendation action links inside each recommendation card.
- Keep base action links as secondary navigation.

`qa_page.html/js` will keep the existing Readiness link and add a compact callout style if needed. It will not fetch readiness summary to avoid adding extra admin-scope API requirements to a user-facing page.

## Safety

- No mutation endpoints.
- No raw report case contents.
- Report links use existing safe report paths already returned by the eval report discovery layer.
- Existing clients can ignore the new additive fields.
