# Eval Promotion Quality Review

## Goal

Review and harden eval draft quality when promoting real feedback from Retrieval Quality.

## Requirements

- Keep promoted eval drafts compatible with the existing eval runner (`id`, `query`, `kb_name`, `relevant`, `tags`, `notes`).
- Surface promotion quality in preview/export results so operators can distinguish stable matchers from weak matchers.
- Do not block useful feedback promotion solely because a matcher is weak; warn and route operators to browser eval/report review.
- Treat matchers with `text_contains` or `anchor_key` as stronger than source/header/manual-only matchers.
- Preserve existing skip behavior for unusable feedback and duplicate case ids.

## Acceptance Criteria

- [ ] Promotion preview cases include quality metadata describing matcher strength.
- [ ] Retrieval Quality renders weak matcher warnings in the promotion summary.
- [ ] Browser feedback-to-eval flow still previews, exports, and opens the eval run launcher.
- [ ] Unit tests cover strong and weak promotion quality metadata.
- [ ] Focused validation passes before commit and archive.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
