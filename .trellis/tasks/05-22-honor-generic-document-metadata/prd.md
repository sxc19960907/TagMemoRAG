# Honor generic document metadata

## Goal

Make public/general knowledge documents keep their sidecar-declared generic
metadata after build. Public web samples currently write `domain` and
`doc_type` into sidecars, but the build path loads them through
`ManualMetadata` and then `manual_node_attrs`, which forces all documents to
`domain=product_manual` and `doc_type=manual`.

This task should respect explicit generic sidecar fields while preserving
backward-compatible product manual fields and existing manual eval behavior.

## Requirements

- Preserve existing product manual behavior when sidecars omit generic
  `domain` / `doc_type`.
- If a sidecar includes `domain` and/or `doc_type`, carry those values into
  build chunk metadata and search results instead of forcing
  `product_manual/manual`.
- Preserve legacy fields such as `manual_id`, `manual_title`,
  `product_category`, `product_model`, and public tags so current UI/API/eval
  consumers remain compatible.
- Preserve connector/public web sidecar fields such as `remote_id` and `url`
  in node metadata where safe.
- Avoid broad renaming of manual APIs in this slice.

## Acceptance Criteria

- [ ] Unit tests prove `ManualMetadata.from_dict` keeps safe extra sidecar
      fields.
- [ ] Unit tests prove `manual_node_attrs` respects explicit
      `domain=software_docs` and `doc_type=documentation`.
- [ ] Public web materialize + build smoke shows a generated Python docs page
      is indexed with `domain=software_docs` and `doc_type=documentation`.
- [ ] Existing product manual eval and connector tests remain green.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
