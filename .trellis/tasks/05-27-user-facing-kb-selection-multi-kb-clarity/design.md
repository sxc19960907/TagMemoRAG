# User Facing KB Selection And Multi KB Clarity Design

## Scope

Modify the user-facing QA page only. Admin pages already have KB inputs and navigation links. API contracts remain unchanged.

## UI Design

Add a compact `Knowledge base` block in the QA left rail, directly under the assistant context card:

- A readonly-looking active KB label.
- A `<select>` populated from `/kb`.
- A short hint explaining that switching reloads the QA page for the chosen KB.

If `/kb` fails, keep the current KB visible and show a muted fallback message. If `/kb` returns no entries, include the current KB as the only option.

## Navigation

Changing the selector uses `window.location.assign("/qa?kb_name=<selected>")`. If the URL contains a `question` parameter, preserve it so eval report deep links and copied troubleshooting links keep their prefilled question.

## Compatibility

Do not add `kb_name` to `/qa/answer` in this task. The answer endpoint's current auto-routing behavior is useful when the active page has ambiguous context, and changing that contract would expand the task beyond UI clarity.

## Rollback

Revert the QA template, JS, CSS, i18n, and tests. No data migration or API rollback is required.
