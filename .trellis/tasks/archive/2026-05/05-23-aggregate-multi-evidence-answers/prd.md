# Aggregate multi evidence answers

## Goal

Improve answer quality after multi-evidence retrieval by making the local
extractive answer generator combine multiple relevant evidence chunks into a
clear answer for general knowledge/documentation questions.

The current retrieval layer can return multiple supporting chunks. The local
noop answer generator already supports multi-step troubleshooting answers, but
generic documentation questions still inherit a product-manual flavored prefix
and the fallback path only keeps one excerpt. This task makes the deterministic
offline answer path a better baseline before adding or relying on remote LLM
generation.

## Requirements

- Keep scope inside the answer layer; do not change retrieval ranking,
  embeddings, or external provider behavior.
- Preserve existing safety and unsupported-repair behavior for product manual
  questions.
- For generic multi-evidence answers, use a neutral answer prefix instead of a
  troubleshooting-specific prefix.
- When no excerpt passes relevance filtering but context evidence is available,
  fall back to multiple allowed excerpts, not only the first one.
- Keep citations attached to every evidence-backed sentence/step.
- Add focused tests for generic multi-evidence documentation answers.

## Acceptance Criteria

- [ ] A generic documentation question with two relevant context items produces
      a multi-evidence answer citing both items.
- [ ] Generic multi-evidence wording does not say "建议先这样处理".
- [ ] The fallback path can include up to `MAX_EXTRACTIVE_EXCERPTS` allowed
      excerpts when relevance filtering finds no overlap.
- [ ] Existing answer generator/API tests still pass.
- [ ] No fetched third-party web content is committed.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
