# QA three pane layout

## Goal

Redesign the existing `/qa` page into a more polished three-pane interface inspired by Codex-style workspaces: left context rail, center question-answer flow, and right citations/sources rail.

## Requirements

- Keep the existing `/qa` route and `/answer` request contract unchanged.
- Split the page into three desktop regions:
  - left rail for product name, selected KB, readiness/status, and optional API token
  - center pane for answer state and the question composer
  - right rail for cited sources
- Make the center pane feel like the primary workspace, with a bottom composer and visible answer surface.
- Keep debug internals hidden from the user page.
- Collapse gracefully on narrower screens without overlapping text or controls.
- Reuse existing Jinja2 + vanilla JS + shared CSS asset pattern.

## Acceptance Criteria

- [x] `/qa?kb_name=ops` renders the three-pane shell with left context, center chat/workspace, and right sources pane.
- [x] The existing ask flow still sends `POST /answer` with `include_retrieve=true`, `top_k=5`, `source_k=8`, and `mode="classic"`.
- [x] KB changes update visible state and URL query param.
- [x] Empty, pending, refusal/error, and source states remain user-readable.
- [x] Focused UI tests pass and cover the new shell markers.
- [x] Browser visual check confirms desktop layout is three-pane and responsive enough to use.

## Notes

- Lightweight task: PRD-only is sufficient because this is a UI layout iteration over an existing route and API contract.
